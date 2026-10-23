"""Reproduce actual local D1 import twice, with concise output and no credentials."""
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable,'-m','pipeline.import_mephi','--export-sql','data/normalized/mephi/import.sql'],cwd=ROOT,check=True)
    def command(arguments, expect_json=False):
        result=subprocess.run(['npx','wrangler',*arguments],cwd=ROOT,capture_output=True,text=True,timeout=120)
        if result.returncode:
            raise RuntimeError('Local D1 command failed: '+result.stderr[-600:])
        return json.loads(result.stdout) if expect_json else None
    persist=['--local','--persist-to','.wrangler/mephi-demo']
    command(['d1','migrations','apply','ballnik',*persist])
    query="SELECT (SELECT count(*) FROM programs) AS profiles,(SELECT count(*) FROM program_versions) AS profile_versions,(SELECT count(*) FROM campaign_field_offerings) AS campaign_fields,(SELECT count(*) FROM admission_observations) AS history_rows,(SELECT count(*) FROM seat_allocations) AS seat_allocations,(SELECT count(*) FROM model_versions) AS models;"
    def counts():
        return command(['d1','execute','ballnik',*persist,'--command',query,'--json'],True)[0]['results'][0]
    before=counts()
    executions=[]
    for _ in range(2):
        results=command(['d1','execute','ballnik',*persist,'--file','data/normalized/mephi/import.sql','--json'],True)
        assert all(r['success'] for r in results)
        executions.append(counts())
    expected=dict(profiles=82,profile_versions=82,campaign_fields=31,history_rows=286,seat_allocations=39,models=0)
    assert executions[0]==executions[1]==expected
    report=dict(runtime='actual Wrangler/workerd local D1',persist_to='.wrangler/mephi-demo',
                before=before,after_first=executions[0],after_second=executions[1],
                repeated_import_counts_equal=True,public_deployment=False)
    path=ROOT/'docs/local_d1_verification.json';path.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS local D1:',json.dumps(executions[1]),'; repeat import unchanged')


if __name__=='__main__':main()
