"""Metrics only; a metric implementation does not establish empirical validation."""
import math


def calibration_metrics(predictions,outcomes,bins=10):
    if not predictions or len(predictions)!=len(outcomes) or type(bins) is not int or not 1<=bins<=100:raise ValueError('invalid_calibration_sample')
    if any(not math.isfinite(p) or not 0<=p<=1 for p in predictions) or any(type(y) is not int or y not in (0,1) for y in outcomes):raise ValueError('invalid_probability_or_outcome')
    n=len(outcomes);reliability=[];ece=0
    for b in range(bins):
        members=[(p,y) for p,y in zip(predictions,outcomes) if min(int(p*bins),bins-1)==b]
        if not members:continue
        confidence=sum(p for p,_ in members)/len(members);frequency=sum(y for _,y in members)/len(members)
        ece+=len(members)/n*abs(confidence-frequency)
        reliability.append(dict(lower=b/bins,upper=(b+1)/bins,n=len(members),mean_prediction=confidence,observed_frequency=frequency))
    eps=1e-15
    return dict(n=n,brier=sum((p-y)**2 for p,y in zip(predictions,outcomes))/n,
        log_loss=-sum(y*math.log(max(eps,min(1-eps,p)))+(1-y)*math.log(max(eps,min(1-eps,1-p))) for p,y in zip(predictions,outcomes))/n,
        expected_calibration_error=ece,reliability=reliability,
        warning='Calibration depends on label quality, sampling and temporal validation; ECE depends on bins.')
