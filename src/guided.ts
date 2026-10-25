import release from '../config/bot.release.json' with {type:'json'};
import rules from '../data/normalized/rules_v1/public_rules.json' with {type:'json'};
import { catalogOptions,catalogCard,catalogSources } from './catalog.ts';
import { calculateAcademicScore } from './academic.ts';
import { MENU } from './ui.ts';

export const SUBJECTS=[
  {key:'russian',label:'Русский язык'},{key:'mathematics',label:'Математика'},
  {key:'informatics',label:'Информатика'},{key:'physics',label:'Физика'},
  {key:'chemistry',label:'Химия'},{key:'biology',label:'Биология'},
  {key:'history',label:'История'},{key:'social_studies',label:'Обществознание'},
  {key:'foreign_language',label:'Иностранный язык'},
] as const;
export const UNIVERSITIES=[
  {id:'mipt',name:'МФТИ'},{id:'hse',name:'ВШЭ'},{id:'itmo',name:'ИТМО'},{id:'mephi',name:'МИФИ'},
  {id:'spbu',name:'СПбГУ'},{id:'msu',name:'МГУ'},{id:'nsu',name:'НГУ'},{id:'bmstu',name:'Бауманка'},
  {id:'innopolis',name:'Иннополис'},{id:'cu',name:'ЦУ'},
] as const;
const OLY={u:'не указан',n:'нет',w:'победитель перечневой олимпиады',p:'призёр перечневой олимпиады'};
export interface SelectionState {
  year:2026|2027;mask:number;scores:(number|null)[];olympiad:keyof typeof OLY;
  olympiadLevel:number;olympiadSubject:number;university:number;funding:'b'|'p';
}
type Button={text:string;callback_data:string};
type InlineButton=Button|{text:string;url:string};
export interface GuidedView {text:string;reply_markup:{inline_keyboard:InlineButton[][]}|{force_reply:true;input_field_placeholder:string}|typeof MENU;delivery?:'send'}
export const initialSelection=():SelectionState=>({year:2027,mask:7,scores:Array<number|null>(9).fill(null),
  olympiad:'u',olympiadLevel:0,olympiadSubject:9,university:10,funding:'b'});
function valid(s:SelectionState):boolean {
  return [2026,2027].includes(s.year)&&Number.isInteger(s.mask)&&s.mask>=0&&s.mask<512&&s.scores.length===9&&
    s.scores.every((v,i)=>v===null||((s.mask&(1<<i))!==0&&Number.isInteger(v)&&v>=0&&v<=100))&&
    Object.hasOwn(OLY,s.olympiad)&&Number.isInteger(s.olympiadLevel)&&s.olympiadLevel>=0&&s.olympiadLevel<=3&&
    Number.isInteger(s.olympiadSubject)&&s.olympiadSubject>=0&&s.olympiadSubject<=9&&
    (!['u','n'].includes(s.olympiad)||(s.olympiadLevel===0&&s.olympiadSubject===9))&&
    Number.isInteger(s.university)&&s.university>=0&&s.university<=10&&['b','p'].includes(s.funding);
}
export function packSelection(s:SelectionState):string {
  if(!valid(s))throw new Error('invalid_selection');
  return String(s.year-2020)+s.mask.toString(36).padStart(2,'0')+
    s.scores.map(v=>v===null?'--':v.toString(36).padStart(2,'0')).join('')+
    s.olympiad+s.olympiadLevel+s.olympiadSubject+s.university.toString(36)+s.funding;
}
export function unpackSelection(value:string):SelectionState|null {
  if(!/^[67][0-9a-z]{2}(?:[0-9a-z]{2}|--){9}[unwp][0-3][0-9][0-9a][bp]$/.test(value))return null;
  const s:SelectionState={year:(2020+Number(value[0])) as 2026|2027,mask:parseInt(value.slice(1,3),36),
    scores:Array.from({length:9},(_,i)=>value.slice(3+i*2,5+i*2)==='--'?null:parseInt(value.slice(3+i*2,5+i*2),36)),
    olympiad:value[21] as keyof typeof OLY,olympiadLevel:Number(value[22]),olympiadSubject:Number(value[23]),
    university:parseInt(value[24]!,36),funding:value[25] as 'b'|'p'};
  return valid(s)?s:null;
}
function button(s:SelectionState,text:string,action:string,arg=''):Button {
  const data=`gp1:${action}:${arg}:${packSelection(s)}`;
  if(data.length>64||!/^[\x20-\x7e]+$/.test(data))throw new Error('callback_too_large');
  return {text,callback_data:data};
}
function inline(text:string,rows:InlineButton[][]):GuidedView {return {text,reply_markup:{inline_keyboard:rows}};}
function chunks<T>(xs:T[],n:number):T[][] {return Array.from({length:Math.ceil(xs.length/n)},(_,i)=>xs.slice(i*n,i*n+n));}
function scoreValues(s:SelectionState):Record<string,number> {
  return Object.fromEntries(SUBJECTS.flatMap((subject,i)=>s.scores[i]===null?[]:[[subject.key,s.scores[i]!]]));
}
function summary(s:SelectionState):string {
  const lines=SUBJECTS.flatMap((v,i)=>(s.mask&(1<<i))?[`${v.label}: ${s.scores[i]??'—'}`]:[]);
  if(s.olympiad!=='u')lines.push('Диплом: '+OLY[s.olympiad]+(s.olympiadLevel?`; уровень ${s.olympiadLevel}`:'')+
    (s.olympiadSubject<9?`; ${SUBJECTS[s.olympiadSubject]!.label}`:''));
  if(s.university!==10)lines.push('Вуз: '+UNIVERSITIES[s.university]!.name);
  if(s.funding==='p')lines.push('Финансирование: платно');
  return lines.join('\n');
}
export function subjectSelection(s=initialSelection()):GuidedView {
  return inline(`1 из 4 · Твои предметы\nПриём ${s.year}. Выбери предметы ЕГЭ.\nБаллы введём по одному. Сохранение профиля выключено.`,[
    ...chunks(SUBJECTS.map((v,i)=>button(s,`${(s.mask&(1<<i))?'✓ ':''}${v.label}`,'t',String(i))),2),
    [button(s,'Ввести баллы →','b')],[button(s,'Баллы пока неизвестны','z')],
    [button(s,s.year===2027?'Справочно: условия 2026':'Вернуться к приёму 2027','y',s.year===2027?'6':'7')],
    [button(s,'Главное меню','h')],
  ]);
}
function scorePrompt(s:SelectionState,i:number,error=false):GuidedView {
  return {text:(error?'Нужно целое число от 0 до 100.\n':'')+`Баллы ЕГЭ · приём ${s.year}\n${summary(s)}\n\n`+
    `Балл по предмету «${SUBJECTS[i]!.label}»? Введи число от 0 до 100.`,
    reply_markup:{force_reply:true,input_field_placeholder:'Например: 85'},delivery:'send'};
}
function olympiadView(s:SelectionState):GuidedView {
  const present=s.olympiad==='w'||s.olympiad==='p';
  return inline('2 из 4 · Олимпиада\nЕсть диплом перечневой олимпиады?'+(present?
    `\nВыбрано: ${OLY[s.olympiad]}. Уровень: ${s.olympiadLevel||'не указан'}, предмет: ${SUBJECTS[s.olympiadSubject]?.label??'не указан'}.`:'')+
    '\nЛьготу для конкретной программы нужно сверить с правилами вуза.',[
    [button(s,'Нет диплома','k','n')],[button(s,'Победитель','k','w'),button(s,'Призёр','k','p')],
    ...(present?[[button(s,'Уровень 1','l','1'),button(s,'Уровень 2','l','2'),button(s,'Уровень 3','l','3')],
      [button(s,'Предмет диплома','j')],[button(s,'Выбрать вуз →','v')]]:[]),
    [button(s,'← Баллы','e')],
  ]);
}
function olympiadSubjects(s:SelectionState):GuidedView {
  return inline('По какому предмету диплом?',[
    ...chunks(SUBJECTS.map((v,i)=>button(s,v.label,'j',String(i))),2),[button(s,'Другой / не указан','j','9')],
  ]);
}
function universityView(s:SelectionState):GuidedView {
  return inline('3 из 4 · Где искать?\nВыбери вуз или посмотри программы всех десяти вузов.',[
    [button(s,'Все вузы','u','a')],...chunks(UNIVERSITIES.map((u,i)=>button(s,u.name,'u',i.toString(36))),2),
    [button(s,'← Олимпиада','o')],
  ]);
}
const PAGE_SIZE=4;
function queryFrom(text:string):string {return text.split('\n').find(l=>l.startsWith('Поиск: '))?.slice(7,135)??'';}
function results(s:SelectionState,page=0,query=''):GuidedView {
  const institution=UNIVERSITIES[s.university]?.id??null;
  const all=catalogOptions(institution,query);const pages=Math.max(1,Math.ceil(all.length/PAGE_SIZE));
  page=Math.max(0,Math.min(page,pages-1));const entries=all.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE);
  const name=UNIVERSITIES[s.university]?.name??'Все вузы';
  return inline(`4 из 4 · ${name}\nЗапрос: приём ${s.year} · ${s.funding==='b'?'бюджет':'платно'}\n`+
    (query?`Поиск: ${query}\n`:'')+
    `В каталоге найдено: ${all.length}. Страница ${page+1}/${pages}.\n`+
    (s.year===2027?'Условия 2027 ещё сверяются. Годы в карточках могут отличаться.':'Справочное сравнение с условиями 2026, не прогноз на 2027.')+
    (all.length?'\nВыбери программу:':'\nСовпадений в собранной части каталога нет; попробуй другое название.')+
    '\nКаталог частичный. Проверенной вероятности зачисления пока нет.',[
    [button(s,'🔎 Найти по названию','n')],
    ...entries.map(row=>{
      const suffix=[institution?'':UNIVERSITIES.find(u=>u.id===row.institution)?.name,
        row.degree==='basic_higher'?'базовое':'',row.code].filter(Boolean).join(' · ');
      const limit=Math.max(18,56-suffix.length);const title=row.name.length>limit?row.name.slice(0,limit-1)+'…':row.name;
      return [button(s,title+(suffix?' · '+suffix:''),'p',row.id+page.toString(36))];
    }),
    ...(pages>1?[[...(page>0?[button(s,'‹ Назад','r',(page-1).toString(36))]:[]),
      ...(page<pages-1?[button(s,'Дальше ›','r',(page+1).toString(36))]:[])]]:[]),
    [button(s,'По требованиям ЕГЭ','d')],
    [button(s,'Другой вуз','v'),button(s,'Изменить баллы','e')],
    [button(s,s.funding==='b'?'Платное обучение':'Бюджет','f',s.funding==='b'?'p':'b')],
    [button(s,'Главное меню','h')],
  ]);
}
function searchPrompt(s:SelectionState):GuidedView {
  return {text:`Поиск программ · приём ${s.year}\n${summary(s)}\n\nКакую программу ищешь? Например: математика или ИИ.`,
    reply_markup:{force_reply:true,input_field_placeholder:'Название или код программы'},delivery:'send'};
}
function programView(s:SelectionState,id:string,query='',page=0):GuidedView {
  const option=catalogOptions(null).find(r=>r.id===id);const detail=catalogCard(id);
  if(!option||!detail)return results(s,0,query);
  const scores=scoreValues(s);
  const context=option.institution==='mephi'&&option.code?calculateAcademicScore({institution:'mephi',year:s.year,
    code:option.code,category:s.funding==='b'?'general_budget':'paid',scores}):null;
  const note=context?.status==='ok'?`\n\nДля московского направления МИФИ ${option.code}, ${s.year}: сумма ЕГЭ ${context.total}, без ИД. Минимумы направления выполнены. Кампус и условия этого профиля требуют отдельной сверки.`:
    context?.status==='ineligible'?'\n\nПо имеющимся правилам московского направления МИФИ один из минимумов ЕГЭ не выполнен.':
    '\n\nПравила этой программы на выбранный год ещё не сверены полностью.';
  const sources=catalogSources(id);
  const sourceButtons:InlineButton[]=[];
  if(sources?.source.startsWith('https://'))sourceButtons.push({text:'Официальный источник',url:sources.source});
  if(sources?.program?.startsWith('https://')&&sources.program!==sources.source)sourceButtons.push({text:'Описание программы',url:sources.program});
  const concise=detail.split('\n').filter(line=>!line.startsWith('Источник:')&&!line.startsWith('Программа / описание:')).join('\n');
  return inline(concise+note+(s.olympiad==='w'||s.olympiad==='p'?`\nДиплом: ${OLY[s.olympiad]}. Льготу и возможные ИД нужно сверить по названию олимпиады и году/классу диплома.`:'')+
    (query?`\nПоиск: ${query}`:'')+'\n\nЭто справочные сведения, не вероятность поступления.',[
    ...(sourceButtons.length?[sourceButtons]:[]),
    [button(s,'← Программы','r',page.toString(36))],[button(s,'Другой вуз','v'),button(s,'Изменить баллы','e')],
  ]);
}
function directionView(s:SelectionState,page=0,reference=false):GuidedView {
  if(s.year!==2026&&!reference)return inline('Для кампании 2027 ещё нет проверенного набора годовых правил.\nМожно отдельно посмотреть справочные минимумы 2026. Это не прогноз зачисления.',[
    [button(s,'Посмотреть правила 2026','a','6')],[button(s,'← Программы','r','0')],
  ]);
  if(s.university!==10&&UNIVERSITIES[s.university]?.id!=='mephi')return inline('Пока внесены ограничения школьного ЕГЭ МИФИ (Москва, 2026). Для выбранного вуза нужно сверить правила.\nВысокую вероятность по этим сведениям определить нельзя.',[
    [button(s,'Посмотреть МИФИ 2026','m')],[button(s,'← Программы','r','0')],
  ]);
  const candidates=rules.rules.filter(r=>r.category===(s.funding==='b'?'general_budget':'paid')).flatMap(r=>{
    const result=calculateAcademicScore({institution:'mephi',year:2026,code:r.official_code,category:r.category,scores:scoreValues(s)});
    return result.status==='ok'?[{rule:r,total:result.total}]:[];
  });
  const pages=Math.max(1,Math.ceil(candidates.length/4));page=Math.max(0,Math.min(page,pages-1));
  const shown=candidates.slice(page*4,page*4+4);
  const pageAction=reference?'q':'d';
  return inline('МИФИ · Москва · 2026'+(s.year===2027?' · справка, приём 2027 не проверен':'')+'\nНаправления, для которых выполнены документированные минимумы ЕГЭ.\n'+
    (shown.length?shown.map(r=>`${r.rule.official_code} · сумма ЕГЭ ${r.total}`).join('\n'):'Для расчёта не хватает баллов или не выполнены минимумы. Их можно изменить кнопкой ниже.')+
    '\n\nМинимум для участия не равен проходному баллу. Условия конкретного профиля, квоты и диплом нужно сверить отдельно. Это не список с гарантией или высокой вероятностью.',[
    ...shown.map(r=>[button(s,`${r.rule.official_code} · ${r.rule.name}`.slice(0,60),'c',r.rule.official_code.replaceAll('.',''))]),
    ...(pages>1?[[...(page>0?[button(s,'‹ Назад',pageAction,(page-1).toString(36))]:[]),...(page<pages-1?[button(s,'Дальше ›',pageAction,(page+1).toString(36))]:[])]]:[]),
    [button(s,'Изменить баллы','e'),button(s,'← Программы','r','0')],
  ]);
}
function editScores(s:SelectionState):GuidedView {
  return inline('Какой балл изменить?',[
    ...chunks(SUBJECTS.flatMap((v,i)=>(s.mask&(1<<i))?[button(s,`${v.label}: ${s.scores[i]??'—'}`,'e',String(i))]:[]),2),
    [button(s,'Изменить предметы','s')],[button(s,'← Программы','r','0')],
  ]);
}
export function guidedCallback(data:string,messageText=''):GuidedView|null {
  if(data.length>64)return null;
  const parts=data.split(':');if(parts.length!==4||parts[0]!=='gp1'||!/^[a-z]$/.test(parts[1]!)||!/^[a-z0-9]{0,12}$/.test(parts[2]!))return null;
  const s=unpackSelection(parts[3]!);if(!s)return null;
  const action=parts[1]!,arg=parts[2]!,n=arg?parseInt(arg,36):0,query=queryFrom(messageText);
  switch(action){
    case 'h':return {text:'Выбери действие. Новый подбор начнётся с чистого выбора.',reply_markup:MENU,delivery:'send'};
    case 's':return subjectSelection(s);
    case 't':if(!/^[0-8]$/.test(arg))return null;s.mask^=1<<n;if(!(s.mask&(1<<n)))s.scores[n]=null;return subjectSelection(s);
    case 'b':{
      if(!s.mask){const view=subjectSelection(s);return {...view,text:view.text+'\nОтметь хотя бы один предмет или выбери «Баллы пока неизвестны».'};}
      const i=SUBJECTS.findIndex((_,i)=>(s.mask&(1<<i))&&s.scores[i]===null);return i<0?olympiadView(s):scorePrompt(s,i);
    }
    case 'z':s.scores.fill(null);return olympiadView(s);
    case 'o':return olympiadView(s);
    case 'k':if(!['n','w','p'].includes(arg))return null;s.olympiad=arg as 'n'|'w'|'p';s.olympiadLevel=0;s.olympiadSubject=9;return arg==='n'?universityView(s):olympiadView(s);
    case 'l':if(!/^[0-3]$/.test(arg)||!['w','p'].includes(s.olympiad))return null;s.olympiadLevel=n;return olympiadView(s);
    case 'j':if(!['w','p'].includes(s.olympiad))return null;if(!arg)return olympiadSubjects(s);if(!/^[0-9]$/.test(arg))return null;s.olympiadSubject=n;return olympiadView(s);
    case 'v':return universityView(s);
    case 'u':if(!/^[0-9a]$/.test(arg))return null;s.university=n;return results(s);
    case 'y':if(!/^[67]$/.test(arg))return null;s.year=(2020+n) as 2026|2027;return subjectSelection(s);
    case 'a':if(arg!=='6')return null;return directionView(s,0,true);
    case 'm':s.university=3;return directionView(s,0,true);
    case 'f':if(!['b','p'].includes(arg))return null;s.funding=arg as 'b'|'p';return results(s,0,query);
    case 'r':return n<1000?results(s,n,query):null;
    case 'p':return /^[0-9a-f]{8}[0-9a-z]{1,3}$/.test(arg)?programView(s,arg.slice(0,8),query,parseInt(arg.slice(8),36)):null;
    case 'n':return searchPrompt(s);
    case 'e':return arg?(/^[0-8]$/.test(arg)&&(s.mask&(1<<n))?scorePrompt(s,n):null):editScores(s);
    case 'd':return n<1000?directionView(s,n):null;
    case 'q':return n<1000?directionView(s,n,true):null;
    case 'c':if(!/^\d{6}$/.test(arg))return null;s.university=3;return results(s,0,arg.slice(0,2)+'.'+arg.slice(2,4)+'.'+arg.slice(4));
    default:return null;
  }
}

function parseSummary(lines:string[]):SelectionState|null {
  const first=lines[0]?.match(/^(Баллы ЕГЭ|Поиск программ) · приём (2026|2027)$/);if(!first)return null;
  const s=initialSelection();s.year=Number(first[2]) as 2026|2027;s.mask=0;
  for(const line of lines.slice(1)){
    const subject=SUBJECTS.findIndex(v=>line.startsWith(v.label+': '));
    if(subject>=0){if(s.mask&(1<<subject))return null;const value=line.slice(SUBJECTS[subject]!.label.length+2);
      if(value!=='—'&&!/^\d{1,3}$/.test(value))return null;s.mask|=1<<subject;s.scores[subject]=value==='—'?null:Number(value);continue;}
    if(line.startsWith('Диплом: ')){
      const values=line.slice(8).split('; ');const kind=Object.entries(OLY).find(([key,v])=>key!=='u'&&v===values[0])?.[0];
      if(!kind)return null;s.olympiad=kind as keyof typeof OLY;
      for(const v of values.slice(1)){if(/^уровень [1-3]$/.test(v))s.olympiadLevel=Number(v.at(-1));
        else{const i=SUBJECTS.findIndex(subject=>subject.label===v);if(i<0)return null;s.olympiadSubject=i;}}
    }else if(line.startsWith('Вуз: ')){const i=UNIVERSITIES.findIndex(u=>u.name===line.slice(5));if(i<0)return null;s.university=i;}
    else if(line==='Финансирование: платно')s.funding='p';
    else return null;
  }
  return valid(s)?s:null;
}
export function guidedReply(value:string,reply:unknown):GuidedView|null {
  if(value.trim().startsWith('/')||!reply||typeof reply!=='object')return null;
  const r=reply as {text?:unknown;from?:{is_bot?:unknown;username?:unknown}};
  if(r.from?.is_bot!==true||r.from.username!==release.bot_username||typeof r.text!=='string')return null;
  const original=r.text.startsWith('Нужно целое число от 0 до 100.\n')?r.text.slice('Нужно целое число от 0 до 100.\n'.length):r.text;
  const parts=original.split('\n\n');if(parts.length!==2)return null;
  const s=parseSummary(parts[0]!.split('\n'));if(!s)return null;
  if(original.startsWith('Поиск программ')){
    if(searchPrompt(s).text!==original)return null;const query=value.trim().replace(/\s+/g,' ').slice(0,128);
    return query?results(s,0,query):searchPrompt(s);
  }
  const i=SUBJECTS.findIndex(v=>parts[1]===`Балл по предмету «${v.label}»? Введи число от 0 до 100.`);
  if(i<0||!(s.mask&(1<<i))||scorePrompt(s,i).text!==original)return null;
  const number=value.trim();if(!/^\d{1,3}$/.test(number)||Number(number)>100)return scorePrompt(s,i,true);
  s.scores[i]=Number(number);const next=SUBJECTS.findIndex((_,i)=>(s.mask&(1<<i))&&s.scores[i]===null);
  return next>=0?scorePrompt(s,next):s.olympiad==='u'?olympiadView(s):results(s);
}
