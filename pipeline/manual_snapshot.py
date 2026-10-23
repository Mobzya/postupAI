"""Explicit manual fallback; never labels user-provided files as HTTP-verified."""
import argparse
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from .sources import SnapshotStore, digest, timestamp
from .validate import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-id', required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--obtained-at', required=True, help='ISO timestamp with timezone; declared by provider')
    parser.add_argument('--note', required=True)
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme != 'https' or parsed.hostname != 'admission.mephi.ru' or parsed.username or parsed.password:
        parser.error('An official MEPhI HTTPS source URL is required')
    obtained = datetime.fromisoformat(args.obtained_at)
    if obtained.tzinfo is None:
        parser.error('obtained-at must include timezone')
    data = args.file.read_bytes()
    sha = digest(data)
    store = SnapshotStore()
    # Caller-controlled source IDs never become filesystem components.
    filename = 'manual-' + sha + ('.pdf' if data.startswith(b'%PDF-') else '.html')
    target = store.directory / filename
    if not target.exists():
        target.write_bytes(data)
    item = dict(source_id=args.source_id, url=args.url, final_url=args.url, retrieved_at=args.obtained_at,
                recorded_at=timestamp(), http_status=None, content_type='application/pdf' if data.startswith(b'%PDF-') else 'text/html',
                sha256=sha, path=str(target.relative_to(ROOT)), bytes=len(data), retrieval_method='manual_user_provided_unverified',
                adapter_version='manual-v1', review_note=args.note)
    if not any(s['source_id']==args.source_id and s['sha256']==sha for s in store.manifest['snapshots']):
        store.manifest['snapshots'].append(item)
        store._persist()
    print('Manual snapshot recorded; provenance is provider-declared and requires review.')


if __name__ == '__main__':
    main()
