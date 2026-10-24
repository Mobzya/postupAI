import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogSummary, searchPrograms } from '../src/catalog.ts';

test('catalog summary distinguishes unavailable programs and marketing tracks', () => {
  const text = catalogSummary();
  assert.ok(text.includes('МФТИ'));
  assert.ok(text.includes('каталог пока не извлечён'));
  assert.ok(text.includes('Полнота'));
  assert.ok(text.length < 4096);
});

test('search combines university alias and program terms with provenance', () => {
  const text = searchPrograms('ВШЭ математика');
  assert.ok(text.includes('Найдено:'));
  assert.ok(text.includes('https://ba.hse.ru/'));
  assert.ok(text.includes('год приёма уточняется') || text.includes('2026'));
  assert.ok(text.length < 4096);
});

test('no match is never treated as absence of a program in a university', () => {
  assert.ok(searchPrograms('synthetic-no-such-program-9q7').includes('не означает отсутствия'));
  assert.ok(searchPrograms('').includes('/search'));
});
