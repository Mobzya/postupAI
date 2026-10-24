# Развёртывание на бесплатном Cloudflare Workers

Актуальное указание пользователя 24.10.2026: пока запускать бот локально во время
работы. Cloudflare-публикация сейчас не выполняется. Текущая инструкция:
[LOCAL_BOT.md](LOCAL_BOT.md); ниже сохранён план будущего постоянного размещения.

Проверено по официальной документации 2026-10-23. Нужны бесплатный аккаунт Cloudflare
и бот от BotFather. VPS, купленный домен, платные API и LLM не требуются.
Команды ниже — инструкция; реальный деплой и изменение webhook здесь не выполнялись.

## Локально

```bash
npm ci
npm run check
npm run db:local
cp .dev.vars.example .dev.vars
npm run dev
```

В `.dev.vars` заполнить независимые `TELEGRAM_WEBHOOK_SECRET` и `USER_ID_HMAC_KEY`.
Для каждого значения подходит генерация `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.
Webhook-secret: 32–256 символов A–Z/a–z/0–9/_/-. HMAC-key: не менее 32 символов.
Не использовать одинаковые ключи и не копировать секреты в исходники или историю команд.

`curl http://localhost:8787/health` возвращает этап и версию из bot.release.json,
а также forecasting=false и режим сохранения профилей.
Health не подтверждает доступность D1 и наличие таблиц.
Команда dev явно задаёт loopback и отключает инспектор: это также обходит
ошибку определения сетевых интерфейсов в некоторых изолированных средах.

## Подготовка Cloudflare и базы

```bash
npx wrangler login
npx wrangler d1 create ballnik
```

В `wrangler.toml` заменить нулевой `database_id` на выданный UUID.
UUID базы не является токеном, его можно версионировать. Оставить Workers Free.

```bash
npm run db:remote
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET
npx wrangler secret put USER_ID_HMAC_KEY
npx wrangler secret put TELEGRAM_BOT_TOKEN
npm run deploy:dry
npm run deploy
```

`secret put` запрашивает значения интерактивно: не передавать их аргументами.
Токен нужен для регистрации webhook и будущих исходящих Bot API-вызовов.
В этапе 0 Worker отвечает напрямую на webhook и не читает этот токен.
Хранить его только как Cloudflare secret; ввод при регистрации временный и не сохраняется.
Деплой выдаёт адрес `https://ballnik.<account>.workers.dev` без покупки домена.

## Регистрация Telegram webhook

```bash
python3 scripts/register_webhook.py --url https://ballnik.YOUR-SUBDOMAIN.workers.dev/telegram/webhook
```

Скрипт скрыто запрашивает токен бота и ранее установленный webhook-secret.
Значения должны совпадать с Cloudflare secrets. Скрипт вызывает `setWebhook`,
разрешает только сообщения, ограничивает параллельные соединения двумя и не
удаляет накопленные обновления. Токен, URL Bot API и ответ ошибки не печатаются.
Скрипт регистрации не вызывался с реальными credentials в этом этапе.

Проверить `/health`, затем в личном чате `/start`, `/profile`, `/sources`, `/delete_data`.
Через D1 убедиться, что профиль удалён. Прогноз на этапе 0 должен быть недоступен.

## Обновление

Новая схема — новая миграция: `npx wrangler d1 migrations create ballnik CHANGE_NAME`.
Сначала локальная миграция и тесты; перед изменением реальной базы сохранить резервную копию.

```bash
npx wrangler d1 export ballnik --remote --output backup.sql
npm run db:remote
```

Бэкап может содержать пользовательские данные: не коммитить, ограничить доступ,
удалять по принятой политике. Удаление профиля действует на рабочую базу; восстановление
из старого бэкапа может вернуть удалённые данные. Для такого восстановления нужна
отдельная процедура повторного удаления. Автоматическое управление бэкапами пока не реализовано.

Для данных сейчас доступны `python3 -m pipeline.validate` и `python3 -m pipeline.audit`.
Импорт исторических программ и публикация моделей появятся на этапе 1 и позднее:
не импортировать fixtures вручную в реальную базу. Исправления чисел — новые ревизии.

## Лимиты и эксплуатационные границы

На проверенную дату Workers Free: 100 000 запросов/сутки и 10 мс CPU/вызов.
D1 Free: 5 млн прочитанных строк/сутки, 100 000 записанных строк/сутки и 5 GB суммарно.
Доступность бесплатного режима ограничена квотами; это не обещание бесконечной нагрузки.
Запросы подготовлены и индексированы. PDF и симуляции не входят в обработку webhook.
Фактический CPU на Cloudflare ещё не профилирован; локальные времена тестов его не заменяют.

Worker не пишет payload или ошибки в console; observability выключен в конфиге.
Не включать запись тел запросов, заголовков секретов или подробных Bot API-ошибок.
HMAC-псевдоним — псевдонимизация, не анонимизация. Потеря/ротация HMAC-ключа
разрывает доступ к старым профилям: до ротации нужен план миграции и удаления.

## Первичные технические источники

- [Workers limits](https://developers.cloudflare.com/workers/platform/limits/).
- [D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/).
- [D1 commands](https://developers.cloudflare.com/d1/wrangler-commands/).
- [D1 local development](https://developers.cloudflare.com/d1/best-practices/local-development/).
- [Telegram Bot API / setWebhook](https://core.telegram.org/bots/api#setwebhook).
- [Telegram webhook replies](https://core.telegram.org/bots/faq#how-can-i-make-requests-in-response-to-updates).
