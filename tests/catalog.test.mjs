import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogSummary, searchPrograms,programReferences,renderProgram,comparePrograms,catalogOptions } from '../src/catalog.ts';

test('catalog summary distinguishes unavailable programs and marketing tracks', () => {
  const text = catalogSummary();
  assert.ok(text.includes('МФТИ'));
  assert.ok(text.includes('профильных записей'));
  assert.ok(text.includes('Полнота'));
  assert.ok(text.length < 4096);
});

test('ITMO explicit 2026 disclosure is searchable without converting it into a 2027 offering',()=>{
  const s=searchPrograms('итмо 2026 AI360');assert.ok(s.includes('AI360'));assert.ok(s.includes('https://itmo.ru/sveden/education'));
  assert.ok(!s.includes('2027'));assert.ok(searchPrograms('итмо 2027').includes('не означает отсутствия'));
});

test('catalog references are unique; pagination retrieves different cards without a profile',()=>{
  assert.equal(new Set(programReferences.map(p=>p.id)).size,programReferences.length);
  const first=searchPrograms('вшэ'),second=searchPrograms('вшэ страница=2');
  const ids=s=>[...s.matchAll(/\/program ([a-f0-9]{8})/g)].map(m=>m[1]);
  assert.equal(ids(first).length,3);assert.equal(ids(second).length,3);
  assert.ok(ids(first).every(id=>!ids(second).includes(id)));
  assert.ok(searchPrograms('вшэ страница=9999').includes('Доступно страниц'));
  assert.ok(searchPrograms('вшэ страница=0').includes('положительным'));
});
test('cards and comparison retain sources, unknowns, category boundaries and distinct references',()=>{
  const [a,b]=programReferences;const card=renderProgram(a.id);
  assert.ok(card.includes('Источник: https://'));assert.ok(card.includes('Бюджет всего (с квотами)'));
  const c=comparePrograms(`${a.id} ${b.id}`);assert.ok(c.includes(a.name));assert.ok(c.includes(b.name));
  assert.ok(c.includes('не ранжирование шансов'));assert.ok(comparePrograms(`${a.id} ${a.id}`).includes('разные'));
  assert.ok(comparePrograms(`${a.id} 00000000`).includes('не найден'));
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

test('a common AI abbreviation finds actual named profiles in the guided search',()=>{
  const matches=catalogOptions(null,'ИИ');assert.ok(matches.length>0);
  assert.ok(matches.some(r=>/искусствен|AI360/i.test(r.name)));
});

test('MIPT pilot level and CU legal profiles can be searched without assuming a 2027 intake',()=>{
  const m=searchPrograms('мфти базовое AI360');assert.ok(m.includes('базовое высшее образование'));
  assert.ok(m.includes('год приёма уточняется'));assert.ok(!m.includes('; бакалавриат;'));
  const c=searchPrograms('цу математика');assert.ok(c.includes('2025'));assert.ok(c.includes('https://static.centraluniversity.ru/'));
});
