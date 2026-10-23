# Воспроизводимый импорт в локальную D1

Нужны Node 24+, Python 3.12+, lxml из requirements-data.txt и Poppler/pdftotext.
Проверенная версия pdftotext — 24.02.0. Сеть для воспроизведения по сохранённым снимкам не нужна.

```bash
npm ci
python3 -m pip install -r requirements-data.txt
python3 -m pipeline.mephi_pipeline build
python3 -m pipeline.import_mephi --export-sql data/normalized/mephi/import.sql
npx wrangler d1 migrations apply ballnik --local --persist-to .wrangler/mephi-demo
npx wrangler d1 execute ballnik --local --persist-to .wrangler/mephi-demo --file data/normalized/mephi/import.sql --json
```

Импортировать тот же файл повторно безопасно. Файл содержит около 1.1 MB SQL с реальными
агрегатами и метаданными; HTML/PDF целиком туда не помещаются. Секреты бота для импорта не нужны.
Директория persist-to выделена для демонстрации и не затрагивает удалённую базу.

Проверки:

```sql
SELECT count(*) AS profiles FROM programs;
SELECT count(*) AS campaign_directions FROM campaign_field_offerings;
SELECT count(*) AS historical_rows FROM admission_observations;
SELECT threshold_status, count(*) FROM admission_observations GROUP BY threshold_status;
SELECT o.official_code_raw, o.cutoff, o.threshold_status, o.mean_ege_score
FROM admission_observations o JOIN admission_campaigns c ON c.id=o.campaign_id
WHERE c.year=2025 AND o.official_code_raw IN ('01.03.02','09.03.04');
SELECT places, funding, evidence_json FROM seat_allocations WHERE places=120;
```

На чистой схеме ожидаются: 82 профиля, 31 направление кампании, 286 исторических
наблюдений, 279 numeric и 7 bvi_only; одна запись на 120 мест, содержащая четыре IT-кода.
После повторного импорта количества не растут. Чистая схема содержит 29 таблиц проекта.
Таблица служебных миграций Wrangler не входит в это число.

Альтернатива без D1: применить migrations/*.sql по порядку к SQLite с FK=ON,
затем `python3 -m pipeline.import_mephi --sqlite PATH.sqlite`.
Импорт Python атомарный: ошибка откатывает весь batch. SQL-экспорт проверен локальным
Wrangler; для обновления удалённой базы требуется отдельная процедура публикации и резервирования.

## Новый сбор и ручной путь

```bash
python3 -m pipeline.mephi_pipeline run
python3 -m pipeline.mephi_pipeline run --refresh
```

Без refresh повторно используются проверенные по хешу снимки. Fetch соблюдает robots,
ожидание не менее 1.5 секунды на хост, ограничение размера и timeout. Междоменные
перенаправления требуют проверки. CAPTCHA/вход не обходятся.
Discover читает ссылки в HTML и находит каталог и три нужных PDF. Скрипты сайта не исполняются.

Если автоматическое получение публичного файла невозможно, предоставленный законным
способом файл можно зарегистрировать явно:

```bash
python3 -m pipeline.manual_snapshot --source-id mephi-history \
  --url https://admission.mephi.ru/admission/baccalaureate-and-specialty/exams/previous-years \
  --file LOCAL_PUBLIC_FILE.html --obtained-at 2026-10-23T18:00:00+03:00 \
  --note "Файл предоставлен для ручной проверки происхождения"
```

Время и происхождение такого файла считаются заявленными поставщиком; он не получает
статус HTTP-проверенного. Затем build/validate выполняют ту же проверку структуры.
`--dataset PATH.json` у import_mephi позволяет выбрать проверенный нормализованный набор;
редактирование значения без соответствующего исходного снимка отвергается replay-проверкой.
После обновления источника контрольные строки и документы необходимо сверить повторно.
