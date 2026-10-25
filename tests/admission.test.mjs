import test from 'node:test';
import assert from 'node:assert/strict';
import { admissionReadinessText } from '../src/admission.ts';
import { forecastAvailability } from '../src/domain.ts';
test('synthetic competition laboratory and threshold backtest do not unlock real probabilities',()=>{
  assert.equal(forecastAvailability().status,'insufficient_data');
  const text=admissionReadinessText();
  assert.ok(text.includes('недоступна'));assert.ok(text.includes('синтетических'));assert.ok(text.includes('/ege'));
  assert.ok(!text.includes('%'));
});
