"""Stage 1B evidence ledger. No competition identity is inferred from a seat pool.

Base facts replay through the existing 1A adapter. New page excerpts are compact
review artifacts; full newly fetched pages remain outside Git and D1.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from lxml import html

from .import_mephi import insert_sql, import_plan
from .mephi_pipeline import OUT, validate_dataset
from .sources import SnapshotStore, canonical, digest, write_json
from .validate import ROOT, require

VERSION = 'mephi-competition-review-v1'
OUTPUT = OUT / 'competition_research.json'
REVIEW = ROOT / 'data/reviews/mephi_1b_findings.json'
EXCERPTS = ROOT / 'tests/fixtures/mephi/1b'


def proof(row):
    p = row['provenance']
    return dict(source_id=p['source_id'], url=p['url'], snapshot_sha256=p['snapshot_sha256'],
                locator=p.get('locator') or f"page={p.get('page')}; first_line={p.get('first_line')}")


def reviewed_findings():
    review = json.loads(REVIEW.read_text())
    require(review['assessment_version'] == VERSION, 'research_version_mismatch')
    for excerpt in review['source_excerpts']:
        path = EXCERPTS / excerpt['file']
        require(path.parent == EXCERPTS and path.suffix == '.html', 'invalid_excerpt_path')
        data = path.read_bytes()
        require(digest(data) == excerpt['excerpt_sha256'], 'research_excerpt_hash_mismatch')
        require(len(excerpt['parent_sha256']) == 64 and excerpt['source_url'].startswith('https://admission.mephi.ru/'), 'research_excerpt_provenance')
        # No roster, IDs or applicant rows are accepted by these metadata adapters.
        root = html.fromstring(data)
        if excerpt['kind'] == 'entrants_navigation':
            buttons = root.xpath('.//button[contains(text(),"г. Москва")]')
            require(len(buttons) == 1 and buttons[0].get('onclick') == "document.location='https://org.mephi.ru/pupil-rating/index/osp/1'", 'entrants_target_changed')
        elif excerpt['kind'] == 'enrollment_publication_notice':
            text = ' '.join(root.text_content().split())
            require('приказы о зачислении не публикуются' in text and 'Списки зачисленных' in text, 'orders_notice_changed')
            require(root.xpath('.//a[@href="https://admission.mephi.ru/lists/entrants"]'), 'orders_lists_link_changed')
        else:
            raise ValueError('unknown_research_excerpt_kind')
    return review


def fetch_metadata():
    """Fetch navigation/notice only; never follow the link to personal lists."""
    store = SnapshotStore(directory=ROOT/'data/raw/mephi_1b')
    for name, path in [('entrants','lists/entrants'), ('orders','lists/orders')]:
        snapshot = store.fetch('mephi-1b-'+name, 'https://admission.mephi.ru/'+path, refresh=True)
        print(name, snapshot['sha256'])
    return store


def replay_excerpts(store):
    review = reviewed_findings()
    for excerpt in review['source_excerpts']:
        sources = [s for s in store.manifest['snapshots'] if s['url']==excerpt['source_url'] and s['sha256']==excerpt['parent_sha256']]
        require(len(sources)==1, 'matching_parent_snapshot_missing_or_changed')
        root = html.fromstring(store.read(sources[0]), parser=html.HTMLParser(encoding='utf-8',no_network=True))
        nodes = root.xpath(excerpt['locator'])
        require(len(nodes)==1, 'research_excerpt_locator_changed')
        content = b'<!doctype html><html><meta charset="utf-8"><body><section>'+html.tostring(nodes[0],encoding='utf-8',with_tail=False)+b'</section></body></html>\n'
        require(digest(content)==excerpt['excerpt_sha256'], 'research_excerpt_does_not_replay')


def build_research(dataset, store):
    validate_dataset(dataset, store)
    review = reviewed_findings()
    require({r['code'] for r in review['discrepancies']} == {r['code'] for r in dataset['review_queue']}, 'six_discrepancies_must_remain_identifiable')
    require(len(review['discrepancies']) == 6, 'unexpected_discrepancy_count')
    group_assessments = []
    for allocation in dataset['seats']['records']:
        payload = dict(group_id=allocation['id']+'-candidate', campaign_year=2026,
                       status='unresolved', basis='allocation_scope_only',
                       evidence=[proof(allocation)], assessment_version=VERSION)
        group_assessments.append(dict(id='group-review-'+digest(payload)[:24], **payload))
    history_assessments = []
    for observation in dataset['history']['records']:
        payload = dict(observation_id=observation['id'], campaign_year=observation['year'],
                       group_id=None, status='unresolved', reason='no_documented_same_year_competition_identity',
                       evidence=[proof(observation)], assessment_version=VERSION)
        history_assessments.append(dict(id='history-review-'+digest(payload)[:24], **payload))
    known = {s['sha256']: s for s in store.manifest['snapshots']}
    for finding in review['discrepancies'] + review['priority_findings']:
        require(finding['status'] in {'unresolved','partially_resolved','resolved'}, 'invalid_finding_status')
        require(finding['evidence'], 'finding_requires_evidence')
        for evidence in finding['evidence']:
            require(evidence['snapshot_sha256'] in known, 'unknown_finding_snapshot')
            source = known[evidence['snapshot_sha256']]
            require(evidence['url'] == source['url'] and evidence['source_id'] == source['source_id'], 'finding_source_mismatch')
            require(evidence['locator'], 'finding_locator_required')
            # Every cited baseline source is checked against its original bytes.
            store.read(source)
    group_counts = Counter(r['status'] for r in group_assessments)
    history_counts = Counter(r['status'] for r in history_assessments)
    return dict(assessment_version=VERSION, base_dataset_sha256=digest(dataset),
                group_assessments=group_assessments, history_assessments=history_assessments,
                findings=review, metrics=dict(
                    confirmed=group_counts['confirmed'], inferred=group_counts['inferred'],
                    unresolved_allocation_candidates=group_counts['unresolved'],
                    actual_competition_count=None, historical_rows_confirmed=history_counts['confirmed'],
                    historical_rows_unresolved=history_counts['unresolved'],
                    unresolved_source_discrepancies=sum(r['status']!='resolved' for r in review['discrepancies']),
                    score_distributions_available=False, forecasting_ready=False))


def validate_research(research, dataset, store):
    require(research == build_research(dataset, store), 'research_does_not_replay')


def research_plan(research, dataset, store):
    validate_research(research, dataset, store)
    snapshots = {s['sha256']: 'snapshot-'+digest([s['source_id'],s['sha256']])[:32] for s in store.manifest['snapshots']}
    statements = import_plan(dataset, store)
    for row in research['group_assessments']:
        statements.append(insert_sql('competition_group_assessments', dict(
            id=row['id'], group_id=row['group_id'], status=row['status'], basis=row['basis'],
            evidence_json=canonical(row['evidence']), source_snapshot_id=snapshots[row['evidence'][0]['snapshot_sha256']],
            supersedes_id=None, assessment_version=VERSION, payload_json=canonical(row))))
    for row in research['history_assessments']:
        statements.append(insert_sql('historical_group_assessments', dict(
            id=row['id'], observation_id=row['observation_id'], group_id=row['group_id'], status=row['status'],
            reason=row['reason'], evidence_json=canonical(row['evidence']), assessment_version=VERSION,
            payload_json=canonical(row))))
    return statements


def import_research(connection, research, dataset, store):
    before = connection.total_changes
    try:
        connection.execute('BEGIN')
        for statement in research_plan(research, dataset, store):
            connection.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return connection.total_changes-before


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build','validate','export-sql','fetch-metadata','replay-excerpts'])
    parser.add_argument('--output', type=Path, default=OUT / 'competition_research.sql')
    args = parser.parse_args()
    if args.command == 'fetch-metadata':
        fetch_metadata(); return
    if args.command == 'replay-excerpts':
        replay_excerpts(SnapshotStore(directory=ROOT/'data/raw/mephi_1b'))
        print('Official metadata excerpts replay from matching full snapshots.'); return
    dataset = json.loads((OUT/'dataset.json').read_text()); store = SnapshotStore()
    if args.command == 'build':
        research = build_research(dataset, store); write_json(OUTPUT, research)
    else:
        research = json.loads(OUTPUT.read_text()); validate_research(research, dataset, store)
    if args.command == 'export-sql':
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text('-- Stage 1B public aggregates and unresolved assessments. Apply migrations 0001-0005 first.\n'+'\n'.join(research_plan(research,dataset,store))+'\n')
    print(json.dumps(research['metrics'], ensure_ascii=False))


if __name__ == '__main__':
    main()
