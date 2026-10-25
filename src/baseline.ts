import index from '../data/normalized/threshold_baseline_v1/public_index.json' with {type:'json'};

export function renderBaseline(text:string):string {
  const [yearText,...words]=text.trim().split(/\s+/);const year=Number(yearText);
  if(!/^\d{4}$/.test(yearText??'')||!words.length)return 'Экспериментальный baseline порогов: /baseline 2026 вшэ математика. Для 2027 нужна история 2026; вероятности поступления не вычисляются.';
  if(year!==index.year)return `Артефакт рассчитан только для ${index.year}. Правила и историю других лет автоматически не подставляем.`;
  let query=words.join(' ').toLocaleLowerCase('ru').replace(/вшэ|hse/g,'').trim();
  const category=/платно/.test(query)?'paid':/бюджет/.test(query)?'budget_unspecified':null;
  query=query.replace(/платно|бюджет/g,'').trim();
  if(!query)return 'Добавьте название или код программы: /baseline 2026 вшэ математика бюджет';
  const matches=index.records.filter(r=>(!category||r.category===category)&&query.split(/\s+/).every(w=>
    `${r.name} ${r.official_code}`.toLocaleLowerCase('ru').includes(w))).slice(0,3);
  if(!matches.length)return 'Для запроса нет непрерывной сопоставленной текстовой серии. Это не означает отсутствия программы или конкурса. /history — исходные наблюдения.';
  return `Эксперимент порогов ${index.version}. Вероятности зачисления нет.\n`+
    matches.map(r=>`ВШЭ, ${r.name}, ${r.official_code}, ${r.category==='paid'?'платно':'бюджет (подкатегория не установлена)'}.\n`+
      `Перенос опубликованного порога ${r.last_published_year} на ${year}: ≈${Math.round(r.estimate/5)*5} конкурсных баллов.\n`+
      `Исходная история: ${r.training_years.map((y,i)=>`${y}: ${r.training_values[i]}`).join('; ')}.\n${r.source_url}`).join('\n\n')+
    `\n\nНа ${index.metrics.last_year.n} отложенных наблюдениях 2023–2025 средняя абсолютная ошибка переноса ≈${Math.round(index.metrics.last_year.mae)} баллов. Это общая метрика, не гарантия ошибки этой программы.\n`+
    'Совпадение URL/названия/кода не доказывает неизменность конкурса. Экзамены, места и льготы могли измениться. Порог не означает индивидуальное зачисление; оценка не даёт допуска или категории риска.';
}
