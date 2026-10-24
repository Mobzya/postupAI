"""Append-only catalog observation import, sharing existing institution/source tables."""
import argparse,json
from pathlib import Path
from .catalog_pipeline import OUT,INPUTS,VERSION,build,validate
from .import_mephi import insert_sql
from .competition_research import research_plan,OUTPUT as RESEARCH_OUTPUT
from .sources import canonical,digest,SnapshotStore
from .validate import ROOT,require


def import_plan(dataset):
    validate(dataset);require(dataset==build(write=False),'catalog_facts_do_not_replay')
    base=json.loads((ROOT/'data/normalized/mephi/dataset.json').read_text())
    statements=research_plan(json.loads(RESEARCH_OUTPUT.read_text()),base,SnapshotStore())
    def add(table,**row):statements.append(insert_sql(table,row))
    batch='catalog-batch-'+digest(dataset)[:24]
    add('import_batches',id=batch,dataset_sha256=digest(dataset),adapter_version=VERSION,is_synthetic=0)
    snapshots={}
    for filename in json.loads((INPUTS/'manifest.json').read_text()):
        s=json.loads((ROOT/filename).read_text())['source'];sid='snapshot-'+digest([s['source_id'],s['sha256']])[:32]
        snapshots[s['source_id']]=sid
        years=sorted({r['campaign_year'] for r in dataset['records'] if r['provenance']['source_id']==s['source_id'] and r['campaign_year'] is not None})
        add('source_records',id=s['source_id'],institution_id=s['institution_id'],url=s['url'],
            document_type='catalog_observations',years_json=canonical(years),last_checked_at=s['retrieved_at'],
            extraction_method=s['retrieval_method'],parsing_status='partial',reliability='official_unverified',
            original_url=s['url'],notes='Source excerpt preserved; campaign and program completeness not established.')
        add('source_snapshots',id=sid,source_record_id=s['source_id'],import_batch_id=batch,captured_at=s['retrieved_at'],
            sha256=s['sha256'],artifact_path=s['path'])
    for row in dataset['records']:
        if row['campaign_year'] is not None:
            statements.append(f"INSERT INTO admission_years(year) VALUES ({row['campaign_year']}) ON CONFLICT(year) DO NOTHING;")
        add('catalog_observations',id=row['id'],institution_id=row['institution_id'],name=row['name'],campus=row['campus'],
            degree=row['degree'],official_code=row['official_code'],campaign_year=row['campaign_year'],kind=row['kind'],
            program_url=row['program_url'],legacy_program_id=row.get('legacy_program_id'),
            source_snapshot_id=snapshots[row['provenance']['source_id']],adapter_version=VERSION,payload_json=canonical(row))
    return statements


def import_dataset(connection,dataset):
    before=connection.total_changes
    try:
        connection.execute('BEGIN')
        for statement in import_plan(dataset):connection.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback();raise
    return connection.total_changes-before


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--export-sql',type=Path,required=True);args=p.parse_args()
    dataset=json.loads((OUT/'dataset.json').read_text());args.export_sql.parent.mkdir(parents=True,exist_ok=True)
    args.export_sql.write_text('-- Public catalog observations; apply all migrations first.\n'+'\n'.join(import_plan(dataset))+'\n')
    print('Catalog SQL exported; observations:',len(dataset['records']))
