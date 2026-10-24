"""Refetch reviewed source URLs without silently replacing versioned snapshots."""
import argparse,json
from pathlib import Path
from .sources import SnapshotStore,write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--cache-root',type=Path,required=True);p.add_argument('--refresh',action='store_true');a=p.parse_args()
    rows=json.loads(a.inventory.read_text());stores={};results=[]
    for row in rows:
        source=row.get('snapshot',row);ident=row['institution_id'];url=source.get('url')
        if not url or not source.get('source_id'):continue
        store=stores.setdefault(ident,SnapshotStore(a.cache_root/ident))
        try:
            snapshot=store.fetch(source['source_id'],url,refresh=a.refresh)
            expected=source.get('sha256')
            status='matching_snapshot' if expected==snapshot['sha256'] else 'new_snapshot_requires_review'
            results.append(dict(institution_id=ident,source_id=source['source_id'],status=status,
                sha256=snapshot['sha256'],expected_sha256=expected))
        except Exception as error:
            results.append(dict(institution_id=ident,source_id=source['source_id'],status='unavailable',reason=str(error)[:180]))
    write_json(a.cache_root/'fetch_results.json',results)
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':main()
