"""Real local workerd/D1: additive migration, repeat import, no remote operations."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    export=ROOT/'.wrangler/competition_research.sql'; export.parent.mkdir(exist_ok=True)
    subprocess.run([sys.executable,'-m','pipeline.competition_research','export-sql','--output',str(export)],cwd=ROOT,check=True)
    persist=['--local','--persist-to','.wrangler/mephi-demo']
    def run(args,as_json=False):
        p=subprocess.run(['npx','wrangler',*args],cwd=ROOT,capture_output=True,text=True,timeout=120)
        if p.returncode: raise RuntimeError('Local D1 check failed: '+p.stderr[-600:])
        return json.loads(p.stdout) if as_json else None
    run(['d1','migrations','apply','ballnik',*persist])
    query="SELECT (SELECT count(*) FROM programs) profiles,(SELECT count(*) FROM admission_observations) history_rows,(SELECT count(*) FROM competition_group_assessments) group_assessments,(SELECT count(*) FROM historical_group_assessments) history_assessments,(SELECT count(*) FROM competition_group_assessments WHERE status='confirmed') confirmed,(SELECT count(*) FROM competition_group_assessments WHERE status='inferred') inferred,(SELECT count(*) FROM model_versions) models;"
    counts=[]
    for _ in range(2):
        result=run(['d1','execute','ballnik',*persist,'--file',str(export),'--json'],True)
        assert all(r['success'] for r in result)
        counts.append(run(['d1','execute','ballnik',*persist,'--command',query,'--json'],True)[0]['results'][0])
    assert counts[0]==counts[1]==dict(profiles=82,history_rows=286,group_assessments=39,history_assessments=286,confirmed=0,inferred=0,models=0)
    foreign_keys=run(['d1','execute','ballnik',*persist,'--command','PRAGMA foreign_key_check;','--json'],True)
    assert all(not r['results'] for r in foreign_keys)
    report=dict(runtime='actual Wrangler/workerd local D1',after_first=counts[0],after_second=counts[1],repeated_import_counts_equal=True,foreign_key_violations=0,public_deployment=False)
    (ROOT/'docs/stage_1b_local_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS stage 1B local D1:',json.dumps(counts[1]))


if __name__=='__main__':main()
