import type { Env } from './platform.ts';
import { matchesSecret, userKey } from './privacy.ts';
import { applyMutation } from './store.ts';
import { forecastAvailability } from './domain.ts';
import registry from '../data/source_registry.json' with { type: 'json' };
import release from '../config/bot.release.json' with { type: 'json' };
import coverage from '../data/normalized/mephi/metrics.json' with { type: 'json' };

const MAX_BODY = 65536;
const json = (data: unknown, status = 200): Response => Response.json(data, {
  status, headers: { 'Cache-Control': 'no-store' },
});

async function readBounded(request: Request): Promise<unknown> {
  const reader = request.body?.getReader();
  if (!reader) throw new Error('invalid_body');
  const chunks: Uint8Array[] = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY) { await reader.cancel(); throw new Error('body_too_large'); }
    chunks.push(value);
  }
  const body = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.length; }
  return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(body));
}

type MessageUpdate = {
  update_id: number;
  message?: { text?: string; chat?: { id?: number; type?: string }; from?: { id?: number; is_bot?: boolean } };
};
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function parseUpdate(value: unknown): MessageUpdate | null {
  if (!record(value) || !Number.isSafeInteger(value.update_id) || (value.update_id as number) < 0) return null;
  if (value.message !== undefined) {
    const m = value.message;
    if (!record(m) || (m.text !== undefined && typeof m.text !== 'string') ||
        (m.chat !== undefined && !record(m.chat)) ||
        (m.from !== undefined && !record(m.from))) return null;
  }
  return value as MessageUpdate;
}

const prototypeIntro = 'Ballnik: подготовка сервиса оценки поступления. Проверенной модели пока нет. ' +
  'Команда /start сохраняет только псевдоним профиля и дату согласия; имя, Telegram ID и сообщения не сохраняются. ' +
  'Удаление: /delete_data. Команды: /profile /programs /search /compare /forecast /achievements /sources.';

function stageStatus(): string {
  return `BALLNIK / postupAI — этап ${release.stage}, версия ${release.version}.\n` +
    (release.review_status === 'accepted' ? 'Этап принят.\n' : 'Результат этапа ожидает внешней проверки.\n') +
    `МИФИ: ${coverage.program_profiles} профиля, ${coverage.historical_rows} исторических строк, ` +
    `${coverage.seat_allocations} распределений мест.\n` +
    `Подтверждённых конкурсных групп: ${coverage.competition_groups_confirmed}.\n` +
    'Вероятности поступления пока не рассчитываются.\n' +
    `Отчёт: ${release.review_url}`;
}

const publicIntro = 'BALLNIK / postupAI — помощник по поступлению, сейчас в разработке.\n' +
  `Текущий этап: ${release.stage}. /status — результаты и ограничения.\n` +
  'Сохранение профилей и результатов пока выключено.\n' +
  'Команды: /status /sources /programs /forecast.';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const path = new URL(request.url).pathname;
    const profileStorageEnabled = env.PROFILE_STORAGE_ENABLED === 'true';
    if (path === '/health' && request.method === 'GET') {
      return json({ status: 'ok', stage: release.stage, version: release.version,
        forecasting: false, profileStorageEnabled, databaseChecked: false });
    }
    if (path !== '/telegram/webhook') return json({ error: 'not_found' }, 404);
    if (request.method !== 'POST') return json({ error: 'method_not_allowed' }, 405);
    if (!env.TELEGRAM_WEBHOOK_SECRET || env.TELEGRAM_WEBHOOK_SECRET.length < 32 ||
        !/^[A-Za-z0-9_-]{32,256}$/.test(env.TELEGRAM_WEBHOOK_SECRET) ||
        (profileStorageEnabled && (!env.DB || !env.USER_ID_HMAC_KEY || env.USER_ID_HMAC_KEY.length < 32))) {
      return json({ error: 'service_not_configured' }, 503);
    }
    const secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token') ?? '';
    if (secret.length > 256 || !await matchesSecret(secret, env.TELEGRAM_WEBHOOK_SECRET)) {
      return json({ error: 'unauthorized' }, 401);
    }
    if (request.headers.get('Content-Type')?.split(';')[0]?.trim().toLowerCase() !== 'application/json') {
      return json({ error: 'unsupported_media_type' }, 415);
    }
    const declared = request.headers.get('Content-Length');
    if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > MAX_BODY)) {
      return json({ error: 'body_too_large' }, 413);
    }
    let value: unknown;
    try { value = await readBounded(request); } catch (error) {
      return json({ error: 'invalid_body' }, error instanceof Error && error.message === 'body_too_large' ? 413 : 400);
    }
    const update = parseUpdate(value);
    if (!update) return json({ error: 'invalid_update' }, 400);
    const message = update.message;
    if (!message?.text || message.chat?.type !== 'private' ||
        !Number.isSafeInteger(message.from?.id) || message.from?.is_bot !== false ||
        message.from!.id! <= 0 || message.chat.id !== message.from?.id) return json({ ok: true });
    const command = message.text.trim().split(/\s+/)[0]?.split('@')[0]?.toLowerCase();
    try {
      let text: string;
      switch (command) {
        case '/start': {
          if (profileStorageEnabled) {
            const key = await userKey(message.from!.id!, env.USER_ID_HMAC_KEY!);
            await applyMutation(env.DB!, key, update.update_id, '/start');
          }
          text = profileStorageEnabled ? prototypeIntro : publicIntro;
          break;
        }
        case '/delete_data': {
          if (profileStorageEnabled) {
            const key = await userKey(message.from!.id!, env.USER_ID_HMAC_KEY!);
            await applyMutation(env.DB!, key, update.update_id, '/delete_data');
            text = 'Профиль и связанные сохранённые данные удалены. Данные аккаунта и переписка в Telegram управляются в Telegram.';
          } else {
            text = 'В текущей версии сохранение профилей выключено. Переписка в Telegram управляется в Telegram.';
          }
          break;
        }
        case '/profile': {
          if (!profileStorageEnabled) {
            text = 'Сохранение профилей и результатов пока выключено. /status — текущие возможности.';
            break;
          }
          const key = await userKey(message.from!.id!, env.USER_ID_HMAC_KEY!);
          const profile = await env.DB!.prepare('SELECT created_at FROM user_profiles WHERE id = ?')
            .bind(key).first<{ created_at: string }>();
          text = profile ? 'Профиль создан. Ввод результатов и настройки подготовки появятся на следующем этапе разработки бота.' :
            'Сохранённого профиля нет. /start — создать профиль.';
          break;
        }
        case '/sources':
          text = 'Официальные источники вузов. Данные МИФИ извлечены; для остальных вузов пока выполнена разведка.\n' +
            registry.sources.map(s => `${s.institution_name}: ${s.url}`).join('\n');
          break;
        case '/programs': case '/search':
          text = `В источниках МИФИ извлечено ${coverage.program_profiles} профиля. ` +
            'Полнота каталога кампании пока не подтверждена. Поиск по десяти вузам появится после подготовки каталога. /status — состояние данных.';
          break;
        case '/status':
          text = stageStatus();
          break;
        case '/forecast': case '/compare':
          forecastAvailability();
          text = 'Прогноз пока недоступен: нет проверенных данных и модели. Проценты поступления не рассчитываются.';
          break;
        case '/achievements':
          text = 'Ввод достижений пока недоступен. Учёт БВИ и дополнительных баллов потребует проверенных правил каждой программы.';
          break;
        default: text = profileStorageEnabled ? prototypeIntro : publicIntro;
      }
      // Telegram supports a Bot API method in the webhook response; no outbound API call.
      return json({ method: 'sendMessage', chat_id: message.chat.id, text });
    } catch {
      // Never log the request, SQL parameters, exception or Bot API URL.
      return json({ error: 'temporary_storage_failure' }, 503);
    }
  },

  async scheduled(_event: unknown, env: Env): Promise<void> {
    if (env.PROFILE_STORAGE_ENABLED !== 'true' || !env.DB) return;
    await env.DB.prepare('DELETE FROM telegram_updates WHERE update_id IN ' +
      '(SELECT update_id FROM telegram_updates WHERE expires_at < ? ORDER BY expires_at LIMIT 1000)')
      .bind(Math.floor(Date.now() / 1000)).run();
  },
};
