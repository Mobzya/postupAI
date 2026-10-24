"""Actual local D1 catalog replay. No remote database or real user profiles."""
import json
from pathlib import Path
import subprocess,sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    path=ROOT/'.wrangler/catalog-import.sql';path.parent.mkdir(exist_ok=True)
    subprocess.run([sys.executable,'-m','pipeline.import_catalog','--export-sql',str(path)],cwd=ROOT,check=True)
    flags=['--local','--persist-to','.wrangler/catalog-demo']
    def run(args,as_json=False):
        p=subprocess.run([str(ROOT/'node_modules/.bin/wrangler'),*args],cwd=ROOT,capture_output=True,text=True,timeout=180)
        if p.returncode:raise RuntimeError('Local catalog D1 verification failed; command output suppressed.')
        return json.loads(p.stdout) if as_json else None
    run(['d1','migrations','apply','ballnik',*flags])
    sql="SELECT (SELECT count(*) FROM programs) legacy_programs,(SELECT count(*) FROM admission_observations) historical_rows,(SELECT count(*) FROM competition_group_assessments) group_assessments,(SELECT count(*) FROM catalog_observations) catalog_observations,(SELECT count(*) FROM user_profiles) profiles;"
    counts=[]
    for _ in range(2):
        result=run(['d1','execute','ballnik',*flags,'--file',str(path),'--json'],True)
        assert all(r['success'] for r in result)
        counts.append(run(['d1','execute','ballnik',*flags,'--command',sql,'--json'],True)[0]['results'][0])
    expected_count=len(json.loads((ROOT/'data/normalized/catalog_v1/dataset.json').read_text())['records'])
    assert counts[0]==counts[1]==dict(legacy_programs=82,historical_rows=286,group_assessments=39,catalog_observations=expected_count,profiles=0)
    fk=run(['d1','execute','ballnik',*flags,'--command','PRAGMA foreign_key_check;','--json'],True)
    assert all(not r['results'] for r in fk)
    (ROOT/'docs/stage_1c_local_verification.json').write_text(json.dumps(dict(first=counts[0],second=counts[1],foreign_key_violations=0,public_deployment=False),indent=2)+'\n')
    print('PASS local D1 catalog:',json.dumps(counts[1]))


if __name__=='__main__':main()
