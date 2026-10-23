"""Actual local workerd + D1 integration check with synthetic identity and secrets."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SECRET = 'synthetic-webhook-secret-for-tests-only'
HMAC = 'synthetic-hmac-key-for-tests-only-12345'


def main():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = 'http://127.0.0.1:8788'
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen([
            str(ROOT / 'node_modules/.bin/wrangler'), 'dev', '--local', '--ip', '127.0.0.1',
            '--port', '8788', '--inspector-port', '0',
            '--var', f'TELEGRAM_WEBHOOK_SECRET:{SECRET}', '--var', f'USER_ID_HMAC_KEY:{HMAC}',
        ], cwd=ROOT, stdout=log, stderr=log, start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None:
                    raise RuntimeError('local Wrangler server exited; no public deployment performed')
                try:
                    with opener.open(base + '/health', timeout=1) as response:
                        health = json.load(response)
                    assert health['forecasting'] is False
                    break
                except (urllib.error.URLError, TimeoutError):
                    if time.monotonic() > deadline:
                        raise RuntimeError('local Wrangler readiness timeout') from None
                    time.sleep(.1)
            update_id = time.time_ns() % 1_000_000_000_000

            def call(command):
                nonlocal update_id
                update_id += 1
                body = {'update_id': update_id, 'message': {
                    'text': command, 'chat': {'id': 777001, 'type': 'private'},
                    'from': {'id': 777001, 'is_bot': False},
                }}
                request = urllib.request.Request(
                    base + '/telegram/webhook', data=json.dumps(body).encode(),
                    headers={'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': SECRET},
                )
                with opener.open(request, timeout=10) as response:
                    return json.load(response)

            assert call('/start')['method'] == 'sendMessage'
            assert 'Профиль создан' in call('/profile')['text']
            assert 'недоступен' in call('/forecast')['text']
            assert 'удалены' in call('/delete_data')['text']
            assert 'профиля нет' in call('/profile')['text']
            print('PASS: actual local workerd/D1 HTTP smoke: health, start, profile, forecast refusal, deletion.')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


if __name__ == '__main__':
    main()
