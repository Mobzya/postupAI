"""Run Telegram long polling against a local stateless workerd.

Secrets stay in ignored .dev.vars/environment. Updates, offsets, chat IDs and
message text exist only in memory. Stopping the process stops bot responses.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_METHODS = {'getMe', 'getWebhookInfo', 'getUpdates', 'sendMessage', 'setMyCommands'}
COMMANDS = [
    {'command': 'start', 'description': 'Начать работу'},
    {'command': 'status', 'description': 'Текущий этап и результаты'},
    {'command': 'sources', 'description': 'Официальные источники вузов'},
    {'command': 'programs', 'description': 'Состояние каталога программ'},
    {'command': 'search', 'description': 'Поиск: вуз, название или код'},
    {'command': 'universities', 'description': 'Покрытие десяти вузов'},
    {'command': 'forecast', 'description': 'Доступность прогноза'},
    {'command': 'profile', 'description': 'Состояние сохранения профиля'},
    {'command': 'delete_data', 'description': 'Сведения об удалении данных'},
]


class BotError(Exception):
    def __init__(self, message, *, retryable=False, retry_after=2):
        super().__init__(message)
        self.retryable, self.retry_after = retryable, retry_after


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args):
        return None


def credentials():
    local = {}
    path = ROOT / '.dev.vars'
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                local[key.strip()] = value.strip().strip('"\'')
    values = {key: os.environ.get(key) or local.get(key, '')
              for key in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_WEBHOOK_SECRET')}
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', values['TELEGRAM_BOT_TOKEN']):
        raise BotError('Missing or invalid TELEGRAM_BOT_TOKEN; value suppressed.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', values['TELEGRAM_WEBHOOK_SECRET']):
        raise BotError('Missing or invalid TELEGRAM_WEBHOOK_SECRET; value suppressed.')
    return values


class BotAPI:
    def __init__(self, token):
        self._token = token
        self.opener = urllib.request.build_opener(NoRedirect())

    def call(self, method, payload=None):
        if method not in ALLOWED_METHODS:
            raise BotError('Unsupported Bot API method.')
        timeout = 35 if method == 'getUpdates' else 20
        request = urllib.request.Request('https://api.telegram.org/bot'+self._token+'/'+method,
            data=json.dumps(payload or {}).encode(), headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000: raise BotError('Bot API response too large; content suppressed.')
                result = json.loads(raw)
        except urllib.error.HTTPError as error:
            if error.code == 409:
                raise BotError('Another polling instance or webhook is active; local bot stopped.') from None
            if error.code in (401, 404):
                raise BotError('Telegram rejected bot credentials; value suppressed.') from None
            if error.code == 403 and method == 'sendMessage':
                raise BotError('Reply is not deliverable to this chat.') from None
            raise BotError(f'Bot API HTTP {error.code}; details suppressed.',
                           retryable=error.code==429 or error.code>=500) from None
        except (urllib.error.URLError, TimeoutError, ValueError):
            raise BotError('Bot API connection failed; details suppressed.',retryable=True) from None
        if not isinstance(result,dict) or result.get('ok') is not True:
            raise BotError('Telegram rejected request; response suppressed.')
        return result.get('result')


def check_identity(bot, release):
    identity = bot.call('getMe')
    if not isinstance(identity,dict) or identity.get('is_bot') is not True or identity.get('username') != release['bot_username']:
        raise BotError('Bot identity differs from config/bot.release.json; no updates consumed.')
    webhook = bot.call('getWebhookInfo')
    if not isinstance(webhook,dict) or webhook.get('url'):
        raise BotError('A webhook is configured. Local runner does not delete it or consume updates.')
    return identity['username']


def worker_call(base_url, path, payload=None, secret=None):
    # Loopback is the only destination permitted for the local no-proxy client.
    if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}',base_url):
        raise BotError('Only loopback Worker URLs are allowed.')
    headers = {'Content-Type': 'application/json'}
    if secret: headers['X-Telegram-Bot-Api-Secret-Token'] = secret
    request = urllib.request.Request(base_url+path,
        data=None if payload is None else json.dumps(payload).encode(),headers=headers)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        with opener.open(request,timeout=10) as response:
            return json.load(response)
    except (urllib.error.URLError,TimeoutError,ValueError):
        raise BotError('Local Worker request failed; update content suppressed.',retryable=True) from None


def handle_update(update, bot, base_url, secret):
    reply = worker_call(base_url,'/telegram/webhook',update,secret)
    if reply == {'ok': True}: return
    if (not isinstance(reply,dict) or reply.get('method')!='sendMessage'
        or not isinstance(reply.get('text'),str) or not isinstance(reply.get('chat_id'),int)):
        raise BotError('Unexpected local Worker response; content suppressed.')
    bot.call('sendMessage',{'chat_id':reply['chat_id'],'text':reply['text']})


def poll_once(bot, base_url, secret, offset):
    updates = bot.call('getUpdates',{'offset':offset,'timeout':20,'limit':20,'allowed_updates':['message']})
    if not isinstance(updates,list): raise BotError('Invalid update batch; content suppressed.')
    next_offset = offset
    for update in updates:
        if not isinstance(update,dict) or type(update.get('update_id')) is not int:
            raise BotError('Invalid update identity; content suppressed.')
        try:
            handle_update(update,bot,base_url,secret)
        except BotError as error:
            if error.retryable: return next_offset, True
            # A user may block the bot between an incoming message and its reply.
            if str(error)!='Reply is not deliverable to this chat.': raise
        next_offset = max(next_offset,update['update_id']+1)
    return next_offset, False


def run_local(bot, release, secret):
    with socket.socket() as port_socket:
        port_socket.bind(('127.0.0.1',0)); port=port_socket.getsockname()[1]
    base_url=f'http://127.0.0.1:{port}'
    # Actual credentials are read by Wrangler from .dev.vars, never CLI arguments.
    process=subprocess.Popen([str(ROOT/'node_modules/.bin/wrangler'),'dev','--config',
        str(ROOT/'wrangler.bot.toml'),'--local','--ip','127.0.0.1','--port',str(port),
        '--inspector-port','0'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    def stop(_signum,_frame): raise KeyboardInterrupt
    previous_handlers={s:signal.signal(s,stop) for s in (signal.SIGTERM,signal.SIGINT)}
    try:
        deadline=time.monotonic()+40
        while True:
            if process.poll() is not None: raise BotError('Local Worker exited during startup.')
            try:
                health=worker_call(base_url,'/health')
                if (health.get('version')!=release['version'] or health.get('profileStorageEnabled') is not False
                    or health.get('forecasting') is not False):
                    raise BotError('Local Worker release or profile mode mismatch.')
                if worker_call(base_url,'/telegram/webhook',{'update_id':0},secret)!={'ok':True}:
                    raise BotError('Local Worker authentication check failed.')
                break
            except BotError as error:
                if not error.retryable: raise
                if time.monotonic()>deadline: raise BotError('Local Worker readiness timeout.') from None
                time.sleep(.1)
        bot.call('setMyCommands',{'commands':COMMANDS})
        print(json.dumps(dict(status='running',bot_username=release['bot_username'],stage=release['stage'],
                              version=release['version'],profile_storage=False,mode='local_long_polling')),flush=True)
        offset=0
        while process.poll() is None:
            try:
                offset,retry=poll_once(bot,base_url,secret,offset)
                if retry: time.sleep(2)
            except BotError as error:
                if not error.retryable: raise
                print('Temporary Telegram connection failure; retrying. No message content logged.',flush=True)
                time.sleep(error.retry_after)
        raise BotError('Local Worker stopped; polling ended.')
    finally:
        for sig,handler in previous_handlers.items(): signal.signal(sig,handler)
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Verify identity and webhook state without consuming updates')
    args=parser.parse_args()
    try:
        values=credentials();release=json.loads((ROOT/'config/bot.release.json').read_text())
        bot=BotAPI(values['TELEGRAM_BOT_TOKEN']);username=check_identity(bot,release)
        if args.check:
            print(json.dumps(dict(status='bot_verified',bot_username=username,webhook_configured=False,
                                  mode='local_long_polling_ready')));return
        (ROOT/'.wrangler').mkdir(exist_ok=True)
        with (ROOT/'.wrangler/local-bot.lock').open('w') as lock:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise BotError('Local polling is already running in this workspace.') from None
            run_local(bot,release,values['TELEGRAM_WEBHOOK_SECRET'])
    except BotError as error: raise SystemExit(str(error)) from None
    except KeyboardInterrupt: print('Local bot stopped; no profiles or messages saved.')


if __name__=='__main__':main()
