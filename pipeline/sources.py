"""Offline snapshot IO: bounded HTTPS, robots, per-host pacing, no script execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

from .validate import ROOT

USER_AGENT = 'BALLNIK-research/0.2 (public university admission aggregates; no personal lists)'
MAX_BYTES = 12 * 1024 * 1024


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        old, new = urllib.parse.urlsplit(request.full_url), urllib.parse.urlsplit(newurl)
        if new.scheme != 'https' or new.hostname != old.hostname:
            raise ValueError('cross_origin_redirect_requires_review')
        return super().redirect_request(request, response, code, message, headers, newurl)


class SnapshotStore:
    def __init__(self, directory=None, delay=1.5):
        self.directory = Path(directory or ROOT / 'data/raw/mephi')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.directory / 'manifest.json'
        self.manifest = json.loads(self.manifest_path.read_text()) if self.manifest_path.exists() else {'schema_version': 1, 'snapshots': [], 'attempts': []}
        self.delay = max(1.0, delay)
        self.last_request = {}
        self.robots = {}
        self.opener = urllib.request.build_opener(SafeRedirect())

    def _request(self, url):
        host = urllib.parse.urlsplit(url).hostname
        elapsed = time.monotonic() - self.last_request.get(host, 0)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request[host] = time.monotonic()
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html,application/pdf,text/plain;q=0.9,*/*;q=0.5'})
        with self.opener.open(request, timeout=25) as response:
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('source_too_large')
            return data, response

    def _robots_allowed(self, url):
        parsed = urllib.parse.urlsplit(url)
        origin = f'{parsed.scheme}://{parsed.netloc}'
        if origin not in self.robots:
            robots_url = origin + '/robots.txt'
            try:
                data, response = self._request(robots_url)
                self._save('robots', robots_url, data, response)
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(data.decode('utf-8', errors='replace').splitlines())
                self.robots[origin] = parser
            except urllib.error.HTTPError as error:
                if error.code not in (404, 410):
                    raise ValueError('robots_unavailable_no_fetch') from None
                self.robots[origin] = None
        parser = self.robots[origin]
        return parser is None or parser.can_fetch(USER_AGENT, url)

    def _persist(self):
        write_json(self.manifest_path, self.manifest)

    def _save(self, source_id, url, data, response):
        sha = digest(data)
        mime = response.headers.get('Content-Type', '').split(';')[0]
        suffix = '.pdf' if mime == 'application/pdf' else '.html' if 'html' in mime else '.txt'
        filename = f'{source_id}-{sha[:16]}{suffix}'
        path = self.directory / filename
        if not path.exists():
            path.write_bytes(data)
        existing = next((s for s in self.manifest['snapshots'] if s['source_id'] == source_id and s['url'] == url and s['sha256'] == sha), None)
        if existing:
            return existing
        item = dict(source_id=source_id, url=url, final_url=response.url, retrieved_at=timestamp(),
                    http_status=response.status, content_type=mime, sha256=sha,
                    path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                    bytes=len(data), retrieval_method='https', adapter_version='fetch-v1')
        self.manifest['snapshots'].append(item)
        self._persist()
        return item

    def fetch(self, source_id, url, refresh=False):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('public_https_required')
        existing = [s for s in self.manifest['snapshots'] if s['source_id'] == source_id and s['url'] == url]
        if existing and not refresh:
            self.read(existing[-1])  # Also checks that cached bytes still match the hash.
            return existing[-1]
        attempt = dict(source_id=source_id, url=url, attempted_at=timestamp())
        try:
            if not self._robots_allowed(url):
                raise ValueError('robots_disallowed')
            data, response = self._request(url)
            item = self._save(source_id, url, data, response)
            attempt.update(status='success', sha256=item['sha256'])
            return item
        except (urllib.error.URLError, ValueError, TimeoutError) as error:
            attempt.update(status='error', error=type(error).__name__, reason=str(error)[:200])
            raise
        finally:
            self.manifest['attempts'].append(attempt)
            self._persist()

    @staticmethod
    def read(snapshot):
        path = Path(snapshot['path'])
        if not path.is_absolute():
            path = ROOT / path
        data = path.read_bytes()
        if digest(data) != snapshot['sha256']:
            raise ValueError('snapshot_hash_mismatch')
        return data
