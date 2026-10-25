import release from '../config/bot.release.json' with {type:'json'};

export const MENU={keyboard:[['🎓 Подобрать программы'],['📚 Каталог','📈 Прогресс ЕГЭ'],['ℹ️ Возможности']],
  resize_keyboard:true,is_persistent:false,one_time_keyboard:true,input_field_placeholder:'Выберите действие или введите команду'};
export const PROMPTS={
  search:'Найти программу\nОтветьте на это сообщение названием, кодом или вузом: например, ВШЭ математика. Каталог частичный.',
  ege:'Сценарии ЕГЭ\nОтветьте датой экзамена и баллами/часами на каждый предмет:\n2027-06-01 мат=70/6 инф=75/6 рус=65/3 цель=280 рег=0.8\nРегулярность 0–1. Пробник по умолчанию сегодня; можно добавить пробник=YYYY-MM-DD. Темпы — некалиброванные гипотезы. Результаты не сохраняются.',
  score:'Конкурсный балл МИФИ\nОтветьте годом, кодом, категорией и баллами:\n2026 09.03.04 бюджет мат=85 инф=90 рус=80 ид=5\nВместо бюджет можно платно. Условия ИД проверяет вуз, /achievements — примеры.',
  rules:'Правила МИФИ по году\nОтветьте, например: 2026 09.03.04 бюджет\nГод и категория обязательны; другие кампании автоматически не подставляются. /achievements — отдельные условия ИД.',
  history:'История опубликованных порогов\nОтветьте названием вуза, программы или кодом: например, МИФИ 09.03.04. Метрики и категории источников могут различаться.',
  compare:'Сравнение программ\nОтветьте 2–3 кодами карточек из результатов /search: например, код1 код2. Сравнение показывает доступные сведения, без ранжирования шансов.',
};
export type Prompt=keyof typeof PROMPTS;
const buttons:Record<string,string>={'📚 Каталог':'/programs','🔎 Найти программу':'/search','🎯 Сценарии ЕГЭ':'/ege',
  '🎓 Подобрать программы':'/pick','📈 Прогресс ЕГЭ':'/ege','ℹ️ Возможности':'/help',
  '🧮 Конкурсный балл':'/score','📋 Правила и ИД':'/rules','📊 История порогов':'/history','⚖️ Сравнить программы':'/compare',
  '📎 Источники':'/sources','ℹ️ Статус':'/status','🔐 Данные и профиль':'/profile'};
export function resolveInput(text:string,reply?:unknown):string {
  if(text.trim().startsWith('/'))return text.trim();
  if(Object.hasOwn(buttons,text.trim()))return buttons[text.trim()]!;
  if(reply&&typeof reply==='object') {
    const r=reply as {text?:unknown;from?:{is_bot?:unknown;username?:unknown}};
    if(r.from?.is_bot===true&&r.from.username===release.bot_username&&typeof r.text==='string') {
      for(const [mode,prompt] of Object.entries(PROMPTS))if(r.text===prompt)return `/${mode} ${text.trim()}`;
    }
  }
  return '/help';
}
export function forceReply() {return {force_reply:true,selective:true,input_field_placeholder:'Ответьте по примеру в сообщении'};}
export const HELP='Выберите действие кнопкой или введите команду.\n'+
  '/pick — пошагово: баллы, олимпиада, вуз и программы.\n'+
  '/search — поиск, /program — карточка, /compare — сравнение.\n/ege — сценарии ЕГЭ, /score — сумма МИФИ, /rules и /achievements — условия.\n'+
  '/history — опубликованная история, /baseline — эксперимент порогов.\n/forecast — готовность вероятностей, /model — допущения, /sources — источники.\n'+
  '/profile и /delete_data — сведения о хранении. Профили и избранное пока выключены.\n'+
  'Бот обрабатывает ваш ввод для ответа без сохранения в профиле. Переписку хранит Telegram; не отправляйте документы и лишние личные сведения.';
