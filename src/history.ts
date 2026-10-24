import entries from '../data/normalized/history_v1/public_index.json' with { type: 'json' };
const aliases: Record<string,string> = {
  mephi:'мифи',hse:'вшэ вышка',nsu:'нгу',bmstu:'мгту бауманка баумана',innopolis:'иннополис',
};
export function historicalSummary(query: string): string {
  const terms = query.trim().slice(0,128).toLocaleLowerCase('ru').replaceAll('ё','е').split(/\s+/).filter(Boolean);
  if (!terms.length) return 'Поиск опубликованных порогов: /history вшэ математика. Это история источников, не прогноз поступления.';
  const found = entries.filter(r => {
    const key=[aliases[r.institution_id],r.name,r.official_code,r.year].filter(Boolean).join(' ').toLocaleLowerCase('ru').replaceAll('ё','е');
    return terms.every(term => key.includes(term));
  }).sort((a,b) => b.year-a.year);
  if (!found.length) return 'В извлечённой истории совпадений нет. Это не означает, что конкурс не проводился или данных нет у вуза.';
  const labels: Record<string,string>={competition_points:'конкурсные баллы',exam_total_points:'сумма ЕГЭ/ВИ',
    exam_points:'баллы одного ЕГЭ',unspecified_points:'единица требует проверки'};
  const lines=found.slice(0,3).map(r => {
    const value=r.status==='numeric' ? String(r.value) : r.status==='lower_bound' ? `от ${r.value} (нижняя граница источника)` :
      r.status==='priority_only' ? 'места заполнены на приоритетном этапе; числового порога нет' :
      r.status==='bvi_only' ? 'только БВИ — отметка источника' : 'число не установлено';
    return `${r.year}: ${r.name}\n${aliases[r.institution_id] ?? r.institution_id}; ${r.category}\n${value}; ${labels[r.unit]}\n${r.source_url}`;
  });
  return `Исторических наблюдений: ${found.length}. Первые ${lines.length}:\n\n`+lines.join('\n\n')+
    '\n\nСостав конкурса и правила могли меняться. Пороги и единицы разных программ нельзя автоматически сравнивать; это не вероятность поступления.';
}
