"""Recompute canonical and public artifacts offline without modifying the worktree."""
import json,math
from .validate import ROOT,require
from .catalog_pipeline import build as catalog,public_index as catalog_public
from .history_dataset import build as history,public_index as history_public
from .academic_rules import build as rules,public_rules
from .threshold_baseline import build as baseline,CONFIG as BASELINE_CONFIG
from .model_readiness import build as readiness
from .competition_research import build_research
from .sources import SnapshotStore
from .audit import render


def load(path):return json.loads((ROOT/path).read_text())


def equal(path,expected):require(load(path)==expected,'stale_artifact:'+path)


def verify_growth_config(c):
    require(c['status']=='uncalibrated_hypotheses' and c['admission_probability_enabled'] is False,'growth_must_remain_hypothetical')
    require(c['score_bands']==[0,60,85,100],'growth_band_contract')
    for rates in c['subject_parameters'].values():
        require(len(rates)==3 and all(math.isfinite(x) and x>=0 for x in rates) and rates==sorted(rates,reverse=True),'invalid_growth_rates')
    require(abs(sum(n['weight'] for n in c['latent_nodes'])-1)<1e-9,'growth_mass')
    require(all(math.isfinite(n['z']) and 0<=n['weight']<=1 for n in c['latent_nodes']),'growth_nodes')
    require([n['z'] for n in c['latent_nodes']]==sorted(n['z'] for n in c['latent_nodes']),'growth_node_order')
    require(c['target_role']=='diagnostics_only_never_used_in_growth','growth_target_role')
    require(c['reference_hours_per_week']>0 and 0<c['intensity_exponent']<=1,'growth_intensity')


def main():
    equal('data/normalized/mephi/competition_research.json',build_research(load('data/normalized/mephi/dataset.json'),SnapshotStore()))
    c=catalog(write=False);h=history(write=False);r=rules(write=False);b=baseline(write=False)
    equal('data/normalized/catalog_v1/dataset.json',c);equal('data/normalized/catalog_v1/public_index.json',catalog_public(c))
    equal('data/normalized/history_v1/dataset.json',h);equal('data/normalized/history_v1/public_index.json',history_public(h))
    equal('data/normalized/rules_v1/dataset.json',r);equal('data/normalized/rules_v1/public_rules.json',public_rules(r))
    equal('data/normalized/threshold_baseline_v1/evaluation.json',b)
    cfg=json.loads(BASELINE_CONFIG.read_text())
    equal('data/normalized/threshold_baseline_v1/public_index.json',dict(version=b['version'],year=cfg['forecast_year'],metrics=b['metrics'],probability_enabled=False,records=b['current']))
    equal('data/normalized/admission_readiness.json',readiness(write=False))
    verify_growth_config(load('config/progress.scenarios.v1.json'))
    expected=render(load('data/source_registry.json'),load('data/normalized/catalog.json'))
    require((ROOT/'DATA_AUDIT.md').read_text()==expected,'stale_data_audit')
    print('PASS offline canonical/public artifact replay; probability gate remains closed.')


if __name__=='__main__':main()
