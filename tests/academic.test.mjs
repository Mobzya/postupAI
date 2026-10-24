import test from 'node:test';
import assert from 'node:assert/strict';
import { achievementPoints,calculateAcademicScore,findAcademicRule,renderRules,renderAcademicScore } from '../src/academic.ts';

const input={institution:'mephi',year:2026,code:'09.03.04',category:'general_budget',scores:{mathematics:85,informatics:90,russian:80},declaredAchievementPoints:5};
test('documented annual EGE score uses one eligible alternative and caps achievements',()=>{
  const r=calculateAcademicScore({...input,scores:{...input.scores,physics:88},declaredAchievementPoints:30});
  assert.equal(r.status,'ok');assert.equal(r.total,265);assert.equal(r.achievementPoints,10);
  assert.deepEqual(r.selected,['mathematics','informatics','russian']);
  assert.equal(r.admissionEligibility,'not_determined');
});
test('rules never fall back across year, institution or unsupported applicant scope',()=>{
  for(const override of [{year:2027},{institution:'msu'},{code:'31.05.01'},{code:'38.03.01',category:'paid'}])
    assert.equal(calculateAcademicScore({...input,...override}).status,'insufficient_data');
  assert.equal(calculateAcademicScore({...input,category:'targeted'}).status,'unsupported_track');
  assert.equal(calculateAcademicScore({...input,category:'bvi'}).status,'unsupported_track');
});
test('budget and paid minimums remain separate and missing alternatives are not invented',()=>{
  const scores={mathematics:72,physics:72,russian:67};
  assert.equal(calculateAcademicScore({...input,scores,category:'paid'}).status,'ok');
  assert.notEqual(calculateAcademicScore({...input,scores}).status,'ok');
  assert.equal(calculateAcademicScore({...input,scores:{mathematics:90,russian:80}}).status,'insufficient_data');
});
test('out-of-range, fractional or negative self-reported scores are rejected',()=>{
  for(const v of [-1,101,85.5,NaN])assert.equal(calculateAcademicScore({...input,scores:{...input.scores,mathematics:v}}).status,'invalid_input');
  assert.equal(calculateAcademicScore({...input,declaredAchievementPoints:-1}).status,'invalid_input');
});
test('achievement conditions and duplicate families are enforced before adding points',()=>{
  const honors={kind:'honors_rf',conditions:{russian_document:true,with_honors:true}};
  const gto={kind:'gto_gold',conditions:{badge_document_present:true,age_group_eligible_for_campaign:true}};
  const silver={kind:'gto_silver',conditions:gto.conditions};
  const r=achievementPoints([honors,honors,gto,silver]);
  assert.equal(r.status,'conditional');assert.equal(r.points,9);
  assert.equal(achievementPoints([{...gto,conditions:{badge_document_present:true}}]).status,'manual_review');
  assert.equal(achievementPoints([{kind:'unknown_olympiad',conditions:{}}]).status,'manual_review');
});
test('olympiad ID points do not grant BVI and respect the common cap',()=>{
  const r=achievementPoints([{kind:'rsosh_prize_unused',conditions:{diploma_present:true,not_used_for_special_rights:true,grade_11_diploma:true}},
    {kind:'honors_rf',conditions:{russian_document:true,with_honors:true}}]);
  assert.equal(r.status,'conditional');assert.equal(r.points,10);
  assert.equal(achievementPoints([{kind:'vosh_unused',conditions:{diploma_present:true,not_used_for_special_rights:false}}]).status,'manual_review');
});
test('bot score commands require an explicit annual scope and provide sources',()=>{
  assert.ok(renderAcademicScore('2026 09.03.04 бюджет мат=85 инф=90 рус=80 ид=5').includes('260'));
  assert.ok(renderAcademicScore('2026 09.03.04 бюджет мат=85 мат=90').includes('дважды'));
  assert.ok(renderRules('2027 09.03.04 бюджет').includes('другого года'));
  assert.ok(renderRules('2026 09.03.04 бюджет').includes('≥ 75'));
  assert.equal(findAcademicRule('mephi',2026,'09.03.04','general_budget').slots.length,3);
});
