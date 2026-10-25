import test from 'node:test';
import assert from 'node:assert/strict';
import { initialSelection,packSelection,unpackSelection,subjectSelection,guidedCallback,guidedReply } from '../src/guided.ts';
import release from '../config/bot.release.json' with {type:'json'};

const buttons=view=>view.reply_markup.inline_keyboard?.flat()??[];
function press(view,label){const b=buttons(view).find(b=>b.text===label);assert.ok(b,`missing button: ${label}`);return guidedCallback(b.callback_data,view.text);}
function typed(view,value,username=release.bot_username){return guidedReply(value,{text:view.text,from:{is_bot:true,username}});}
function completeScores(){let v=press(subjectSelection(),'Ввести баллы →');for(const n of ['80','85','90'])v=typed(v,n);return v;}
function assertView(v){assert.ok(v.text.length<=4000);for(const b of buttons(v))if(b.callback_data)assert.ok(Buffer.byteLength(b.callback_data,'utf8')<=64);}

test('compact selections round-trip scores, olympiad declaration, year, institution and funding',()=>{
  const a=initialSelection();assert.deepEqual(unpackSelection(packSelection(a)),a);
  const b={...a,year:2026,mask:511,scores:[100,99,0,1,85,62,45,70,90],olympiad:'p',olympiadLevel:3,olympiadSubject:2,university:9,funding:'p'};
  assert.deepEqual(unpackSelection(packSelection(b)),b);assert.equal(packSelection(b).length,26);
  for(const raw of ['',packSelection(a).replace(/^7/,'5'),'7zz'+packSelection(a).slice(3),packSelection(a).slice(0,-1)+'z'])assert.equal(unpackSelection(raw),null);
  assert.throws(()=>packSelection({...a,scores:[-1,...a.scores.slice(1)]}));
});
test('subject buttons edit the selection and all generated payloads fit Telegram limits',()=>{
  const first=subjectSelection();assertView(first);
  const second=press(first,'Физика');assert.ok(buttons(second).some(b=>b.text==='✓ Физика'));
  const s=unpackSelection(buttons(second)[0].callback_data.split(':').at(-1));assert.equal(s.mask,15);
  assertView(press(first,'Выбрать год 2026'));
  let empty=first;for(const label of ['✓ Русский язык','✓ Математика','✓ Информатика'])empty=press(empty,label);
  assert.ok(press(empty,'Ввести баллы →').text.includes('Отметь хотя бы один'));
});
test('scores are entered one by one and invalid values do not advance or erase context',()=>{
  let v=press(subjectSelection(),'Ввести баллы →');assert.equal(v.reply_markup.force_reply,true);assert.ok(v.text.includes('«Русский язык»'));
  const invalid=typed(v,'101');assert.ok(invalid.text.startsWith('Нужно целое число'));assert.equal(invalid.reply_markup.force_reply,true);
  v=typed(invalid,'80');assert.ok(v.text.includes('Русский язык: 80'));assert.ok(v.text.includes('«Математика»'));
  v=typed(v,'85');v=typed(v,'90');assert.ok(v.text.includes('2 из 4'));assertView(v);
  assert.equal(typed(invalid,'80','different_synthetic_bot'),null);
  assert.equal(typed(invalid,'/start'),null);
});
test('winner or prize declaration, level and subject survive university and program navigation',()=>{
  let v=press(completeScores(),'Призёр');v=press(v,'Уровень 2');v=press(v,'Предмет диплома');v=press(v,'Информатика');
  assert.ok(v.text.includes('Уровень: 2'));v=press(v,'Выбрать вуз →');v=press(v,'МИФИ');assert.ok(v.text.includes('МИФИ'));
  let state=unpackSelection(buttons(v)[0].callback_data.split(':').at(-1));
  assert.deepEqual(state.scores.slice(0,3),[80,85,90]);assert.equal(state.olympiad,'p');assert.equal(state.olympiadLevel,2);assert.equal(state.olympiadSubject,2);
  v=press(v,'🔎 Найти по названию');assert.equal(v.reply_markup.force_reply,true);v=typed(v,'09.03.04');assert.ok(v.text.includes('Поиск: 09.03.04'));
  const program=buttons(v).find(b=>b.callback_data?.startsWith('gp1:p:'));assert.ok(program);
  v=guidedCallback(program.callback_data,v.text);assert.ok(v.text.includes('Диплом: призёр'));assert.ok(v.text.includes('не сверены'));
  assert.ok(buttons(v).some(b=>b.url?.startsWith('https://')));assertView(v);
  state=unpackSelection(buttons(v).find(b=>b.callback_data).callback_data.split(':').at(-1));assert.equal(state.olympiad,'p');
});
test('reference rules require an explicit request and never overwrite the target 2027 campaign',()=>{
  let v=press(completeScores(),'Нет диплома');v=press(v,'Все вузы');v=press(v,'По требованиям ЕГЭ');
  assert.ok(v.text.includes('Для кампании 2027'));assert.ok(!v.text.includes('сумма ЕГЭ 255'));
  v=press(v,'Посмотреть правила 2026');assert.ok(v.text.includes('2026'));assert.ok(v.text.includes('сумма ЕГЭ 255'));
  assert.equal(unpackSelection(buttons(v)[0].callback_data.split(':').at(-1)).year,2027);
  assert.ok(v.text.includes('не равен проходному'));assert.ok(!v.text.includes('%'));assertView(v);
});
test('pagination and search survive opening a card and returning to the same page',()=>{
  let v=press(subjectSelection(),'Баллы пока неизвестны');v=press(v,'Нет диплома');v=press(v,'Все вузы');
  v=press(v,'Дальше ›');assert.ok(v.text.includes('Страница 2/'));
  const p=buttons(v).find(b=>b.callback_data?.startsWith('gp1:p:'));v=guidedCallback(p.callback_data,v.text);
  v=press(v,'← Программы');assert.ok(v.text.includes('Страница 2/'));
  v=press(v,'🔎 Найти по названию');v=typed(v,'итмо 2026 AI360');assert.ok(v.text.includes('Поиск: итмо 2026 AI360'));
  const card=buttons(v).find(b=>b.callback_data?.startsWith('gp1:p:'));assert.ok(card);
  v=guidedCallback(card.callback_data,v.text);v=press(v,'← Программы');assert.ok(v.text.includes('Поиск: итмо 2026 AI360'));
});
test('score editing preserves the declared diploma and scope without a saved profile',()=>{
  let v=press(completeScores(),'Победитель');v=press(v,'Выбрать вуз →');v=press(v,'ВШЭ');v=press(v,'Изменить баллы');
  v=press(v,'Математика: 85');v=typed(v,'95');assert.ok(v.text.includes('ВШЭ'));
  const state=unpackSelection(buttons(v)[0].callback_data.split(':').at(-1));assert.equal(state.scores[1],95);assert.equal(state.olympiad,'w');
});
test('malformed callbacks and contradictory hidden scores fail closed',()=>{
  const s=initialSelection();for(const data of ['unknown','gp1:t:z:'+packSelection(s),'gp1:p:bad:'+packSelection(s),'x'.repeat(100)])assert.equal(guidedCallback(data),null);
  assert.throws(()=>packSelection({...s,mask:1,scores:[80,70,null,null,null,null,null,null,null]}));
});

test('home hides the step keyboard and a new selection has no values from the previous flow',()=>{
  let v=press(completeScores(),'Нет диплома');v=press(v,'Все вузы');v=press(v,'Главное меню');
  assert.equal(v.delivery,'send');assert.ok(v.reply_markup.keyboard);assert.equal(v.reply_markup.one_time_keyboard,true);
  assert.ok(!JSON.stringify(v.reply_markup).includes('gp1:'));
  assert.ok(initialSelection().scores.every(s=>s===null));assert.equal(initialSelection().olympiad,'u');
});
