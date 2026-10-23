"""Discover → Fetch → Snapshot → Parse → Normalize → Validate → Review → Import."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess
from urllib.parse import urljoin

from .mephi import (ADAPTER_VERSION, ParseError, body, discover, document, parse_catalog,
                    parse_history, parse_moscow_fields_pdf_text, parse_seats, text)
from .sources import SnapshotStore, digest, write_json, timestamp
from .validate import ROOT, number, require

BASE = 'https://admission.mephi.ru/admission/baccalaureate-and-specialty/'
ENTRYPOINTS = dict(history='exams/previous-years', moscow='education/moscow', education='education',
                   documents='documents', exams='exams', rules='rules')
OUT = ROOT / 'data/normalized/mephi'


def fetch(refresh=False):
    store = SnapshotStore()
    failures = []
    for name, path in ENTRYPOINTS.items():
        try:
            store.fetch('mephi-' + name, BASE + path, refresh=refresh)
        except Exception as error:
            failures.append(dict(source=name, status='fetch_error', error=str(error)))
    for parent, name, predicate in [
        ('education', 'programs', lambda label, href: label == 'Образовательные программы'),
        ('documents', 'fields', lambda label, href: label.startswith('Перечень специальностей и направлений подготовки')),
        ('documents', 'kcp', lambda label, href: label.startswith('Количество мест для приёма на обучение по различным условиям')),
        ('documents', 'admission-rules', lambda label, href: label.startswith('Правила приема в НИЯУ МИФИ на 2026/2027')),
    ]:
        try:
            snapshot = latest(store, 'mephi-' + parent)
            anchors = body(document(store.read(snapshot))).xpath('.//a[@href]')
            links = {urljoin(snapshot['url'], a.get('href')) for a in anchors if predicate(text(a), a.get('href'))}
            if len(links) != 1:
                raise ParseError('ambiguous_or_missing_discovery_link:' + name)
            store.fetch('mephi-' + name, links.pop(), refresh=refresh)
        except Exception as error:
            failures.append(dict(source=name, status='discover_or_fetch_error', error=str(error)))
    write_json(OUT / 'fetch_errors.json', failures)
    if failures:
        raise ParseError('some_sources_unavailable_see_fetch_errors')
    return store


def latest(store, source_id):
    candidates = [s for s in store.manifest['snapshots'] if s['source_id'] == source_id]
    if not candidates:
        raise ParseError('missing_snapshot:' + source_id)
    return candidates[-1]


def validate_dataset(dataset, store):
    snapshots = {s['sha256']: s for s in store.manifest['snapshots']}
    checked = set()
    for rows in (dataset['history']['records'], dataset['catalog']['records'], dataset['seats']['records'], dataset['official_fields']):
        ids = set()
        for row in rows:
            identity = row.get('id', row.get('official_code'))
            require(identity not in ids, 'duplicate_normalized_identity')
            ids.add(identity)
            p = row['provenance']
            require(p.get('url', '').startswith('https://admission.mephi.ru/'), 'official_source_url_required')
            require(p['snapshot_sha256'] in snapshots, 'unknown_snapshot')
            source = snapshots[p['snapshot_sha256']]
            require(p['source_id'] == source['source_id'] and p['url'] == source['url'], 'source_provenance_mismatch')
            if p['snapshot_sha256'] not in checked:
                store.read(source)
                checked.add(p['snapshot_sha256'])
    for row in dataset['history']['records']:
        require(type(row['year']) is int and 2015 <= row['year'] <= 2025, 'history_year_outside_scope')
        require(row['threshold_status'] in {'numeric','bvi_only','not_published','not_offered','parse_error','manual_review'}, 'threshold_status')
        require((row['threshold_status'] == 'numeric') == (row['cutoff'] is not None), 'threshold_value_status_conflict')
        if row['cutoff'] is not None:
            require(number(row['cutoff']) and row['cutoff'] >= 0, 'invalid_cutoff')
        if row['mean_ege_score'] is not None:
            require(number(row['mean_ege_score']) and 0 <= row['mean_ege_score'] <= 100, 'mean_ege_scale')
        if row['mean_entrance_total'] is not None:
            require(number(row['mean_entrance_total']) and row['mean_entrance_total'] >= 0, 'mean_entrance_scale')
        require(row['competition_group_id'] is None and row['group_mapping_status'] == 'unresolved', 'unreviewed_historical_group_mapping')
    for a in dataset['seats']['records']:
        require(type(a['places']) is int and a['places'] >= 0, 'invalid_seats')
        require(len(set(a['codes'])) == len(a['codes']), 'duplicate_allocation_member')
    budget = dataset['seats']['sum_budget']
    require(budget == dataset['seats']['published_totals']['ИТОГО Бакалавриат и специалитет 2026'], 'budget_total_mismatch')
    expected = dataset['history']['expected_rows_by_year']
    actual = Counter(r['year'] for r in dataset['history']['records'])
    require({int(y): n for y, n in expected.items()} == dict(actual), 'history_row_count_mismatch')
    require(len(dataset['catalog']['records']) == dataset['catalog']['expected_source_rows'], 'catalog_row_count_mismatch')
    require(not dataset['history']['errors'], 'history_parse_errors_require_review')
    # A source hash alone does not prove that a normalized value came from that source.
    # Replay extraction and compare facts before allowing import of edited JSON.
    for section, parser in [('history', parse_history), ('seats', parse_seats)]:
        sha = dataset[section]['records'][0]['provenance']['snapshot_sha256']
        snapshot = snapshots[sha]
        require(digest(parser(store.read(snapshot), snapshot)) == digest(dataset[section]), 'normalized_facts_do_not_replay:' + section)
    sha = dataset['official_fields'][0]['provenance']['snapshot_sha256']
    pdf = snapshots[sha]
    extracted = subprocess.run(['pdftotext','-layout',str(ROOT / pdf['path']),'-'],
                               capture_output=True, check=True, timeout=30).stdout.decode('utf-8')
    require(parse_moscow_fields_pdf_text(extracted, pdf) == dataset['official_fields'], 'official_fields_do_not_replay')
    sha = dataset['catalog']['records'][0]['provenance']['snapshot_sha256']
    snapshot = snapshots[sha]
    catalog = parse_catalog(store.read(snapshot), snapshot)
    official = {r['official_code'] for r in dataset['official_fields']}
    for row in catalog['records']:
        row['admission_status'] = 'direction_listed_2026_profile_not_individually_confirmed' if row['official_code'] in official else 'direction_not_in_2026_moscow_list_requires_review'
    require(catalog == dataset['catalog'], 'catalog_facts_do_not_replay')


def build():
    store = SnapshotStore()
    dataset = dict(schema_version=2, adapter_version=ADAPTER_VERSION, institution_id='mephi',
                   campus_id='mephi-moscow', catalog_year=2026, forecasting_enabled=False)
    for key, name, parser in [('history','history',parse_history),('catalog','programs',parse_catalog),('seats','moscow',parse_seats)]:
        snapshot = latest(store, 'mephi-' + name)
        dataset[key] = parser(store.read(snapshot), snapshot)
    pdf = latest(store, 'mephi-fields')
    text_path = ROOT / 'data/raw/mephi/fields-2026.pdftotext.txt'
    subprocess.run(['pdftotext', '-layout', str(ROOT / pdf['path']), str(text_path)], check=True, timeout=30)
    dataset['official_fields'] = parse_moscow_fields_pdf_text(text_path.read_text(), pdf)
    official = {f['official_code'] for f in dataset['official_fields']}
    catalog_codes = {p['official_code'] for p in dataset['catalog']['records']}
    seat_codes = {c for a in dataset['seats']['records'] for c in a['codes']}
    for p in dataset['catalog']['records']:
        p['admission_status'] = 'direction_listed_2026_profile_not_individually_confirmed' if p['official_code'] in official else 'direction_not_in_2026_moscow_list_requires_review'
    discrepancies = []
    for code in sorted((catalog_codes | seat_codes) - official):
        discrepancies.append(dict(kind='scope_discrepancy_not_resolved', code=code,
            in_catalog=code in catalog_codes, in_seat_plan=code in seat_codes, in_official_fields=False,
            note='May reflect year/campus/applicant-category differences. Do not infer program absence or resolve automatically.',
            source_ids=['mephi-programs','mephi-moscow','mephi-fields']))
    for code in sorted(official - catalog_codes):
        discrepancies.append(dict(kind='profile_catalog_gap', code=code, in_official_fields=True,
                                  note='Official admission direction lacks a detailed profile row.', source_ids=['mephi-fields','mephi-programs']))
    dataset['review_queue'] = discrepancies
    validate_dataset(dataset, store)
    history = dataset['history']['records']
    repeated = defaultdict(list)
    for row in history:
        if row['official_code']:
            repeated[row['year'], row['official_code']].append(row['id'])
    metrics = dict(program_profiles=len(dataset['catalog']['records']),
        expected_published_profile_rows=dataset['catalog']['expected_source_rows'],
        profile_source_row_coverage=1.0, catalog_complete_for_admission_campaign=False,
        official_admission_directions_2026=len(official), profile_direction_codes=len(catalog_codes),
        competition_groups_confirmed=0, competition_group_candidates=len(dataset['seats']['records']),
        seat_allocations=len(dataset['seats']['records']),
        total_budget_places=dataset['seats']['sum_budget'], total_paid_places=dataset['seats']['sum_paid'],
        historical_rows=len(history), historical_years=sorted({r['year'] for r in history}),
        expected_published_history_rows=sum(dataset['history']['expected_rows_by_year'].values()),
        historical_source_row_coverage=1.0, expected_program_year_universe=None,
        historical_rows_mapped_to_confirmed_group=0, historical_rows_requiring_group_review=len(history),
        rows_with_published_code=sum(r['official_code'] is not None for r in history),
        numeric_thresholds=sum(r['threshold_status']=='numeric' for r in history),
        bvi_only=sum(r['threshold_status']=='bvi_only' for r in history),
        threshold_status_counts=dict(Counter(r['threshold_status'] for r in history)),
        rows_with_confirmed_source=len(history), numeric_conflicts_within_confirmed_group=0,
        unresolved_source_discrepancies=len(discrepancies), repeated_year_code_keys=sum(len(v)>1 for v in repeated.values()),
        extraction_errors=len(dataset['history']['errors']))
    write_json(OUT / 'dataset.json', dataset)
    for name, value in [('history',dataset['history']),('catalog',dataset['catalog']),('seats',dataset['seats']),('official_fields',dataset['official_fields']),('review_queue',discrepancies),('metrics',metrics)]:
        write_json(OUT / (name+'.json'), value)
    write_json(OUT / 'dataset_identity.json', dict(adapter_version=ADAPTER_VERSION, sha256=digest(dataset)))
    return dataset, metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['fetch','build','run','validate'])
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    if args.command in ('fetch','run'):
        fetch(args.refresh)
    if args.command in ('build','run'):
        try:
            _, metrics = build()
        except Exception as error:
            error_path = OUT / 'extraction_errors.json'
            previous = json.loads(error_path.read_text()) if error_path.exists() else []
            previous.append(dict(attempted_at=timestamp(), status='parse_error', adapter_version=ADAPTER_VERSION, error=str(error)))
            write_json(error_path, previous)
            raise
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if args.command == 'validate':
        validate_dataset(json.loads((OUT / 'dataset.json').read_text()), SnapshotStore())
        print('MEPhI dataset: valid provenance, statuses, scopes and source-row counts; group mapping unresolved.')


if __name__ == '__main__':
    main()
