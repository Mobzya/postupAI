"""Validated, append-only import with both SQLite execution and D1 SQL export."""
import argparse
import json
from pathlib import Path
import sqlite3

from .mephi import ADAPTER_VERSION
from .mephi_pipeline import OUT, validate_dataset
from .sources import SnapshotStore, canonical, digest
from .validate import ROOT


def literal(value):
    if value is None:
        return 'NULL'
    if type(value) in (int, float):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def insert_sql(table, row, key='id'):
    fields = ','.join(row)
    values = ','.join(literal(value) for value in row.values())
    payload = {'admission_observations':'payload_json','seat_allocations':'evidence_json','campaign_field_offerings':'evidence_json'}.get(table)
    if payload:
        # A different payload under the same identity is a conflict, not a replay.
        # The append-only trigger rejects this UPDATE; unchanged facts are a no-op.
        conflict = f'DO UPDATE SET id=excluded.id WHERE {table}.{payload} <> excluded.{payload}'
    else:
        conflict = 'DO NOTHING'
    return f'INSERT INTO {table}({fields}) VALUES ({values}) ON CONFLICT({key}) {conflict};'


def import_plan(dataset, store):
    validate_dataset(dataset, store)
    sql = []
    def add(table, **row):
        sql.append(insert_sql(table, row))
    snapshots = [s for s in store.manifest['snapshots'] if s['source_id'] != 'robots']
    batch = 'mephi-batch-' + digest([dataset, [(s['source_id'], s['sha256']) for s in snapshots]])[:24]
    add('import_batches', id=batch, dataset_sha256=digest(dataset), adapter_version=ADAPTER_VERSION, is_synthetic=0)
    snapshot_ids = {}
    for s in snapshots:
        sid = 'snapshot-' + digest([s['source_id'], s['sha256']])[:32]
        snapshot_ids[s['sha256']] = sid
        add('source_records', id=s['source_id'], institution_id='mephi', url=s['url'],
            document_type='historical_table' if s['source_id']=='mephi-history' else 'official_catalog_or_document',
            years_json=canonical(list(range(2015,2026)) if s['source_id']=='mephi-history' else [2026]),
            last_checked_at=s['retrieved_at'], extraction_method=s['retrieval_method'],
            parsing_status='success' if s['source_id'] in {'mephi-history','mephi-programs','mephi-moscow','mephi-fields'} else 'not_started',
            reliability='official_unverified', original_url=s['url'],
            notes='Extraction evidence does not establish a competition group or validate admission rules.')
        add('source_snapshots', id=sid, source_record_id=s['source_id'], import_batch_id=batch,
            captured_at=s['retrieved_at'], sha256=s['sha256'], artifact_path=s['path'])
    add('campuses', id='mephi-moscow', institution_id='mephi', name='НИЯУ МИФИ (Москва)', city='Москва')
    for year in range(2015,2027):
        sql.append(f'INSERT INTO admission_years(year) VALUES ({year}) ON CONFLICT(year) DO NOTHING;')
        add('admission_campaigns', id=f'mephi-moscow-{year}', institution_id='mephi', campus_id='mephi-moscow', year=year)
    all_codes = {r['official_code'] for r in dataset['history']['records'] if r['official_code']}
    all_codes |= {r['official_code'] for r in dataset['catalog']['records']}
    all_codes |= {r['official_code'] for r in dataset['official_fields']}
    all_codes |= {c for r in dataset['seats']['records'] for c in r['codes']}
    for code in sorted(all_codes):
        add('study_fields', id=code, official_code=code, degree='bachelor' if code[3:5]=='03' else 'specialist')
    for field in dataset['official_fields']:
        sha = field['provenance']['snapshot_sha256']
        add('campaign_field_offerings', id='mephi-2026-' + field['official_code'] + '-' + digest([sha,ADAPTER_VERSION])[:12],
            campaign_id='mephi-moscow-2026', field_id=field['official_code'],
            official_name=field['official_name'], study_form='full_time', adapter_version=ADAPTER_VERSION,
            source_snapshot_id=snapshot_ids[sha], evidence_json=canonical(field))
    for p in dataset['catalog']['records']:
        tag_to_legacy = {'Mathematics':'mathematics','Computer Science':'computer_science','Artificial Intelligence / ML':'data_ai','Engineering':'engineering'}
        classification = next((tag_to_legacy[tag] for tag in p['tags'] if tag in tag_to_legacy), 'adjacent')
        add('programs', id=p['id'], institution_id='mephi', classification=classification,
            classification_reason='Heuristic tags; admission campaign/profile and identity changes require review.', is_synthetic=0)
        pid, sha = p['id'], p['provenance']['snapshot_sha256']
        version_id = pid + '-2026-' + digest([sha,ADAPTER_VERSION])[:12]
        # Dynamic revision makes a changed snapshot append a new version without rewriting history.
        fields = 'id,program_id,admission_year,revision,name,official_code,campus,degree,study_form,verification_status,source_snapshot_id,supersedes_id,campus_id,field_id,catalog_metadata_json'
        previous = f"SELECT id FROM program_versions WHERE program_id={literal(pid)} AND admission_year=2026 ORDER BY revision DESC LIMIT 1"
        revision = f"SELECT coalesce(max(revision),0)+1 FROM program_versions WHERE program_id={literal(pid)} AND admission_year=2026"
        values = [literal(version_id), literal(pid), '2026', f'({revision})', literal(p['name']), literal(p['official_code']),
                  literal('Москва'), literal(p['degree']), literal('full_time'), literal('unverified'), literal(snapshot_ids[sha]),
                  f'({previous})', literal('mephi-moscow'), literal(p['official_code']), literal(canonical(p))]
        sql.append(f"INSERT INTO program_versions({fields}) SELECT {','.join(values)} WHERE NOT EXISTS (SELECT 1 FROM program_versions WHERE id={literal(version_id)});")
    for a in dataset['seats']['records']:
        sid = snapshot_ids[a['provenance']['snapshot_sha256']]
        gid, condition = a['id'] + '-candidate', a['id'] + '-condition'
        add('competition_groups', id=gid, campaign_id='mephi-moscow-2026', official_key=None,
            label=a['scope_label'], resolution_status='candidate', source_snapshot_id=sid)
        add('competition_conditions', id=condition, group_id=gid,
            category='budget_total' if a['funding']=='federal_budget_total' else 'paid',
            study_form='full_time', applicant_basis=a['applicant_basis'], rules_json='{}', source_snapshot_id=sid)
        add('seat_allocations', id=a['id'], campaign_id='mephi-moscow-2026', condition_id=condition,
            source_row_key=a['row_key'], funding=a['funding'], places=a['places'], scope_label=a['scope_label'],
            source_snapshot_id=sid, adapter_version=ADAPTER_VERSION, evidence_json=canonical(a))
        for code in a['codes']:
            sql.append(insert_sql('seat_allocation_members', dict(allocation_id=a['id'], field_id=code), key='allocation_id,field_id'))
            add('competition_group_members', id=gid + '-' + code, group_id=gid, field_id=code,
                program_version_id=None, evidence_status='allocation_scope_only')
    for r in dataset['history']['records']:
        add('admission_observations', id=r['id'], row_key=r['row_key'], campaign_id=f"mephi-moscow-{r['year']}",
            field_id=r['official_code'], group_id=None, group_mapping_status='unresolved',
            official_code_raw=r['official_code'], official_name=r['official_name'], division=r['division'],
            competition_category=r['competition_category'], threshold_status=r['threshold_status'], cutoff=r['cutoff'],
            mean_ege_score=r['mean_ege_score'], mean_entrance_total=r['mean_entrance_total'],
            source_snapshot_id=snapshot_ids[r['provenance']['snapshot_sha256']], adapter_version=ADAPTER_VERSION, payload_json=canonical(r))
    return sql


def import_dataset(connection, dataset, store):
    before = connection.total_changes
    try:
        connection.execute('BEGIN')
        for statement in import_plan(dataset, store):
            connection.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return connection.total_changes - before


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, default=OUT/'dataset.json', help='Also accepts a manually reviewed normalized dataset with captured source evidence.')
    parser.add_argument('--sqlite', type=Path)
    parser.add_argument('--export-sql', type=Path)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text())
    store = SnapshotStore()
    if args.export_sql:
        args.export_sql.parent.mkdir(parents=True, exist_ok=True)
        args.export_sql.write_text('-- Real official MEPhI aggregates. Run after all migrations. Idempotent by source/row identity.\n' +
                                  '\n'.join(import_plan(dataset, store))+'\n')
        print('D1 import SQL exported:', args.export_sql)
    if args.sqlite:
        connection = sqlite3.connect(args.sqlite)
        connection.execute('PRAGMA foreign_keys=ON')
        changes = import_dataset(connection, dataset, store)
        print('Imported SQLite row changes:', changes)
        connection.close()
    if not args.export_sql and not args.sqlite:
        parser.error('Choose --sqlite or --export-sql')


if __name__ == '__main__':
    main()
