"""Preliminary ten-university source map; linked does not mean fetched or verified."""
import argparse
import json
import re
from urllib.parse import urljoin

from .mephi import document, text
from .sources import SnapshotStore, write_json
from .validate import ROOT


def build_matrix():
    legacy = json.loads((ROOT/'data/source_registry.json').read_text())
    probes = SnapshotStore(ROOT/'data/raw/source_probes')
    mephi = SnapshotStore()
    results = []
    patterns = dict(archive=r'архив|прошлых лет|прошлые годы', cutoffs=r'проходн',
                    places=r'количество мест|контрольные цифры|план при[её]ма',
                    lists=r'конкурсные списки|списки поступающих|сведения о зачислении|приказы',
                    rules=r'правила при[её]ма|документы')
    for source in legacy['sources']:
        ident = source['institution_id']
        available = [s for s in probes.manifest['snapshots'] if s['source_id']==source['id']]
        failures = [a for a in probes.manifest['attempts'] if a['source_id']==source['id'] and a['status']=='error']
        row = dict(institution_id=ident, institution_name=source['institution_name'], entry_url=source['url'],
                   access_status='not_read', source_verified=False, format='unknown', features={}, parsing_complexity='unknown',
                   archive='unknown', cutoffs='unknown', places='unknown', lists='unknown', rules_notes='Rules document not read.')
        if ident=='mephi':
            available = [s for s in mephi.manifest['snapshots'] if s['source_id']=='mephi-history']
        if available:
            snapshot=available[-1]
            store=mephi if ident=='mephi' else probes
            root=document(store.read(snapshot))
            titles=root.xpath('//title/text()')
            row.update(access_status='http_read',source_verified=True, source_snapshot=snapshot,
                       page_title=titles[0].strip() if titles else None,
                       format='HTML with tables' if root.xpath('//table') else 'HTML; linked documents not inspected',
                       parsing_complexity='medium (preliminary; deep source not validated)')
            for feature, pattern in patterns.items():
                links=[]
                for a in root.xpath('//a[@href]'):
                    label=text(a)
                    if re.search(pattern,label,re.I):
                        url=urljoin(snapshot['url'],a.get('href'))
                        if url.startswith('https://') and (label,url) not in [(x['label'],x['url']) for x in links]:
                            links.append(dict(label=label,url=url,verification='linked_not_read'))
                row['features'][feature]=links[:6]
                row[feature]='linked_not_read' if links else 'not_found_on_entry_page'
            content=text(root)
            terms=[term for term in ['ДВИ','грант','олимпиад','базовое высшее'] if (re.search(r'\bДВИ\b',content,re.I) if term=='ДВИ' else term.casefold() in content.casefold())]
            row['rules_notes']='Entry page mentions: '+', '.join(terms)+'. Exact rules require document review.' if terms else 'No rules conclusions from entry page.'
            visible=document(store.read(snapshot))
            for node in visible.xpath('//script|//style'):
                node.drop_tree()
            if len(text(visible)) < 400 and 'enable javascript' in text(visible).casefold():
                row.update(access_status='javascript_shell_only', source_verified=False,
                    format='JavaScript application shell; admission content not read',
                    parsing_complexity='high/unknown; locate public document endpoints without authorization')
            if ident=='nsu':
                row['lists']='public_list_interface_read_rows_not_collected'
                row['format']='HTML with client templates; applicant rows not fetched'
                row['parsing_complexity']='medium/high; dynamic list interface, find separate admissions archive and documents'
        elif failures:
            row.update(access_status='failed',source_verified=False, failure=failures[-1],
                       parsing_complexity='high/unknown until public source is reachable')
        if ident=='mephi':
            row.update(archive='read_2015_2025',cutoffs='read_2015_2025',places='read_2026',
                format='Static HTML tables with year tabs/rowspan; linked PDF',
                rules_notes='2026 rules PDF read: campus, form, profile, funding and quota distinguish competitions; rules engine not implemented.',
                parsing_complexity='medium; semantics and historical group reconciliation are difficult')
        results.append(row)
    sources = [s for s in mephi.manifest['snapshots'] if s['source_id']!='robots']
    registry=dict(schema_version=2,serialization='JSON subset of YAML 1.2; readable with json or any YAML 1.2 parser',
        scope=dict(pilot='mephi',campus='mephi-moscow',catalog_campaign=2026,history_years=list(range(2015,2026))),
        universities=results,mephi_sources=sources,
        note='source_verified means the listed HTTP response was actually read, not that every linked document or numerical claim was verified.')
    write_json(ROOT/'data/source_registry.yaml',registry)
    write_json(ROOT/'data/normalized/university_source_matrix.json',results)
    lines=['# Карта официальных источников десяти вузов','',
        'Предварительная разведка. «Ссылка найдена» не означает, что целевой документ прочитан.',
        'Детальные снимки, ссылки и статусы: `data/source_registry.yaml` (JSON-совместимый YAML 1.2).','',
        '| Вуз | Фактически прочитано | Формат | Архив / проходные | Места | Списки | Правила / особенности | Сложность |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in results:
        lines.append(f"| [{r['institution_name']}]({r['entry_url']}) | {r['access_status']} | {r['format']} | {r['archive']} / {r['cutoffs']} | {r['places']} | {r['lists']} | {r['rules_notes']} | {r['parsing_complexity']} |")
    lines.extend(['','У остальных девяти вузов не проверялась полнота архивов, не выгружались персональные конкурсные списки и не реализованы парсеры.',
        'Сбой robots или перенаправление на другой origin не обходились. Такие источники не объявлены прочитанными.',
        'Состояния HTTP и содержимого относятся к сохранённому срезу, а не гарантируют доступность в будущем.',''])
    (ROOT/'docs/UNIVERSITY_SOURCE_MATRIX.md').write_text('\n'.join(lines))
    return registry


if __name__=='__main__':
    build_matrix()
    print('Source registry and preliminary matrix generated from captured responses.')
