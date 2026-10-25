import test from 'node:test';
import assert from 'node:assert/strict';
import { renderBaseline } from '../src/baseline.ts';
test('threshold baseline explains holdout errors and never turns them into admission chance',()=>{
  const s=renderBaseline('2026 вшэ математика бюджет');
  assert.ok(s.includes('Исходная история'));assert.ok(s.includes('108'));assert.ok(s.includes('Вероятности зачисления нет'));
  assert.ok(s.includes('https://'));assert.ok(!s.includes('%'));
});
test('unsupported future year and missing series fail closed',()=>{
  assert.ok(renderBaseline('2027 вшэ математика').includes('только для 2026'));
  assert.ok(renderBaseline('2026 random nonexistent').includes('не означает отсутствия'));
  assert.ok(renderBaseline('').includes('/baseline 2026'));
});
