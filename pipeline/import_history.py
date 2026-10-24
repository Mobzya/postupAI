"""Full preceding-stage import plus versioned historical source observations."""
import argparse,json
from pathlib import Path
from .history_dataset import OUT,INPUTS,VERSION,build
from .import_catalog import import_plan as catalog_plan
from .catalog_pipeline import OUT as CATALOG_OUT
from .import_mephi import insert_sql
from .sources import canonical,digest,SnapshotStore
from .validate import ROOT,require


def import_plan(dataset):
    require(dataset==build(write=False),'historical_facts_do_not_replay')
    statements=catalog_plan(json.loads((CATALOG_OUT/'dataset.json').read_text()))
    def add(table,**row):statements.append(insert_sql(table,row))
    batch='history-batch-'+digest(dataset)[:24]
    add('import_batches',id=batch,dataset_sha256=digest(dataset),adapter_version=VERSION,is_synthetic=0)
    snapshots={}
    for s in SnapshotStore().manifest['snapshots']:
        snapshots[(s['source_id'],s['sha256'])]='snapshot-'+digest([s['source_id'],s['sha256']])[:32]
    for filename in json.loads((INPUTS/'manifest.json').read_text()):
        s=json.loads((ROOT/filename).read_text())['source'];sid='snapshot-'+digest([s['source_id'],s['sha256']])[:32]
        snapshots[(s['source_id'],s['sha256'])]=sid
        years=sorted({r['year'] for r in dataset['records'] if r['provenance']['source_id']==s['source_id']})
        add('source_records',id=s['source_id'],institution_id=s['institution_id'],url=s['url'],
            document_type='historical_aggregates',years_json=canonical(years),last_checked_at=s['retrieved_at'],
            extraction_method=s['retrieval_method'],parsing_status='partial',reliability='official_unverified',
            original_url=s['url'],notes='Published source aggregates; unit/category/scope retained; probability calibration unavailable.')
        add('source_snapshots',id=sid,source_record_id=s['source_id'],import_batch_id=batch,captured_at=s['retrieved_at'],
            sha256=s['sha256'],artifact_path=s['path'])
    for r in dataset['records']:
        statements.append(f"INSERT INTO admission_years(year) VALUES ({r['year']}) ON CONFLICT(year) DO NOTHING;")
        p=r['provenance']
        add('historical_source_observations',id=r['id'],institution_id=r['institution_id'],year=r['year'],
            name=r['name'],official_code=r['official_code'],metric=r['metric'],unit=r['unit'],category=r['category'],
            status=r['status'],value=r['value'],source_snapshot_id=snapshots[(p['source_id'],p['parent_sha256'])],
            parent_observation_id=r['parent_observation_id'],adapter_version=VERSION,payload_json=canonical(r))
    return statements


def import_dataset(db,dataset):
    before=db.total_changes
    try:
        db.execute('BEGIN')
        for s in import_plan(dataset):db.execute(s)
        db.commit()
    except Exception:db.rollback();raise
    return db.total_changes-before


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--export-sql',type=Path,required=True);a=p.parse_args()
    a.export_sql.parent.mkdir(parents=True,exist_ok=True)
    d=json.loads((OUT/'dataset.json').read_text());a.export_sql.write_text('-- Historical source observations; all prior stages included.\n'+'\n'.join(import_plan(d))+'\n')
    print('Historical source observations exported:',len(d['records']))
