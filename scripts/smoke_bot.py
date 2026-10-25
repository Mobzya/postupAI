"""Stateless product flow against real local workerd; synthetic messages only."""
import datetime,json,os,re,signal,subprocess,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SECRET='synthetic-stateless-smoke-secret-0123456789'


def main():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));base='http://127.0.0.1:8789'
    p=subprocess.Popen([str(ROOT/'node_modules/.bin/wrangler'),'dev','--config','wrangler.bot.toml',
        '--local','--ip','127.0.0.1','--port','8789','--inspector-port','0',
        '--var','TELEGRAM_WEBHOOK_SECRET:'+SECRET,'--var','PROFILE_STORAGE_ENABLED:false'],
        cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    try:
        deadline=time.monotonic()+30
        while True:
            if p.poll() is not None:raise RuntimeError('Stateless workerd exited; output suppressed.')
            try:
                with opener.open(base+'/health',timeout=1) as response:health=json.load(response)
                assert health['profileStorageEnabled'] is False and health['forecasting'] is False
                break
            except (urllib.error.URLError,TimeoutError):
                if time.monotonic()>deadline:raise RuntimeError('Stateless workerd readiness timeout.') from None
                time.sleep(.1)
        username=json.loads((ROOT/'config/bot.release.json').read_text())['bot_username'];sequence=0
        def call(text,reply=None):
            nonlocal sequence
            sequence+=1;message=dict(text=text,chat=dict(id=777001,type='private'),**{'from':dict(id=777001,is_bot=False)})
            if reply:message['reply_to_message']=dict(text=reply,**{'from':dict(is_bot=True,username=username)})
            req=urllib.request.Request(base+'/telegram/webhook',data=json.dumps(dict(update_id=sequence,message=message)).encode(),
                headers={'Content-Type':'application/json','X-Telegram-Bot-Api-Secret-Token':SECRET})
            with opener.open(req,timeout=10) as response:r=json.load(response)
            assert r['method']=='sendMessage' and len(r['text'])<=4000
            return r
        assert call('/start')['reply_markup']['keyboard']
        prompt=call('🔎 Найти программу');assert prompt['reply_markup']['force_reply']
        found=call('ВШЭ математика',prompt['text']);ids=re.findall(r'/program ([a-f0-9]{8})',found['text'])
        assert len(ids)>=2 and 'Источник:' in call('/program '+ids[0])['text']
        assert 'Сравнение записей' in call('/compare '+' '.join(ids[:2]))['text']
        prompt=call('🧮 Конкурсный балл')
        assert '260' in call('2026 09.03.04 бюджет мат=85 инф=90 рус=80 ид=5',prompt['text'])['text']
        prompt=call('🎯 Сценарии ЕГЭ')
        exam=(datetime.datetime.now(datetime.timezone.utc).date()+datetime.timedelta(days=180)).isoformat()
        assert 'не являются проверенной' in call(exam+' мат=70/6 инф=75/6 рус=65/3 цель=280',prompt['text'])['text']
        assert 'недоступна' in call('/forecast')['text']
        assert 'выключено' in call('/profile')['text'] and 'выключено' in call('/save')['text']
        print('PASS stateless workerd: menu, prompts, search, cards, compare, score, EGE, privacy, forecast gate.')
    finally:
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()


if __name__=='__main__':main()
