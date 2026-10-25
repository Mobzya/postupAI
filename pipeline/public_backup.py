"""Back up a fresh public-data-only SQLite reconstruction; never copy user databases."""
import argparse,hashlib,json,sqlite3,subprocess
from datetime import datetime,timezone
from pathlib import Path
from .validate import ROOT,require
from .sources import write_json
from .import_rules import import_dataset

CORE=['programs','program_versions','admission_observations','competition_group_assessments',
      'catalog_observations','historical_source_observations','academic_rule_versions']
USER=['user_profiles','user_score_history','user_achievements','saved_programs','forecast_results','telegram_updates']


def file_sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(db):
    require(db.execute('PRAGMA integrity_check').fetchall()==[('ok',)],'backup_integrity_failed')
    require(db.execute('PRAGMA foreign_key_check').fetchall()==[],'backup_fk_failed')
    counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in CORE+USER}
    require(all(counts[t]==0 for t in USER),'backup_contains_user_data')
    return counts


def create_backup(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    path=directory/'public-data.sqlite';db=sqlite3.connect(path)
    try:
        db.execute('PRAGMA foreign_keys=ON');migrations=sorted((ROOT/'migrations').glob('*.sql'))
        for p in migrations:db.executescript(p.read_text())
        import_dataset(db,json.loads((ROOT/'data/normalized/rules_v1/dataset.json').read_text()))
        counts=inspect(db)
    finally:db.close()
    manifest=dict(version='public-only-backup-v1',created_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        file='public-data.sqlite',sha256=file_sha(path),counts=counts,contains_user_data=False,
        code_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        migration_hashes={p.name:file_sha(p) for p in migrations},
        dataset_hashes={name:file_sha(ROOT/'data/normalized'/name/'dataset.json') for name in ['mephi','catalog_v1','history_v1','rules_v1']},
        limitation='Public normalized reconstruction, not a production D1/user backup. Source snapshot files are separate.')
    write_json(directory/'manifest.json',manifest)
    return manifest


def restore_backup(directory,destination):
    directory=Path(directory);destination=Path(destination)
    require(not destination.exists(),'restore_destination_already_exists')
    manifest=json.loads((directory/'manifest.json').read_text())
    require(manifest['version']=='public-only-backup-v1' and manifest['file']=='public-data.sqlite','unsupported_backup')
    path=directory/'public-data.sqlite';require(file_sha(path)==manifest['sha256'],'backup_hash_mismatch')
    source=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        require(inspect(source)==manifest['counts'],'backup_counts_mismatch')
        destination.parent.mkdir(parents=True,exist_ok=True);target=sqlite3.connect(destination)
        try:
            source.backup(target);counts=inspect(target)
            require(counts==manifest['counts'],'restored_counts_mismatch')
        finally:target.close()
    finally:source.close()
    return dict(status='restored_and_verified',counts=counts,contains_user_data=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['create','restore']);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--destination',type=Path);a=p.parse_args()
    if a.command=='create':r=create_backup(a.directory)
    else:
        if a.destination is None:p.error('restore requires --destination')
        r=restore_backup(a.directory,a.destination)
    print(json.dumps(dict(status=r.get('status','created'),counts=r['counts'],contains_user_data=False)))
