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
const programs = entries.filter(r => r.kind === 'program_profile');
const index = programs.map(row => ({ row, key: normalize([
  row.name, row.official_code, row.campus, names[row.institution_id], aliases[row.institution_id],
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
  const terms = normalize(query.trim().slice(0, 128)).split(/\s+/).filter(Boolean);
  if (!terms.length) return 'Введите вуз, название или код: /search вшэ математика';
  const found = index.filter(item => terms.every(term => item.key.includes(term)));
  if (!found.length) return 'В извлечённой части каталога совпадений нет. Это не означает отсутствия программы в вузе. /universities — покрытие вузов.';
  const lines = found.slice(0, 3).map(({ row }) => {
    const level = row.degree === 'basic_higher' ? 'базовое высшее образование' :
      row.degree === 'specialist' ? 'специалитет' : row.degree === 'bachelor' ? 'бакалавриат' : 'уровень уточняется';
    return `${row.name}\n${names[row.institution_id]}; ${row.campus ?? 'кампус уточняется'}\n` +
      `${row.official_code ?? 'код уточняется'}; ${level}; ${row.year ?? 'год приёма уточняется'}\n${row.source_url}`;
  });
  return `Найдено: ${found.length}. Показаны первые ${lines.length}.\n\n` + lines.join('\n\n') +
    '\n\nЭто записи источников. Условия и возможность поступления нужно сверять с официальными документами.';
}
