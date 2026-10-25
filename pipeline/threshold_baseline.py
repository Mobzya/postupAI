"""Frozen simple published-threshold baselines with rolling temporal evaluation."""
import argparse,json,math,statistics
from collections import defaultdict,Counter
from .sources import digest,write_json
from .validate import ROOT,require

OUT=ROOT/'data/normalized/threshold_baseline_v1'
CONFIG=ROOT/'config/threshold.baseline.v1.json'


def series_key(row):
    return tuple(row[k] for k in ('institution_id','program_url','name','official_code','category','unit'))


def select_series(rows):
    series=defaultdict(list);exclusions=Counter()
    for r in rows:
        if r['metric']!='cutoff' or r['status']!='numeric' or r['unit']!='competition_points':
            exclusions['metric_status_or_unit']+=1;continue
        if not r['program_url'] or not r['official_code']:
            exclusions['missing_explicit_program_url_or_code']+=1;continue
        series[series_key(r)].append(r)
    return series,dict(exclusions)


def predict_series(rows,year,config):
    # Ambiguous duplicate scopes in a training year stop the chain, never get averaged.
    byyear=defaultdict(list)
    for r in rows:
        if r['year']<year:byyear[r['year']].append(r)
    train=[]
    for y in range(year-1,year-1-config['max_history_years'],-1):
        if len(byyear[y])!=1:break
        train.append(byyear[y][0])
    if len(train)<config['minimum_history_years']:return None
    return dict(last_year=train[0]['value'],median_last_three=statistics.median(r['value'] for r in train),
        training_ids=[r['id'] for r in train],training_years=[r['year'] for r in train],
        training_values=[r['value'] for r in train])


def metrics(rows,method):
    if not rows:return dict(n=0,mae=None,rmse=None,bias=None,median_absolute_error=None)
    errors=[r[method]-r['actual'] for r in rows]
    return dict(n=len(rows),mae=statistics.mean(abs(e) for e in errors),
        rmse=math.sqrt(statistics.mean(e*e for e in errors)),bias=statistics.mean(errors),
        median_absolute_error=statistics.median(abs(e) for e in errors))


def evaluate(rows,config):
    series,excluded=select_series(rows);predictions=[];skipped=Counter();current=[]
    for key,records in sorted(series.items()):
        sid='threshold-series-'+digest(key)[:20]
        byyear=defaultdict(list)
        for row in records:byyear[row['year']].append(row)
        for year in config['evaluation_years']:
            target=byyear.get(year,[])
            if len(target)!=1:
                skipped['missing_or_ambiguous_target']+=1;continue
            pred=predict_series(records,year,config)
            if pred is None:skipped['insufficient_consecutive_history']+=1;continue
            r=target[0]
            predictions.append(dict(series_id=sid,institution_id=r['institution_id'],name=r['name'],
                year=year,category=r['category'],actual=r['value'],target_id=r['id'],**pred))
        pred=predict_series(records,config['forecast_year'],config)
        if pred:
            latest=max((r for r in records if r['year']<config['forecast_year']),key=lambda r:r['year'])
            current.append(dict(id=sid,institution_id=key[0],program_url=key[1],name=key[2],official_code=key[3],category=key[4],
                year=config['forecast_year'],estimate=pred[config['primary_method']],last_published=latest['value'],
                last_published_year=latest['year'],source_url=latest['provenance']['url'],**pred))
    methods=['last_year','median_last_three']
    return dict(series_count=len(series),input_observations=len(rows),eligible_observations=sum(len(v) for v in series.values()),
        excluded=excluded,skipped=dict(skipped),evaluation=predictions,current=current,
        metrics={m:metrics(predictions,m) for m in methods},
        metrics_by_year={str(y):{m:metrics([r for r in predictions if r['year']==y],m) for m in methods} for y in config['evaluation_years']},
        metrics_by_category={c:{m:metrics([r for r in predictions if r['category']==c],m) for m in methods} for c in sorted({r['category'] for r in predictions})})


def build(write=True):
    rows=json.loads((ROOT/'data/normalized/history_v1/dataset.json').read_text())['records'];config=json.loads(CONFIG.read_text())
    result=dict(version=config['version'],status=config['status'],dataset_sha256=digest(rows),config_sha256=digest(config),
        code_sha256=digest((ROOT/'pipeline/threshold_baseline.py').read_bytes()),probability_enabled=False,
        comparability_status='textual_series_not_verified_competition',**evaluate(rows,config))
    for r in result['evaluation']:
        require(all(y<r['year'] for y in r['training_years']),'temporal_leakage')
        require(r['target_id'] not in r['training_ids'],'target_leakage')
    if write:
        write_json(OUT/'evaluation.json',result)
        write_json(OUT/'public_index.json',dict(version=result['version'],year=config['forecast_year'],metrics=result['metrics'],
            probability_enabled=False,records=result['current']))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['build','validate']);a=p.parse_args()
    d=build(write=a.command=='build')
    if a.command=='validate':require(d==json.loads((OUT/'evaluation.json').read_text()),'threshold_evaluation_does_not_replay')
    print(json.dumps(dict(series=d['series_count'],holdout_predictions=len(d['evaluation']),future_series=len(d['current']),metrics=d['metrics'])))
