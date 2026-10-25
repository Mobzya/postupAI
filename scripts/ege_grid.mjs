// Technical scenario audit on synthetic inputs; not empirical validation.
import assert from 'node:assert/strict';
import { mkdirSync,readFileSync,writeFileSync } from 'node:fs';
import { dirname,resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { performance } from 'node:perf_hooks';
import { predictGrowth } from '../src/growth.ts';
import { validateDistribution } from '../src/domain.ts';

const asOf='2026-10-25';
function input(score,hours,regularity,days) {
  const examDate=new Date(Date.parse(asOf+'T00:00:00Z')+days*86400000).toISOString().slice(0,10);
  return {asOf,examDate,target:280,subjects:['mathematics','informatics','russian'].map((subject,i)=>({
    subject,mocks:[{date:asOf,score:Math.max(0,Math.min(100,score+(i===1?5:i===2?-5:0)))}],hoursPerWeek:hours,regularity}))};
}
for(let i=0;i<20;i++)predictGrowth(input(70,6,1,180));
const wall=[];let cpuMicros=0,cases=0,distributions=0;
for(let score=0;score<=100;score+=10)for(const hours of [0,6,40])for(const regularity of [0,0.5,1])for(const days of [0,180,730]) {
  const data=input(score,hours,regularity,days);const start=performance.now(),cpu=process.cpuUsage();
  const result=predictGrowth(data);const used=process.cpuUsage(cpu);cpuMicros+=used.user+used.system;
  wall.push(performance.now()-start);cases++;
  assert.equal(result.status,'uncalibrated_scenario');assert.equal(result.admissionProbability,null);
  for(const s of result.scenarios){
    validateDistribution(s.total,300);distributions++;
    assert.ok(s.targetScenarioMass>=-1e-12&&s.targetScenarioMass<=1+1e-12);
    for(const p of s.subjects){validateDistribution(p.distribution);distributions++;
      assert.ok(p.center>=0&&p.center<=100);
      if(hours===0||regularity===0||days===0)assert.equal(p.center,p.anchor.score);
      assert.ok(p.trajectory.every((t,i,a)=>i===0||t.center>=a[i-1].center));
    }
  }
  assert.ok(result.scenarios.every((s,i,a)=>i===0||s.median>=a[i-1].median));
}
wall.sort((a,b)=>a-b);
const result={status:'synthetic_grid_passed',empirical_validation:false,cases,distributions_checked:distributions,
  node:process.version,platform:process.platform,architecture:process.arch,
  config_sha256:createHash('sha256').update(readFileSync(new URL('../config/progress.scenarios.v1.json',import.meta.url))).digest('hex'),
  local_node_wall_ms:{median:wall[Math.floor(wall.length/2)],p95:wall[Math.ceil(wall.length*0.95)-1],max:wall.at(-1)},
  local_node_cpu_ms_per_case:cpuMicros/1000/cases,
  warning:'Local Node measurements, not Cloudflare isolate CPU or empirical EGE accuracy.'};
const output=resolve(process.argv[2]??'artifacts/ege-grid.json');mkdirSync(dirname(output),{recursive:true});
writeFileSync(output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
