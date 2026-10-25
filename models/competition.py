"""Synthetic-only competition laboratory; never called inside a Worker."""
import argparse,json,math,random
from collections import deque,Counter
from dataclasses import dataclass
from pathlib import Path
from pipeline.sources import digest,write_json


@dataclass(frozen=True)
class Program:
    key:str
    seats:int
    minimum:float=0


@dataclass(frozen=True)
class Entrant:
    scores:dict[str,float]
    preferences:tuple[str,...]
    tie_priority:float


def deferred_acceptance(programs,entrants):
    """Applicant-proposing stable matching for one synthetic general-budget category.

    Each entrant holds at most one seat. Tie priorities are supplied laboratory
    assumptions, not a substitute for the university's annual ordering criteria.
    Entrant array positions are transient simulation indices, not real identifiers.
    """
    bykey={p.key:p for p in programs}
    if len(bykey)!=len(programs) or not bykey:raise ValueError('duplicate_or_empty_programs')
    for p in programs:
        if not p.key or type(p.seats) is not int or p.seats<0 or not math.isfinite(p.minimum) or p.minimum<0:raise ValueError('invalid_program')
    preferences=[]
    for e in entrants:
        if len(e.preferences)!=len(set(e.preferences)) or any(k not in bykey for k in e.preferences):raise ValueError('invalid_preferences')
        if not math.isfinite(e.tie_priority) or any(k not in e.scores or not math.isfinite(e.scores[k]) for k in e.preferences):raise ValueError('invalid_entrant_scores')
        preferences.append([k for k in e.preferences if e.scores[k]>=bykey[k].minimum])
    held={k:[] for k in bykey};next_choice=[0]*len(entrants);queue=deque(range(len(entrants)))
    while queue:
        i=queue.popleft()
        if next_choice[i]>=len(preferences[i]):continue
        key=preferences[i][next_choice[i]];next_choice[i]+=1
        held[key].append(i)
        held[key].sort(key=lambda j:(-entrants[j].scores[key],-entrants[j].tie_priority,j))
        if len(held[key])>bykey[key].seats:queue.append(held[key].pop())
    assignments=[None]*len(entrants)
    for key,indices in held.items():
        for i in indices:assignments[i]=key
    return assignments


def pmf(items,maximum):
    if not items:raise ValueError('empty_distribution')
    seen=set();mass=0
    for value,weight in items:
        if not math.isfinite(value) or value<0 or value>maximum or value in seen or not math.isfinite(weight) or weight<0:raise ValueError('invalid_distribution')
        seen.add(value);mass+=weight
    if abs(mass-1)>1e-9:raise ValueError('unnormalized_distribution')


def inverse(items,u):
    total=0
    for value,weight in items:
        total+=weight
        if u<total:return value
    return items[-1][0]


def wilson(successes,trials):
    # Computational binomial uncertainty conditional on the fictional laboratory model.
    z=1.959963984540054;p=successes/trials;denom=1+z*z/trials
    center=(p+z*z/(2*trials))/denom
    half=z*math.sqrt(p*(1-p)/trials+z*z/(4*trials*trials))/denom
    return [max(0,center-half),min(1,center+half)]


def simulate(config,*,trials=1000,seed=2026):
    if config.get('synthetic') is not True:raise ValueError('real_admission_simulation_not_validated')
    if config.get('category')!='general_budget':raise ValueError('unsupported_competition_category')
    if type(trials) is not int or not 1<=trials<=100000:raise ValueError('invalid_trials')
    maximum=config['maximum_score']
    if not math.isfinite(maximum) or not 0<maximum<=1000:raise ValueError('invalid_score_scale')
    programs=[Program(r['key'],r['seats'],r['minimum']) for r in config['programs']]
    keys={p.key for p in programs}
    if any(p.minimum>maximum for p in programs):raise ValueError('minimum_above_score_scale')
    deferred_acceptance(programs,[])  # Validate capacities and unique keys before drawing.
    counts=config['rival_count_distribution'];pmf(counts,20000)
    if any(type(n) is not int for n,_ in counts):raise ValueError('fractional_rival_count')
    for p in config['programs']:pmf(p['rival_score_distribution'],maximum)
    profiles=config['preference_profiles']
    pmf([(i,r['weight']) for i,r in enumerate(profiles)],len(profiles))
    for r in profiles:
        pref=r['programs']
        if not pref or len(pref)!=len(set(pref)) or any(k not in keys for k in pref):raise ValueError('invalid_preference_profile')
    candidate=config['candidate_scenarios'];pmf([(i,r['weight']) for i,r in enumerate(candidate)],len(candidate))
    pref=config['candidate_preferences']
    if not pref or len(pref)!=len(set(pref)) or any(k not in keys for k in pref):raise ValueError('invalid_candidate_preferences')
    for r in candidate:
        if set(r['scores'])!=keys or any(not math.isfinite(s) or s<0 or s>maximum for s in r['scores'].values()):raise ValueError('invalid_candidate_scenario')
    rng=random.Random(seed);wins=Counter()
    for _ in range(trials):
        own=inverse([(i,r['weight']) for i,r in enumerate(candidate)],rng.random())
        entrants=[Entrant(candidate[own]['scores'],tuple(pref),rng.random())]
        for _ in range(inverse(counts,rng.random())):
            shock=rng.random()  # Shared rival score rank across programs: an explicit assumption.
            scores={r['key']:inverse(r['rival_score_distribution'],shock) for r in config['programs']}
            profile=inverse([(i,r['weight']) for i,r in enumerate(profiles)],rng.random())
            entrants.append(Entrant(scores,tuple(profiles[profile]['programs']),rng.random()))
        wins[deferred_acceptance(programs,entrants)[0]]+=1
    admitted=trials-wins[None]
    return dict(version='synthetic-preference-mc-v1',status='synthetic_laboratory_only',synthetic=True,
        deployable=False,config_sha256=digest(config),code_sha256=digest(Path(__file__).read_text()),seed=seed,trials=trials,
        any_admission_scenario_mass=admitted/trials,
        monte_carlo_interval95=wilson(admitted,trials),
        by_program={p.key:wins[p.key]/trials for p in programs},rejected_mass=wins[None]/trials,
        assumptions=['General budget only; supplied minima and seats are synthetic.',
            'Applicant-proposing stable matching is not a reproduction of all Russian enrollment procedures.',
            'Shared rival score rank; preference mixture and pool sizes are fictional.',
            'Random tie priorities; no automatic BVI, quota, DVI or enrollment consent rules.',
            'Interval measures Monte Carlo noise conditional on assumptions, not real-world calibration.'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=Path('config/competition.synthetic.v1.json'))
    p.add_argument('--trials',type=int,default=1000);p.add_argument('--seed',type=int,default=2026);p.add_argument('--output',type=Path)
    a=p.parse_args();result=simulate(json.loads(a.config.read_text()),trials=a.trials,seed=a.seed)
    if a.output:write_json(a.output,result)
    print(json.dumps(result))
