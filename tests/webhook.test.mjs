import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import worker from '../src/index.ts';
import { userKey } from '../src/privacy.ts';
import { SqliteD1 } from './sqlite-d1.mjs';

const secret = 'synthetic-webhook-secret-for-tests-only';
const hmac = 'synthetic-hmac-key-for-tests-only-12345';
const syntheticUser = 777001;
const env = () => ({ DB: new SqliteD1(), TELEGRAM_WEBHOOK_SECRET: secret, USER_ID_HMAC_KEY: hmac });
const update = (text = '/start', id = 1) => ({
  update_id: id, message: { text, chat: { id: syntheticUser, type: 'private' }, from: { id: syntheticUser, is_bot: false } },
});
function request(body, headers = {}) {
  return new Request('https://example.invalid/telegram/webhook', {
    method: 'POST', body: typeof body === 'string' ? body : JSON.stringify(body),
    headers: { 'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': secret, ...headers },
  });
}

test('health and route status codes', async () => {
  assert.equal((await (await worker.fetch(new Request('https://example.invalid/health'), {})).json()).forecasting, false);
  assert.equal((await worker.fetch(new Request('https://example.invalid/unknown'), {})).status, 404);
  assert.equal((await worker.fetch(new Request('https://example.invalid/telegram/webhook'), {})).status, 405);
  assert.equal((await worker.fetch(request(update()), {})).status, 503);
});
test('webhook secret fails closed with no persisted profile', async () => {
  const e = env();
  for (const bad of ['', 'incorrect']) {
    assert.equal((await worker.fetch(request(update(), { 'X-Telegram-Bot-Api-Secret-Token': bad }), e)).status, 401);
  }
  assert.equal(e.DB.raw.prepare('SELECT count(*) AS n FROM user_profiles').get().n, 0);
});
test('malformed, oversized and unsupported payloads are rejected', async () => {
  const e = env();
  for (const payload of ['{', 'null', '[]', '{}', '{"update_id":true}', '{"update_id":1,"message":3}']) {
    assert.equal((await worker.fetch(request(payload), e)).status, 400);
  }
  assert.equal((await worker.fetch(request('x'.repeat(65537)), e)).status, 413);
  assert.equal((await worker.fetch(request(update(), { 'Content-Length': '65537' }), e)).status, 413);
  assert.equal((await worker.fetch(request(update(), { 'Content-Type': 'text/plain' }), e)).status, 415);
});
test('groups, mismatched users and unsupported updates do not write profiles', async () => {
  const e = env();
  const group = update(); group.message.chat.type = 'group';
  const mismatch = update(); mismatch.message.chat.id++;
  for (const u of [group, mismatch, { update_id: 2 }]) {
    assert.deepEqual(await (await worker.fetch(request(u), e)).json(), { ok: true });
  }
  assert.equal(e.DB.raw.prepare('SELECT count(*) AS n FROM user_profiles').get().n, 0);
});
test('start persists only HMAC pseudonym; replay does not recreate deleted profile', async () => {
  const e = env();
  const reply = await (await worker.fetch(request(update()), e)).json();
  assert.equal(reply.method, 'sendMessage');
  const key = await userKey(syntheticUser, hmac);
  assert.equal(e.DB.raw.prepare('SELECT id FROM user_profiles').get().id, key);
  await worker.fetch(request(update('/delete_data', 2)), e);
  await worker.fetch(request(update('/start', 1)), e);
  assert.equal(e.DB.raw.prepare('SELECT count(*) AS n FROM user_profiles').get().n, 0);
  const dump = JSON.stringify(e.DB.raw.prepare('SELECT * FROM telegram_updates').all());
  assert.ok(!dump.includes(String(syntheticUser)));
});
test('delete cascades through all five user-dependent entities', async () => {
  const e = env(); e.DB.synthetic();
  await worker.fetch(request(update()), e);
  const key = await userKey(syntheticUser, hmac);
  e.DB.raw.prepare('INSERT INTO user_score_history VALUES (?,?,?,?,?,?,?,?,?,?)')
    .run('synthetic-score', key, 'mathematics', 80, '2026-10-23', 'synthetic', 6, 1, 90, '2027-06-01');
  e.DB.raw.prepare('INSERT INTO user_achievements VALUES (?,?,?,?,?)').run('synthetic-achievement', key, 'synthetic', '{}', 'self_reported');
  e.DB.raw.prepare('INSERT INTO saved_programs VALUES (?,?)').run(key, 'synthetic-program');
  e.DB.raw.prepare('INSERT INTO forecast_results(id,user_id,input_json,result_json) VALUES (?,?,?,?)')
    .run('synthetic-forecast', key, '{}', '{"is_synthetic":true}');
  assert.equal((await worker.fetch(request(update('/delete_data', 2)), e)).status, 200);
  for (const table of ['user_profiles', 'user_score_history', 'user_achievements', 'saved_programs', 'forecast_results']) {
    assert.equal(e.DB.raw.prepare(`SELECT count(*) AS n FROM ${table}`).get().n, 0);
  }
});
test('receipt rolls back with failed mutation; retry may succeed', async () => {
  const e = env();
  e.DB.raw.exec("CREATE TRIGGER synthetic_failure BEFORE INSERT ON user_profiles BEGIN SELECT RAISE(ABORT,'synthetic failure'); END");
  assert.equal((await worker.fetch(request(update()), e)).status, 503);
  assert.equal(e.DB.raw.prepare('SELECT count(*) AS n FROM telegram_updates').get().n, 0);
  e.DB.raw.exec('DROP TRIGGER synthetic_failure');
  assert.equal((await worker.fetch(request(update()), e)).status, 200);
});
test('commands acknowledge missing catalog/model; profile remains optional', async () => {
  const e = env();
  for (const cmd of ['/profile', '/programs', '/search', '/compare', '/forecast', '/achievements', '/sources']) {
    const response = await worker.fetch(request(update(cmd)), e);
    assert.equal(response.status, 200);
    const body = await response.json();
    assert.equal(body.method, 'sendMessage');
    assert.ok(body.text.length < 4096);
  }
  assert.equal(e.DB.raw.prepare('SELECT count(*) AS n FROM user_profiles').get().n, 0);
});
test('expired idempotency records are pruned with bounded cleanup', async () => {
  const e = env();
  e.DB.raw.exec('INSERT INTO telegram_updates VALUES (1,1), (2,9999999999)');
  await worker.scheduled({}, e);
  assert.equal(e.DB.raw.prepare('SELECT count(*) AS n FROM telegram_updates').get().n, 1);
});
test('Worker source contains no logging calls; unhandled details stay private', async () => {
  for (const file of ['index.ts', 'store.ts', 'privacy.ts', 'domain.ts']) {
    assert.doesNotMatch(readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8'), /console\.(log|warn|error|info|debug)\s*\(/);
  }
  const e = env(); e.DB.prepare = () => { throw new Error('synthetic-sensitive-detail'); };
  const response = await worker.fetch(request(update('/profile')), e);
  assert.equal(response.status, 503);
  assert.ok(!(await response.text()).includes('synthetic-sensitive-detail'));
});
