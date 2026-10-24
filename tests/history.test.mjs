import test from 'node:test';
import assert from 'node:assert/strict';
import { historicalSummary } from '../src/history.ts';
test('historical lookup includes source, units and absence of probability claim',()=>{
  const text=historicalSummary('вшэ математика');
  assert.ok(text.includes('https://ba.hse.ru/'));
  assert.ok(text.includes('конкурсные баллы'));
  assert.ok(text.includes('не вероятность'));
  assert.ok(text.length<4096);
});
test('historical no-match and missing query are explicit',()=>{
  assert.ok(historicalSummary('').includes('/history'));
  assert.ok(historicalSummary('synthetic-none-8x0').includes('не означает'));
});
