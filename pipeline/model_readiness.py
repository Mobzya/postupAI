"""Source-backed readiness report; laboratory simulations never unlock predictions."""
import argparse,json
from .validate import ROOT,require
from .sources import digest,write_json

OUT=ROOT/'data/normalized/admission_readiness.json'


def build(write=True):
    research=json.loads((ROOT/'data/normalized/mephi/competition_research.json').read_text())
    history=json.loads((ROOT/'data/normalized/history_v1/ml_readiness.json').read_text())
    baseline=json.loads((ROOT/'data/normalized/threshold_baseline_v1/evaluation.json').read_text())
    groups=sum(r['status']=='confirmed' for r in research['group_assessments'])
    d=dict(version='admission-readiness-v1',status='blocked',probability_enabled=False,
        confirmed_competition_groups=groups,threshold_holdout_predictions=len(baseline['evaluation']),
        real_admission_backtest_available=False,real_calibration_available=False,
        validated_probability_artifact=None,complete_annual_rules=False,
        laboratory_simulator='synthetic_only_offline',
        source_hashes=dict(competition_review=digest(research),history_readiness=digest(history),threshold_evaluation=digest(baseline)),
        blockers=['Same-year verified competition populations and final enrollment distributions missing.',
            'BVI, quotas, ties, actual preference/consent procedure and annual rules incomplete.',
            'No temporal individual-admission backtest or empirically calibrated artifact.',
            'Synthetic simulator results and threshold MAE cannot authorize real admission probabilities.'])
    if write:write_json(OUT,d)
    return d


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['build','validate']);a=p.parse_args();d=build(write=a.command=='build')
    if a.command=='validate':require(d==json.loads(OUT.read_text()),'admission_readiness_not_reproducible')
    print(json.dumps(d))
