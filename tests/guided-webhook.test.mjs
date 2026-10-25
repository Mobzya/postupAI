import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.ts';
import release from '../config/bot.release.json' with {type:'json'};

const secret='synthetic-guided-webhook-secret-0123456789';
const env={TELEGRAM_WEBHOOK_SECRET:secret,DB:{prepare(){throw new Error('guided flow must not persist data');}}};
let id=0;
async function call(update){const r=await worker.fetch(new Request('https://example.invalid/telegram/webhook',{method:'POST',
  headers:{'Content-Type':'application/json','X-Telegram-Bot-Api-Secret-Token':secret},body:JSON.stringify({update_id:++id,...update})}),env);
  assert.equal(r.status,200);return r.json();}
const message=text=>({message:{text,chat:{id:777001,type:'private'},from:{id:777001,is_bot:false}}});
const callback=(data,text,patch={})=>({callback_query:{id:'synthetic-callback',data,from:{id:777001,is_bot:false},
  message:{message_id:101,text,chat:{id:777001,type:'private'},from:{is_bot:true,username:release.bot_username}},...patch}});
const button=(r,text)=>r.reply_markup.inline_keyboard.flat().find(b=>b.text===text);

test('real webhook path supports inline callbacks and sequential numeric replies without D1',async()=>{
  const start=await call(message('/start'));assert.equal(start.reply_markup.keyboard.length,3);
  let r=await call(message('🎓 Подобрать программы'));assert.ok(r.text.includes('1 из 4'));
  r=await call(callback(button(r,'Ввести баллы →').callback_data,r.text));assert.equal(r.method,'sendMessage');assert.equal(r.reply_markup.force_reply,true);
  for(const number of ['80','85','90']){
    const u=message(number);u.message.reply_to_message={text:r.text,from:{is_bot:true,username:release.bot_username}};r=await call(u);
  }
  assert.ok(r.text.includes('2 из 4'));
  r=await call(callback(button(r,'Нет диплома').callback_data,r.text));assert.equal(r.method,'editMessageText');assert.equal(r.message_id,101);
  r=await call(callback(button(r,'Все вузы').callback_data,r.text));assert.ok(r.text.includes('4 из 4'));assert.ok(r.text.includes('вероятности'));
});
test('callbacks from groups, another bot or another user do not access storage or send messages',async()=>{
  const r=await call(message('/pick'));const data=button(r,'Ввести баллы →').callback_data;
  const group=callback(data,r.text);group.callback_query.message.chat.type='group';
  const foreign=callback(data,r.text);foreign.callback_query.message.from.username='different_synthetic_bot';
  const mismatch=callback(data,r.text);mismatch.callback_query.from.id=777002;
  for(const u of [group,foreign,mismatch])assert.deepEqual(await call(u),{ok:true});
});
test('a stale or malformed button is acknowledged with a recovery action, not retried indefinitely',async()=>{
  const r=await call(callback('broken','Synthetic old view'));
  assert.equal(r.method,'answerCallbackQuery');assert.equal(r.callback_query_id,'synthetic-callback');assert.ok(r.text.includes('/pick'));
});
