"""Append annual score rules, preserving all preceding source datasets."""
import argparse,json
from pathlib import Path
from .academic_rules import OUT,INPUTS,VERSION,build
from .import_history import import_plan as history_plan
from .history_dataset import OUT as HISTORY_OUT
from .import_mephi import insert_sql
from .sources import canonical,digest
from .validate import require


def import_plan(dataset):
    require(dataset==build(write=False),'academic_rules_do_not_replay')
    statements=history_plan(json.loads((HISTORY_OUT/'dataset.json').read_text()))
    def add(table,**row):statements.append(insert_sql(table,row))
    batch='rules-batch-'+digest(dataset)[:24]
    add('import_batches',id=batch,dataset_sha256=digest(dataset),adapter_version=VERSION,is_synthetic=0)
    snapshots={}
    for b in json.loads((INPUTS/'mephi-2026.json').read_text()):
        s=b['source'];sid='snapshot-'+digest([s['source_id'],s['sha256']])[:32];snapshots[s['source_id']]=sid
        add('source_records',id=s['source_id'],institution_id='mephi',url=s['url'],document_type='annual_academic_rules',
            years_json='[2026]',last_checked_at=s['retrieved_at'],extraction_method=s['retrieval_method'],
            parsing_status='partial',reliability='official_unverified',original_url=s['url'],
            notes='Documented school EGE score constraints only; BVI, quotas, ties require separate verification.')
        add('source_snapshots',id=sid,source_record_id=s['source_id'],import_batch_id=batch,captured_at=s['retrieved_at'],
            sha256=s['sha256'],artifact_path=s['path'])
    for r in dataset['rules']:
        add('academic_rule_versions',id=r['id'],institution_id=r['institution_id'],campus_id=r['campus_id'],year=r['year'],
            field_id=r['official_code'],category=r['category'],applicant_basis=r['applicant_basis'],
            source_snapshot_id=snapshots[r['evidence']['exams']['source_id']],adapter_version=VERSION,payload_json=canonical(r))
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
    d=json.loads((OUT/'dataset.json').read_text());a.export_sql.write_text('-- Annual academic rules, all prior stages included.\n'+'\n'.join(import_plan(d))+'\n')
    print('Annual school EGE rule versions exported:',len(d['rules']))
