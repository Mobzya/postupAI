import bundle from '../data/normalized/rules_v1/public_rules.json' with { type: 'json' };
import { competitionScore } from './domain.ts';

export interface AchievementClaim { kind: string; conditions: Readonly<Record<string,boolean>> }
export function achievementPoints(claims: readonly AchievementClaim[]) {
  const byFamily = new Map<string,number>();
  for (const claim of claims) {
    if(!Object.hasOwn(bundle.supported_achievements,claim.kind))return {status:'manual_review' as const,reason:'unsupported_achievement'};
    const rule = bundle.supported_achievements[claim.kind as keyof typeof bundle.supported_achievements];
    if (!rule) return { status:'manual_review' as const, reason:'unsupported_achievement' };
    if (!rule.requires.every(key => claim.conditions[key] === true)) {
      return { status:'manual_review' as const, reason:'achievement_conditions_not_established' };
    }
    byFamily.set(rule.family,Math.max(byFamily.get(rule.family) ?? 0,rule.points));
  }
  const cap=bundle.rules[0]?.achievementCap;
  if (cap===undefined) return {status:'manual_review' as const,reason:'achievement_cap_unavailable'};
  return {status:'conditional' as const,points:Math.min([...byFamily.values()].reduce((a,b)=>a+b,0),cap),cap,
    inputStatus:'self_reported' as const};
}

export function findAcademicRule(institution: string,year: number,code: string,category: string) {
  if (institution!==bundle.institution_id || year!==bundle.year) return undefined;
  return bundle.rules.find(r=>r.official_code===code && r.category===category);
}

export function calculateAcademicScore(input: {
  institution:string;year:number;code:string;category:string;scores:Readonly<Record<string,number>>;
  declaredAchievementPoints?:number;
}) {
  if (!['general_budget','paid'].includes(input.category)) return {status:'unsupported_track' as const,reason:'requires_separate_rules'};
  const rule=findAcademicRule(input.institution,input.year,input.code,input.category);
  if (!rule) return {status:'insufficient_data' as const,reason:'no_documented_rules_for_scope'};
  const points=input.declaredAchievementPoints ?? 0;
  if (!Number.isInteger(points) || points<0 || Object.values(input.scores).some(v=>!Number.isInteger(v)||v<0||v>100)) {
    return {status:'invalid_input' as const,reason:'invalid_ege_or_achievement_score'};
  }
  const result=competitionScore(input.scores,points,{track:input.category as 'general_budget'|'paid',verified:true,
    slots:rule.slots,achievementCap:rule.achievementCap});
  return {...result,year:input.year,ruleId:rule.id,inputStatus:'self_reported' as const,
    admissionEligibility:'not_determined' as const,sources:bundle.sources};
}

const labels:Record<string,string>={mathematics:'Математика',russian:'Русский язык',physics:'Физика',
  informatics:'Информатика',chemistry:'Химия',biology:'Биология',history:'История',
  social_studies:'Обществознание',foreign_language:'Иностранный язык'};
const aliases:Record<string,string>={мат:'mathematics',математика:'mathematics',рус:'russian',русский:'russian',
  физ:'physics',физика:'physics',инф:'informatics',информатика:'informatics',хим:'chemistry',химия:'chemistry',
  био:'biology',биология:'biology',ист:'history',история:'history',общ:'social_studies',обществознание:'social_studies',
  ин:'foreign_language',иностранный:'foreign_language'};
const category = (v:string) => v==='бюджет' ? 'general_budget' : v==='платно' ? 'paid' : v;

export function renderRules(argumentsText:string):string {
  const [yearText,code,trackText]=argumentsText.trim().split(/\s+/);
  if (!yearText || !code || !trackText) return 'Правила МИФИ: /rules 2026 09.03.04 бюджет (или платно). Для других вузов правила ещё не внесены.';
  const rule=findAcademicRule('mephi',Number(yearText),code,category(trackText));
  if (!rule) return 'Документированные правила для этого года, направления или категории ещё не внесены. Правила другого года автоматически не применяются.';
  return `МИФИ, Москва, ${yearText}, ${code}, ${trackText}. ЕГЭ после школы:\n`+
    rule.slots.map((slot,i)=>`${i+1}. ${slot.map(e=>`${labels[e.key] ?? e.key} ≥ ${e.minimum}`).join(' или ')}`).join('\n')+
    `\nОбщие ИД: максимум ${rule.achievementCap}.\nБВИ, квоты и ранжирование при равенстве требуют отдельной проверки.\n`+
    'Расчёт: /score 2026 09.03.04 бюджет мат=85 инф=90 рус=80 ид=5\n'+bundle.sources[0];
}

export function renderAcademicScore(argumentsText:string):string {
  const [yearText,code,trackText,...pairs]=argumentsText.trim().split(/\s+/);
  if (!yearText || !code || !trackText) return 'Укажите год, направление, категорию и баллы: /score 2026 09.03.04 бюджет мат=85 инф=90 рус=80 ид=5';
  const scores:Record<string,number>={};let points=0;let achievementSpecified=false;
  for (const pair of pairs) {
    const match=/^([^=]+)=(\d+)$/.exec(pair);
    if (!match) return 'Баллы задаются целыми числами: мат=85 инф=90 рус=80 ид=5';
    const key=match[1]!.toLocaleLowerCase('ru');const value=Number(match[2]);
    if (key==='ид') {if(achievementSpecified)return 'ИД указаны дважды.';points=value;achievementSpecified=true;}
    else {
      const subject=Object.hasOwn(aliases,key)?aliases[key]:undefined;
      if (!subject) return 'Неизвестный предмет. Доступны мат, рус, физ, инф, хим, био, ист, общ, ин.';
      if (scores[subject]!==undefined) return 'Один предмет указан дважды.';
      scores[subject]=value;
    }
  }
  const result=calculateAcademicScore({institution:'mephi',year:Number(yearText),code,category:category(trackText),scores,declaredAchievementPoints:points});
  if(result.status==='invalid_input')return 'Баллы ЕГЭ должны быть целыми от 0 до 100, ИД — неотрицательным целым числом.';
  if(result.status==='unsupported_track')return 'БВИ и квоты требуют отдельных правил; обычная сумма не определяет право участия.';
  if(result.status==='insufficient_data')return 'Не хватает документированных правил или обязательного/альтернативного экзамена. Проверьте /rules и год кампании.';
  if(result.status==='ineligible')return 'Не выполнен минимум одного из обязательных экзаменов по выбранным правилам. Проверьте /rules.';
  if(result.status!=='ok')return 'Для этого расчёта требуется дополнительная проверка правил.';
  return `Условный конкурсный балл: ${result.total}. Учтено ИД: ${result.achievementPoints}.\n`+
    `Выбраны экзамены: ${result.selected.map(s=>labels[s] ?? s).join(', ')}.\n`+
    'Баллы и ИД указаны вами; подтверждение достижений выполняет вуз. Это расчёт по правилам, не подтверждение допуска или вероятность зачисления.\n'+bundle.sources[0];
}

export function renderAchievementRules():string {
  return 'МИФИ, 2026: общие ИД — максимум 10.\n'+
    'Документ РФ об образовании с отличием: 5. ГТО: золото 4, серебро 3, бронза 2 — при выполнении возрастных и документальных условий.\n'+
    'Неиспользованный для особых прав диплом ВСоШ: 10; РСОШ за 11 класс: победитель 10, призёр 8. Это не автоматическое право БВИ.\n'+
    'Другие достижения и подтверждающие условия требуют отдельной проверки. /rules — экзамены.\n'+
    'https://admission.mephi.ru/admission/baccalaureate-and-specialty/personal-achievements';
}
