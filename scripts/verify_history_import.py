"""Real local D1 historical replay with previous stages and repeated import."""
import json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    path=ROOT/'.wrangler/history-import.sql';path.parent.mkdir(exist_ok=True);(ROOT/'artifacts').mkdir(exist_ok=True)
    subprocess.run([sys.executable,'-m','pipeline.import_history','--export-sql',str(path)],cwd=ROOT,check=True)
    flags=['--local','--persist-to','.wrangler/history-demo']
    def run(args,as_json=False):
        p=subprocess.run([str(ROOT/'node_modules/.bin/wrangler'),*args],cwd=ROOT,capture_output=True,text=True,timeout=180)
        if p.returncode:raise RuntimeError('Local historical D1 verification failed; output suppressed.')
        return json.loads(p.stdout) if as_json else None
    run(['d1','migrations','apply','ballnik',*flags])
    query="SELECT (SELECT count(*) FROM admission_observations) original_history,(SELECT count(*) FROM catalog_observations) catalog_observations,(SELECT count(*) FROM historical_source_observations) historical_source_observations,(SELECT count(*) FROM user_profiles) profiles;"
    counts=[]
    for _ in range(2):
        result=run(['d1','execute','ballnik',*flags,'--file',str(path),'--json'],True)
        assert all(r['success'] for r in result)
        counts.append(run(['d1','execute','ballnik',*flags,'--command',query,'--json'],True)[0]['results'][0])
    n=len(json.loads((ROOT/'data/normalized/history_v1/dataset.json').read_text())['records'])
    assert counts[0]==counts[1]==dict(original_history=286,catalog_observations=len(json.loads((ROOT/'data/normalized/catalog_v1/dataset.json').read_text())['records']),historical_source_observations=n,profiles=0)
    fk=run(['d1','execute','ballnik',*flags,'--command','PRAGMA foreign_key_check;','--json'],True)
    assert all(not r['results'] for r in fk)
    (ROOT/'artifacts/history_import_verification.json').write_text(json.dumps(dict(first=counts[0],second=counts[1],foreign_key_violations=0,public_deployment=False),indent=2)+'\n')
    print('PASS historical D1:',json.dumps(counts[1]))


if __name__=='__main__':main()
