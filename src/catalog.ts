import entries from '../data/normalized/catalog_v1/public_index.json' with { type: 'json' };
import registry from '../data/source_registry.json' with { type: 'json' };

const aliases: Record<string, string> = {
  mipt: 'мфти физтех', hse: 'вшэ вышка hse', itmo: 'итмо itmo', mephi: 'мифи mephi',
  spbu: 'спбгу spbu', msu: 'мгу msu', nsu: 'нгу nsu', bmstu: 'баумана бауманка мгту bmstu',
  innopolis: 'иннополис innopolis', cu: 'центральный университет цу central',
};
const names: Record<string, string> = Object.fromEntries(
  registry.sources.map(s => [s.institution_id, s.institution_name]),
);
const normalize = (s: string): string => s.toLocaleLowerCase('ru').replaceAll('ё', 'е');
function matchesTerms(key:string,terms:string[]):boolean {
  return terms.every(term=>['ии','ai'].includes(term)?
    (key.includes('искусствен')||key.includes('машинн')||/(?:^|\W)ai(?:360|\W|$)/u.test(key)):
    term==='ml'?(key.includes('машинн')||key.includes('machine learning')||/(?:^|\W)ml(?:\W|$)/u.test(key)):key.includes(term));
}
const programs = entries.filter(r => r.kind === 'program_profile');
export const programReferences = programs.map(row=>({id:row.id.slice(-24,-16),name:row.name}));
const reference=(row:typeof programs[number])=>row.id.slice(-24,-16);
function level(row:typeof programs[number]):string {
  return row.degree === 'basic_higher' ? 'базовое высшее образование' :
    row.degree === 'specialist' ? 'специалитет' : row.degree === 'bachelor' ? 'бакалавриат' : 'уровень уточняется';
}
const index = programs.map(row => ({ row, key: normalize([
  row.name, row.official_code, row.campus, names[row.institution_id], aliases[row.institution_id],level(row),row.year,
].filter(Boolean).join(' ')) }));

export function catalogSummary(): string {
  const rows = registry.sources.map(s => {
    const count = programs.filter(r => r.institution_id === s.institution_id).length;
    return `${s.institution_name}: ${count ? count + ' профильных записей' : 'каталог пока не извлечён'}`;
  });
  return `Частичный каталог: ${programs.length} профильных записей.\n` +
    rows.join('\n') + '\n\nПолнота и актуальные условия приёма требуют проверки. ' +
    'Маркетинговые треки не считаются подтверждёнными программами.\nПоиск: /search математика';
}

export function searchPrograms(query: string): string {
  const pages=[...query.matchAll(/(?:^|\s)страница=([^\s]+)/g)];
  const page=pages.length?Number(pages[0]![1]):1;
  if(pages.length>1||!Number.isSafeInteger(page)||page<1)return 'Страница должна быть положительным целым числом: /search вшэ страница=2';
  const clean=query.replace(/(?:^|\s)страница=[^\s]+/g,'').trim().slice(0,128);
  const terms = normalize(clean).split(/\s+/).filter(Boolean);
  if (!terms.length) return 'Введите вуз, название или код: /search вшэ математика';
  const found = index.filter(item => matchesTerms(item.key,terms));
  if (!found.length) return 'В извлечённой части каталога совпадений нет. Это не означает отсутствия программы в вузе. /universities — покрытие вузов.';
  const maxPage=Math.ceil(found.length/3);
  if(page>maxPage)return `Доступно страниц: ${maxPage}. /search ${clean} страница=1`;
  const lines = found.slice((page-1)*3,page*3).map(({ row }) => {
    return `${row.name}\n${names[row.institution_id]}; ${row.campus ?? 'кампус уточняется'}\n` +
      `${row.official_code ?? 'код уточняется'}; ${level(row)}; ${row.year ?? 'год приёма уточняется'}\n${row.source_url}\nКарточка: /program ${reference(row)}`;
  });
  return `Найдено: ${found.length}. Страница ${page}/${maxPage}.\n\n` + lines.join('\n\n') +
    (page<maxPage?`\n\nДалее: /search ${clean} страница=${page+1}`:'')+
    '\n\nЭто записи источников. Условия и возможность поступления нужно сверять с официальными документами.';
}

function findProgram(id:string) {return /^[a-f0-9]{8}$/.test(id)?programs.find(row=>reference(row)===id):undefined;}
export function catalogOptions(institution:string|null,query='') {
  const terms=normalize(query.trim().slice(0,128)).split(/\s+/).filter(Boolean);
  return index.filter(({row,key})=>(institution===null||row.institution_id===institution)&&matchesTerms(key,terms))
    .map(({row})=>({id:reference(row),name:row.name,institution:row.institution_id,code:row.official_code,year:row.year,degree:row.degree}));
}
export function catalogCard(id:string):string|undefined {const row=findProgram(id);return row?card(row):undefined;}
export function catalogSources(id:string) {const row=findProgram(id);return row?{source:row.source_url,program:row.program_url}:undefined;}
function placesText(row:typeof programs[number]):string {
  const places=row.places as Record<string,unknown>|null;
  const budget=places?.budget_total,paid=places?.paid;
  return `Бюджет всего (с квотами): ${typeof budget==='number'?budget:'не установлено'}; платно: ${typeof paid==='number'?paid:'не установлено'}.`;
}
function card(row:typeof programs[number]):string {
  return `${row.name}\n${names[row.institution_id]}; ${row.campus??'кампус уточняется'}; ${level(row)}\n`+
    `Код: ${row.official_code??'не установлен'}, год: ${row.year??'не установлен'}.\n`+
    `Форма: ${({full_time:'очная',part_time:'очно-заочная',correspondence:'заочная'} as Record<string,string>)[row.study_form??'']??'не установлена'}.\n${placesText(row)}\n`+
    `Источник: ${row.source_url}`+(row.program_url?`\nПрограмма / описание: ${row.program_url}`:'');
}
export function renderProgram(id:string):string {
  const row=findProgram(id.trim());
  if(!row)return 'Карточка не найдена в текущем каталоге. Найдите программу через /search и скопируйте команду /program из результата.';
  return card(row)+`\nКод карточки: ${reference(row)}. Сравнение: /compare ${reference(row)} <код второй карточки>\n`+
    'Условия приёма и экзамены проверяются отдельно; число бюджетных мест не равно общему конкурсу. Запись источника не подтверждает допуск.'+
    (row.institution_id==='mephi'&&row.year===2026&&row.official_code?`\nПравила направления: /rules 2026 ${row.official_code} бюджет`:'');
}
export function comparePrograms(text:string):string {
  const ids=text.trim().split(/\s+/);
  if(ids.length<2||ids.length>3||new Set(ids).size!==ids.length)return 'Укажите 2–3 разные карточки: /compare <код1> <код2>. Коды указаны в /search и /program. Сравниваем сведения каталога; надёжных категорий риска пока нет.';
  const rows=ids.map(findProgram);
  if(rows.some(r=>!r))return 'Один из кодов не найден. Получите актуальные коды через /search.';
  return 'Сравнение записей каталога:\n\n'+rows.map(r=>card(r!)).join('\n\n')+
    '\n\nНеизвестные поля не заменены нулями. Годы и кампусы могут различаться. Это не ранжирование шансов поступления. Сохранение сравнения в профиле пока выключено.';
}
