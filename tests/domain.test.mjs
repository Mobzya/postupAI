import test from 'node:test';
import assert from 'node:assert/strict';
import { competitionScore, validateDistribution, forecastAvailability, TRACKS } from '../src/domain.ts';

const rules = {
  verified: true, track: 'general_budget', achievementCap: 10,
  slots: [
    [{ key: 'russian', minimum: 40, maximum: 100 }],
    [{ key: 'mathematics', minimum: 50, maximum: 100 }],
    [{ key: 'informatics', minimum: 60, maximum: 100 }, { key: 'physics', minimum: 40, maximum: 100 }],
  ],
};

test('synthetic rules select eligible alternative and cap achievements', () => {
  assert.deepEqual(competitionScore({ russian: 80, mathematics: 90, informatics: 59, physics: 70 }, 20, rules), {
    status: 'ok', total: 250, selected: ['russian', 'mathematics', 'physics'], achievementPoints: 10,
  });
});
test('missing, unverified and ineligible inputs produce no score', () => {
  assert.equal(competitionScore({}, 0, rules).status, 'insufficient_data');
  assert.equal(competitionScore({}, 0, { ...rules, verified: false }).status, 'insufficient_data');
  assert.equal(competitionScore({ russian: 39, mathematics: 90, physics: 70 }, 0, rules).status, 'ineligible');
  assert.equal(competitionScore({ russian: 80, mathematics: 90, informatics: 59 }, 0, rules).status, 'insufficient_data');
});
test('special categories require separate deterministic rules', () => {
  for (const track of TRACKS.filter(t => !['general_budget', 'paid'].includes(t))) {
    assert.equal(competitionScore({}, 0, { ...rules, track }).status, 'unsupported_track');
  }
});
test('DVI is an independent required component in synthetic rules', () => {
  const dvi = { ...rules, slots: [...rules.slots, [{ key: 'dvi:math', minimum: 40, maximum: 100 }]] };
  const scores = { russian: 80, mathematics: 90, physics: 70 };
  assert.equal(competitionScore(scores, 0, dvi).status, 'insufficient_data');
  assert.equal(competitionScore({ ...scores, 'dvi:math': 85 }, 0, dvi).total, 325);
});
test('invalid scores and contradictory exam slots are rejected', () => {
  for (const russian of [-1, 101, NaN, Infinity]) {
    assert.throws(() => competitionScore({ russian, mathematics: 80, physics: 80 }, 0, rules));
  }
  assert.throws(() => competitionScore({}, -1, rules));
  assert.throws(() => competitionScore({}, 0, { ...rules, slots: [[], rules.slots[0]] }));
  assert.throws(() => competitionScore({}, 0, { ...rules, slots: [rules.slots[0], rules.slots[0]] }));
});
test('normalized bounded synthetic distributions include 100 without exceeding it', () => {
  validateDistribution([{ score: 99, probability: 0.4 }, { score: 100, probability: 0.6 }]);
  validateDistribution([{ score: 0, probability: 1 }]);
  validateDistribution([{ score: 325, probability: 1 }], 410);
});
test('negative, nonfinite, duplicate, unnormalized and >100 distributions fail', () => {
  for (const points of [[], [{ score: 101, probability: 1 }], [{ score: -1, probability: 1 }],
    [{ score: 70, probability: -0.1 }, { score: 80, probability: 1.1 }],
    [{ score: 80, probability: 0.9 }], [{ score: NaN, probability: 1 }],
    [{ score: 80, probability: 0.5 }, { score: 80, probability: 0.5 }]]) {
    assert.throws(() => validateDistribution(points));
  }
});
test('no forecast is published at stage 0', () => {
  assert.equal(forecastAvailability().status, 'insufficient_data');
});
