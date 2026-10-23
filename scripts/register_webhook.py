"""Register an explicitly requested webhook; credentials never enter argv or logs."""
import argparse
import getpass
import json
import re
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True, help='https://YOUR-WORKER.workers.dev/telegram/webhook')
    args = parser.parse_args()
    parsed = urllib.parse.urlparse(args.url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != '/telegram/webhook':
        parser.error('Use a public HTTPS webhook URL ending in /telegram/webhook, without credentials or query.')
    token = getpass.getpass('Bot token (hidden): ').strip()
    secret = getpass.getpass('Existing TELEGRAM_WEBHOOK_SECRET (hidden): ').strip()
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token) or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', secret):
        raise SystemExit('Invalid credential format; nothing sent.')
    request = urllib.request.Request(
        f'https://api.telegram.org/bot{token}/setWebhook',
        data=json.dumps({'url': args.url, 'secret_token': secret, 'allowed_updates': ['message'], 'max_connections': 2}).encode(),
        headers={'Content-Type': 'application/json'}, method='POST',
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            result = json.load(response)
        if result.get('ok') is not True:
            raise SystemExit('Telegram rejected registration; check settings. Response suppressed to protect credentials.')
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise SystemExit('Webhook registration failed; credentials and request URL suppressed.') from None
    print('Webhook registered. Test /start and /delete_data in a private chat.')


if __name__ == '__main__':
    main()
