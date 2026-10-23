import type { Database } from './platform.ts';

export async function applyMutation(
  db: Database, key: string, updateId: number, command: '/start' | '/delete_data',
): Promise<void> {
  const receipt = db.prepare('INSERT INTO telegram_updates(update_id, expires_at) VALUES (?, ?)')
    .bind(updateId, Math.floor(Date.now() / 1000) + 7 * 86400);
  const mutation = command === '/start'
    ? db.prepare('INSERT OR IGNORE INTO user_profiles(id, consent_version) VALUES (?, ?)').bind(key, 'stage0-v1')
    : db.prepare('DELETE FROM user_profiles WHERE id = ?').bind(key);
  try {
    // D1 batch is transactional: receipt and mutation commit together.
    await db.batch([receipt, mutation]);
  } catch {
    const existing = await db.prepare('SELECT update_id FROM telegram_updates WHERE update_id = ?')
      .bind(updateId).first();
    if (!existing) throw new Error('storage_failure');
  }
}
