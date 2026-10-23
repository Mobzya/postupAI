// Minimal structural subset of the public D1 binding API; no runtime package.
export interface Statement {
  bind(...values: (string | number | null)[]): Statement;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  all<T = Record<string, unknown>>(): Promise<{ results: T[]; success: boolean }>;
  run(): Promise<{ success: boolean }>;
}

export interface Database {
  prepare(sql: string): Statement;
  batch(statements: Statement[]): Promise<unknown[]>;
}

export interface Env {
  DB: Database;
  TELEGRAM_WEBHOOK_SECRET: string;
  USER_ID_HMAC_KEY: string;
  TELEGRAM_BOT_TOKEN?: string;
}
