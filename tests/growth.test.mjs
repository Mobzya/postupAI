import test from 'node:test';
import assert from 'node:assert/strict';
import { predictGrowth,renderGrowth,dateDay } from '../src/growth.ts';
import { validateDistribution } from '../src/domain.ts';
const plan=(subject='mathematics',score=70,hours=6)=>({subject,mocks:[{date:'2026-10-24',score}],hoursPerWeek:hours,regularity:1});
const input={asOf:'2026-10-24',examDate:'2027-06-01',subjects:[plan(),plan('informatics',75),plan('russian',65,3)],target:280};
test('growth is deterministic, bounded and normalized for all scenarios and subjects',()=>{
  const a=predictGrowth(input);assert.deepEqual(a,predictGrowth(input));assert.equal(a.status,'uncalibrated_scenario');assert.equal(a.admissionProbability,null);
  for(const s of a.scenarios){validateDistribution(s.total,300);for(const p of s.subjects)validateDistribution(p.distribution);assert.ok(s.targetScenarioMass>=0&&s.targetScenarioMass<=1);}
  assert.ok(a.scenarios[0].median<=a.scenarios[1].median&&a.scenarios[1].median<=a.scenarios[2].median);
});
test('target is diagnostic and never changes the score distribution',()=>{
  const a=predictGrowth(input),b=predictGrowth({...input,target:210});
  for(let i=0;i<3;i++){assert.deepEqual(a.scenarios[i].total,b.scenarios[i].total);assert.ok(a.scenarios[i].targetScenarioMass<=b.scenarios[i].targetScenarioMass);}
});
test('zero preparation and zero regularity cause no assumed central growth; exam day has no future growth',()=>{
  for(const subjects of [[plan('mathematics',70,0)],[{...plan(),regularity:0}]]){
    const a=predictGrowth({...input,subjects,target:90});assert.equal(a.scenarios[1].subjects[0].center,70);
  }
  const a=predictGrowth({...input,examDate:input.asOf});assert.equal(a.months,0);assert.equal(a.scenarios[1].subjects[0].center,70);
});
test('near-100 progress slows and saturation does not create out-of-bounds scores',()=>{
  const low=predictGrowth({...input,subjects:[plan('mathematics',55)],target:90}).scenarios[1].subjects[0];
  const high=predictGrowth({...input,subjects:[plan('mathematics',90)],target:90}).scenarios[1].subjects[0];
  assert.ok(low.center-55>high.center-90);
  for(const score of [0,100])for(const s of predictGrowth({...input,subjects:[plan('mathematics',score,40)],target:100}).scenarios)validateDistribution(s.subjects[0].distribution);
});
test('latest dated mock anchors forecast; gaps increase uncertainty without applying the plan to the past',()=>{
  const subjects=[{...plan(),mocks:[{date:'2026-10-24',score:70},{date:'2026-09-01',score:40}]}];
  const r=predictGrowth({...input,subjects,target:90}).scenarios[1].subjects[0];assert.equal(r.anchor.score,70);assert.equal(r.historyCount,2);
  const future=predictGrowth({...input,asOf:'2027-01-01',subjects,target:90}).scenarios[1].subjects[0];assert.ok(future.center<r.center);
});
test('shared latent shock sums to joint total rather than assuming independent subjects',()=>{
  const a=predictGrowth(input);for(const s of a.scenarios){
    assert.equal(s.total[0].score,s.subjects.reduce((n,p)=>n+p.samples[0],0));
    assert.equal(s.total.at(-1).score,s.subjects.reduce((n,p)=>n+p.samples.at(-1),0));
  }
});
test('invalid dates, future mocks, past exams, duplicate or unsupported subjects fail closed',()=>{
  assert.throws(()=>dateDay('2027-02-29'));assert.throws(()=>dateDay('2027-2-01'));
  for(const override of [{examDate:'2026-10-23'},{examDate:'2030-01-01'},{subjects:[plan(),plan()]},
    {subjects:[plan('physics')]},{subjects:[plan('mathematics',101)]},{subjects:[{...plan(),regularity:1.1}]},
    {subjects:[{...plan(),mocks:[{date:'2026-10-25',score:70}]}]},{subjects:[]},{target:301}])assert.throws(()=>predictGrowth({...input,...override}));
});
test('bot calculator labels assumptions, reports all scenarios and never persists inputs',()=>{
  const s=renderGrowth('2027-06-01 мат=70/6 инф=75/6 рус=65/3 цель=280 рег=0.8','2026-10-24');
  for(const text of ['Осторожный','Базовый','Ускоренный','не являются проверенной','Пробник 2026-10-24'])assert.ok(s.includes(text));
  assert.ok(renderGrowth('2027-06-01 мат=70/6 мат=75/6','2026-10-24').includes('Проверьте'));
});
