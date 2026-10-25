import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.ts';
import { MENU,PROMPTS } from '../src/ui.ts';
import release from '../config/bot.release.json' with {type:'json'};

const secret='synthetic-ui-secret-for-tests-only-0123456';
const env={TELEGRAM_WEBHOOK_SECRET:secret,DB:{prepare(){throw new Error('public flow must not use storage');}}};
let updateId=0;
async function call(text,reply,username=release.bot_username) {
  const body={update_id:++updateId,message:{text,chat:{id:777001,type:'private'},from:{id:777001,is_bot:false},
    ...(reply?{reply_to_message:{text:reply,from:{is_bot:true,username}}}:{})}};
  const response=await worker.fetch(new Request('https://example.invalid/telegram/webhook',{method:'POST',
    headers:{'Content-Type':'application/json','X-Telegram-Bot-Api-Secret-Token':secret},body:JSON.stringify(body)}),env);
  assert.equal(response.status,200);const data=await response.json();assert.ok(data.text.length<=4000);return data;
}
test('public path from start through button, search reply, card and comparison needs no profile',async()=>{
  const start=await call('/start');assert.deepEqual(start.reply_markup,MENU);
  const prompt=await call('🔎 Найти программу');assert.equal(prompt.text,PROMPTS.search);assert.equal(prompt.reply_markup.force_reply,true);
  const found=await call('ВШЭ математика',prompt.text);
  const ids=[...found.text.matchAll(/\/program ([a-f0-9]{8})/g)].map(m=>m[1]);assert.ok(ids.length>=2);
  assert.ok((await call(`/program ${ids[0]}`)).text.includes('Источник:'));
  assert.ok((await call(`/compare ${ids[0]} ${ids[1]}`)).text.includes('Сравнение записей'));
  assert.ok((await call('/save')).text.includes('выключено'));
});
test('rule and growth prompts accept replies only to this bot and expose model limitations',async()=>{
  const p=await call('🧮 Конкурсный балл');assert.equal(p.text,PROMPTS.score);
  assert.ok((await call('2026 09.03.04 бюджет мат=85 инф=90 рус=80 ид=5',p.text)).text.includes('260'));
  const e=await call('🎯 Сценарии ЕГЭ');assert.equal(e.text,PROMPTS.ege);
  const examDate=new Date(Date.now()+180*86400000).toISOString().slice(0,10);
  const result=await call(`${examDate} мат=70/6 инф=75/6 рус=65/3 цель=280`,e.text);
  assert.ok(result.text.includes('не являются проверенной'));
  const forged=await call('2026 09.03.04 бюджет мат=85 инф=90 рус=80 ид=5',p.text,'different_synthetic_bot');
  assert.ok(!forged.text.includes('Условный конкурсный балл:'));
});
test('unknown text and unavailable profile have actionable replies without capturing input',async()=>{
  const unknown=await call('synthetic unmatched input');assert.ok(unknown.text.includes('/help')||unknown.text.includes('Выберите'));
  assert.ok(!unknown.text.includes('synthetic unmatched input'));
  assert.ok((await call('🔐 Данные и профиль')).text.includes('выключено'));
  assert.ok((await call('/forecast')).text.includes('недоступна'));
});
