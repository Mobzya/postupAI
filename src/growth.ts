import config from '../config/progress.scenarios.v1.json' with { type:'json' };
import { validateDistribution, type Distribution } from './domain.ts';

export interface MockResult { date:string; score:number }
export interface SubjectPlan { subject:string; mocks:readonly MockResult[]; hoursPerWeek:number; regularity:number }
export interface GrowthInput { asOf:string; examDate:string; subjects:readonly SubjectPlan[]; target?:number }
export type Scenario = keyof typeof config.scenarios;
const DAY=86400000; const MONTH=365.25/12;
export function dateDay(value:string):number {
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))throw new Error('invalid_date');
  const ms=Date.parse(value+'T00:00:00Z');
  if(!Number.isFinite(ms)||new Date(ms).toISOString().slice(0,10)!==value)throw new Error('invalid_date');
  return ms/DAY;
}
function checkInput(input:GrowthInput) {
  const now=dateDay(input.asOf), exam=dateDay(input.examDate);
  if(exam<now||exam-now>config.max_horizon_days)throw new Error('invalid_forecast_horizon');
  if(input.subjects.length<1||input.subjects.length>3)throw new Error('invalid_subject_count');
  const seen=new Set<string>();
  for(const s of input.subjects) {
    if(!Object.hasOwn(config.subject_parameters,s.subject)||seen.has(s.subject))throw new Error('unsupported_or_duplicate_subject');
    seen.add(s.subject);
    if(!Number.isFinite(s.hoursPerWeek)||s.hoursPerWeek<0||s.hoursPerWeek>config.max_hours_per_subject_week||
       !Number.isFinite(s.regularity)||s.regularity<0||s.regularity>1||!s.mocks.length||s.mocks.length>100)throw new Error('invalid_study_plan');
    const dates=new Set<number>();
    for(const mock of s.mocks) {
      const day=dateDay(mock.date);
      if(day>now||now-day>config.max_horizon_days||dates.has(day)||!Number.isInteger(mock.score)||mock.score<0||mock.score>100)throw new Error('invalid_mock_history');
      dates.add(day);
    }
  }
  if(input.target!==undefined&&(!Number.isFinite(input.target)||input.target<0||input.target>100*input.subjects.length))throw new Error('invalid_target');
  return {now,exam};
}

// Piecewise integration crosses band boundaries without applying the faster rate above them.
function projectedCenter(score:number,subject:string,months:number,hours:number,regularity:number,scenario:Scenario) {
  const rates=config.subject_parameters[subject as keyof typeof config.subject_parameters];
  const multiplier=Math.pow(hours/config.reference_hours_per_week,config.intensity_exponent)*regularity*config.scenarios[scenario].gain_multiplier;
  let value=score,remaining=months;
  for(let i=0;i<rates.length&&remaining>0;i++) {
    const upper=config.score_bands[i+1]!;if(value>=upper)continue;
    const rate=rates[i]!*multiplier;if(rate<=0)break;
    const used=Math.min(remaining,(upper-value)/rate);value+=used*rate;remaining-=used;
  }
  return Math.min(100,Math.max(0,value));
}
function distribution(scores:readonly number[]):Distribution {
  const weights=new Map<number,number>();
  scores.forEach((score,i)=>weights.set(score,(weights.get(score)??0)+config.latent_nodes[i]!.weight));
  return [...weights].sort((a,b)=>a[0]-b[0]).map(([score,probability])=>({score,probability}));
}
export function quantile(d:Distribution,q:number):number {
  if(!Number.isFinite(q)||q<0||q>1)throw new Error('invalid_quantile');
  let p=0;for(const point of d){p+=point.probability;if(p>=q-1e-12)return point.score;}
  return d[d.length-1]!.score;
}
function summarize(d:Distribution) { return {median:quantile(d,0.5),lower:quantile(d,0.1),upper:quantile(d,0.9)}; }

export function predictGrowth(input:GrowthInput) {
  const {now,exam}=checkInput(input);const months=(exam-now)/MONTH;
  const scenarios=(Object.keys(config.scenarios) as Scenario[]).map(scenario=>{
    const subjects=input.subjects.map(plan=>{
      const mocks=[...plan.mocks].sort((a,b)=>dateDay(a.date)-dateDay(b.date));const latest=mocks[mocks.length-1]!;
      const age=(now-dateDay(latest.date))/MONTH;
      const noise=(config.measurement_uncertainty+config.uncertainty_per_sqrt_month*Math.sqrt(months)+
        config.stale_mock_uncertainty_per_sqrt_month*Math.sqrt(age))*config.scenarios[scenario].uncertainty_multiplier;
      const center=projectedCenter(latest.score,plan.subject,months,plan.hoursPerWeek,plan.regularity,scenario);
      const samples=config.latent_nodes.map(node=>Math.max(0,Math.min(100,Math.round(center+node.z*noise))));
      const d=distribution(samples);validateDistribution(d);
      const trajectory=[];
      for(let m=0;m<months;m+=1)trajectory.push({monthsAhead:m,center:projectedCenter(latest.score,plan.subject,m,plan.hoursPerWeek,plan.regularity,scenario)});
      trajectory.push({monthsAhead:months,center});
      return {subject:plan.subject,anchor:latest,historyCount:mocks.length,center,distribution:d,samples,trajectory,...summarize(d)};
    });
    // Shared shock preserves dependence. This extreme rank model is an explicit assumption.
    const total=distribution(config.latent_nodes.map((_,i)=>subjects.reduce((sum,s)=>sum+s.samples[i]!,0)));
    validateDistribution(total,input.subjects.length*100);
    const mass=input.target===undefined?null:total.filter(p=>p.score>=input.target!).reduce((sum,p)=>sum+p.probability,0);
    return {scenario,subjects,total,...summarize(total),targetScenarioMass:mass};
  });
  return {version:config.version,status:'uncalibrated_scenario' as const,asOf:input.asOf,examDate:input.examDate,
    months,dependence:config.dependence,admissionProbability:null,scenarios};
}

const labels:Record<string,string>={cautious:'Осторожный',base:'Базовый',accelerated:'Ускоренный',mathematics:'мат',informatics:'инф',russian:'рус'};
const aliases:Record<string,string>={мат:'mathematics',инф:'informatics',рус:'russian'};
export function renderGrowth(text:string,asOf=new Date().toISOString().slice(0,10)):string {
  const [examDate,...pairs]=text.trim().split(/\s+/);
  if(!examDate||!pairs.length)return 'Сценарии ЕГЭ: /ege 2027-06-01 мат=70/6 инф=75/6 рус=65/3 цель=280 рег=0.8\nПосле балла указаны часы в неделю ПО КАЖДОМУ предмету. Дата пробника по умолчанию сегодня; можно добавить пробник=2026-10-24. Регулярность по умолчанию 1. Результаты не сохраняются.';
  try {
    const args=new Map<string,string>();
    for(const pair of pairs){const m=/^([^=]+)=(.+)$/.exec(pair);if(!m||args.has(m[1]!))throw new Error('invalid_argument');args.set(m[1]!,m[2]!);}
    const subjects:SubjectPlan[]=[];let target:number|undefined;let regularity=1;let mockDate=asOf;
    for(const [key,value] of args) {
      if(key==='цель'){if(!/^\d+$/.test(value))throw new Error('invalid_target');target=Number(value);}
      else if(key==='рег'){if(!/^(0(?:\.\d+)?|1(?:\.0+)?)$/.test(value))throw new Error('invalid_regularity');regularity=Number(value);}
      else if(key==='пробник')mockDate=value;
      else if(!Object.hasOwn(aliases,key))throw new Error('unknown_subject');
    }
    for(const [key,value] of args)if(Object.hasOwn(aliases,key)){
      const m=/^(\d+)\/(\d+(?:\.\d+)?)$/.exec(value);if(!m)throw new Error('invalid_score_hours');
      subjects.push({subject:aliases[key]!,mocks:[{date:mockDate,score:Number(m[1])}],hoursPerWeek:Number(m[2]),regularity});
    }
    const result=predictGrowth({asOf,examDate,subjects,...(target===undefined?{}:{target})});
    return `Сценарный калькулятор ЕГЭ (${result.version}). Пробник ${mockDate}, план с ${asOf} до ${examDate}.\n`+
      'Темпы и разброс заданы гипотезами, проверка на учениках ещё не проводилась.\n'+
      result.scenarios.map(s=>`${labels[s.scenario]}: ${s.median} (${s.lower}–${s.upper}). `+
        s.subjects.map(p=>`${labels[p.subject]} ${p.median}`).join(', ')+
        (s.targetScenarioMass===null?'':`\nДоля заданного распределения с суммой ≥ ${target}: ≈${Math.round(s.targetScenarioMass*20)*5}%.`)).join('\n')+
      '\nВ скобках — квантили 10–90% заданного распределения, не проверенный доверительный интервал. Общий сценарный шок для предметов. Проценты не являются проверенной вероятностью достижения цели или зачисления. /model — допущения.';
  } catch {return 'Проверьте данные: /ege — пример. Баллы 0–100, часы 0–40 на предмет, регулярность 0–1; пробник не в будущем, экзамен от сегодня до двух лет. Доступны мат, инф, рус; повторять предмет нельзя.';}
}

export function renderGrowthModel():string {
  return `${config.version}: сценарный калькулятор, не обученная модель.\n`+
    'Исходная точка — последний пробник; старые пробники сохраняются только во входном массиве и пока не оценивают личный темп.\n'+
    'При 6 ч/нед и регулярности 1 гипотезы прироста за месяц для диапазонов 0–60 / 60–85 / 85–100:\n'+
    Object.entries(config.subject_parameters).map(([key,rates])=>`${labels[key]}: ${rates.join(' / ')}`).join('\n')+
    '\nИнтенсивность масштабируется квадратным корнем часов; цель не меняет прогноз. Три сценария меняют темп и разброс. Предметы имеют общий сценарный шок; эта зависимость не оценена по данным. БВИ, конкурс и зачисление здесь не моделируются.\n'+
    'Параметры: https://github.com/Mobzya/postupAI/blob/stage/2b-ege-growth/config/progress.scenarios.v1.json';
}
