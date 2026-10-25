"""Technical synthetic-only fault and loopback latency probe, not a human pilot."""
import concurrent.futures,datetime,json,os,platform,signal,statistics,subprocess,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SECRET='synthetic-pilot-probe-secret-0123456789'


def main():
    base='http://127.0.0.1:8789'
    p=subprocess.Popen([str(ROOT/'node_modules/.bin/wrangler'),'dev','--config','wrangler.bot.toml',
        '--local','--ip','127.0.0.1','--port','8789','--inspector-port','0',
        '--var','TELEGRAM_WEBHOOK_SECRET:'+SECRET,'--var','PROFILE_STORAGE_ENABLED:false'],
        cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    def http(body=None,secret=SECRET,content_type='application/json',path='/telegram/webhook'):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req=urllib.request.Request(base+path,data=body,headers={'Content-Type':content_type,'X-Telegram-Bot-Api-Secret-Token':secret})
        try:
            with opener.open(req,timeout=10) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.loads(error.read())
    def update(text,group=False):
        return json.dumps(dict(update_id=1,message=dict(text=text,chat=dict(id=777001,type='group' if group else 'private'),
            **{'from':dict(id=777001,is_bot=False)}))).encode()
    try:
        deadline=time.monotonic()+30
        while True:
            if p.poll() is not None:raise RuntimeError('Pilot probe workerd exited; details suppressed.')
            try:
                _,health=http(path='/health');assert health['profileStorageEnabled'] is False and health['forecasting'] is False;break
            except (urllib.error.URLError,TimeoutError):
                if time.monotonic()>deadline:raise RuntimeError('Pilot probe readiness timeout.') from None
                time.sleep(.1)
        faults={}
        for name,body,secret,mime,expected in [
            ('bad_secret',update('/start'),'wrong','application/json',401),
            ('malformed_json',b'{',SECRET,'application/json',400),
            ('oversized_body',b'x'*65537,SECRET,'application/json',413),
            ('wrong_content_type',update('/start'),SECRET,'text/plain',415),
            ('oversized_message',update('x'*4097),SECRET,'application/json',400)]:
            status,_=http(body,secret,mime);assert status==expected;faults[name]=status
        assert http(update('/start',group=True))[1]=={'ok':True};faults['group_ignored']=True
        assert 'Проверьте' in http(update('/ege 2000-01-01 мат=101/6'))[1]['text'];faults['invalid_growth_rejected']=True
        exam=(datetime.datetime.now(datetime.timezone.utc).date()+datetime.timedelta(days=180)).isoformat()
        commands=['/status','/search вшэ математика','/score 2026 09.03.04 бюджет мат=85 инф=90 рус=80 ид=5',
            '/ege '+exam+' мат=70/6 инф=75/6 рус=65/3 цель=280','/forecast']
        def sample(i):
            started=time.perf_counter();status,response=http(update(commands[i%len(commands)]));elapsed=(time.perf_counter()-started)*1000
            assert status==200 and response['method']=='sendMessage' and len(response['text'])<=4000
            return elapsed
        for i in range(10):sample(i)
        sequential=[sample(i) for i in range(100)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:parallel_samples=list(pool.map(sample,range(40)))
        def stats(values):
            ordered=sorted(values);return dict(n=len(values),median_ms=statistics.median(values),p95_ms=ordered[__import__('math').ceil(.95*len(values))-1],max_ms=max(values))
        result=dict(status='technical_rehearsal_passed',synthetic_only=True,human_pilot_completed=False,
            empirical_calibration=False,platform=platform.system(),fault_checks=faults,
            loopback_sequential=stats(sequential),loopback_four_clients=stats(parallel_samples),
            profile_storage=False,admission_probability=False,
            warning='Loopback HTTP latency in this workspace, not Telegram delivery SLA or Cloudflare CPU measurement.')
        path=ROOT/'artifacts/pilot-probe.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
    finally:
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()


if __name__=='__main__':main()
