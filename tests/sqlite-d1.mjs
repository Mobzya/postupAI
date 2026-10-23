import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';

export class SqliteD1 {
  constructor() {
    this.raw = new DatabaseSync(':memory:');
    this.raw.exec('PRAGMA foreign_keys = ON');
    for (const file of readdirSync(new URL('../migrations/', import.meta.url)).sort()) {
      this.raw.exec(readFileSync(new URL(`../migrations/${file}`, import.meta.url), 'utf8'));
    }
  }
  prepare(sql) {
    const raw = this.raw;
    let bindings = [];
    return {
      bind(...values) { bindings = values; return this; },
      async first() { return raw.prepare(sql).get(...bindings) ?? null; },
      async all() { return { results: raw.prepare(sql).all(...bindings), success: true }; },
      async run() { raw.prepare(sql).run(...bindings); return { success: true }; },
    };
  }
  async batch(statements) {
    this.raw.exec('BEGIN');
    try {
      const results = [];
      for (const statement of statements) results.push(await statement.run());
      this.raw.exec('COMMIT');
      return results;
    } catch (error) {
      this.raw.exec('ROLLBACK');
      throw error;
    }
  }
  synthetic() {
    this.raw.exec(readFileSync(new URL('fixtures/admissions.synthetic.sql', import.meta.url), 'utf8'));
  }
}
