"""Versioned catalog observations with explicit coverage denominators.

Git contains compact structural excerpts / extracted PDF text, not full new
source pages. Parent hashes always refer to the original downloaded document.
"""
import argparse
from collections import Counter,defaultdict
import copy
import json
from pathlib import Path
import subprocess
from lxml import etree,html

from .catalog_adapters import VERSION,parse_html,parse_spbu,parse_msu,record
from .mephi import parse_catalog
from .sources import SnapshotStore,digest,write_json
from .validate import ROOT,require

OUT=ROOT/'data/normalized/catalog_v1'
INPUTS=ROOT/'data/catalog_inputs'
SUPPORTED={'hse-catalog-programs','hse-catalog-seats','innopolis-catalog-programs','nsu-catalog-programs',
           'bmstu-catalog-mytishchi','cu-catalog-programs','mephi-catalog-programs',
           'msu-catalog-seats','spbu-catalog-programs-pdf'}


def materialize():
    inventory=json.loads((OUT/'source_inventory.json').read_text());result=[]
    for row in inventory:
        if row['status']!='fetched' or row['source_id'] not in SUPPORTED:continue
        source=copy.deepcopy(row['snapshot']);source['institution_id']=row['institution_id']
        raw=SnapshotStore.read(source);ident=row['institution_id'];sid=row['source_id']
        if sid=='spbu-catalog-programs-pdf':
            xml=subprocess.run(['pdftotext','-bbox-layout',str(ROOT/source['path']),'-'],capture_output=True,check=True).stdout
            doc=etree.fromstring(xml);content=[]
            for page_i,page in enumerate(doc.xpath('//*[local-name()="page"]'),1):
                for i,b in enumerate(page.xpath('.//*[local-name()="block"]')):
                    if 265<=float(b.get('xMin'))<440 and float(b.get('xMax'))<442:
                        content.append(dict(text=' '.join(b.xpath('.//*[local-name()="word"]/text()')),
                            x0=b.get('xMin'),x1=b.get('xMax'),y0=b.get('yMin'),y1=b.get('yMax'),locator=f'page={page_i}; block={i+1}'))
                for i,w in enumerate(page.xpath('.//*[local-name()="word"]')):
                    if (440<float(w.get('xMin'))<490 and w.text in ('очная','очно-заочная','заочная')) or (
                        float(w.get('xMin'))<80 and __import__('re').fullmatch(r'\d{2}\.(03|05)\.\d{2}',w.text or '')):
                        content.append(dict(text=w.text,x0=w.get('xMin'),x1=w.get('xMax'),y0=w.get('yMin'),y1=w.get('yMax'),locator=f'page={page_i}; word={i+1}'))
            representation='pdftotext-bbox-structural-excerpt'
        elif sid=='msu-catalog-seats':
            content=subprocess.run(['pdftotext','-raw',str(ROOT/source['path']),'-'],capture_output=True,text=True,check=True).stdout
            representation='pdftotext-raw'
        else:
            root=html.fromstring(raw,parser=html.HTMLParser(encoding='utf-8',no_network=True))
            if sid=='hse-catalog-programs':nodes=root.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," events ")]')
            elif sid=='hse-catalog-seats':nodes=root.xpath('//h1|//table')
            elif ident=='mephi':nodes=root.xpath('//*[contains(@class,"field-name-body")]//table')
            elif ident=='innopolis':nodes=root.xpath('//a[contains(concat(" ",normalize-space(@class)," ")," subject-card ")]')
            elif ident=='nsu':nodes=[a for a in root.xpath('//a[@href]') if a.xpath('.//*[starts-with(@field,"text")]') or a.get('href','').rstrip('/').endswith(('/ai','/mechatronics'))]
            elif ident=='bmstu':nodes=root.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," direction-list ")]')
            elif ident=='cu':nodes=[n for n in root.xpath('//h3') if ' '.join(n.text_content().split()) in ('Искусственный интеллект','Бизнес и аналитика','Разработка','Дизайн')]
            else:raise ValueError('unsupported_materialization_source')
            wrapper=html.Element('html');body=etree.SubElement(wrapper,'body')
            for n in nodes:
                n=copy.deepcopy(n)
                for remove in n.xpath('.//script|.//style|.//*[contains(@class,"subject-card__desc")]'):
                    remove.getparent().remove(remove)
                body.append(n)
            content=html.tostring(wrapper,encoding='unicode');representation='structural-html-excerpt'
        source['representation_sha256']=digest(content)
        bundle=dict(source=source,representation=representation,content=content)
        path=INPUTS/(sid+'.json');write_json(path,bundle);result.append(str(path.relative_to(ROOT)))
    write_json(INPUTS/'manifest.json',result)
    return result


def build(write=True):
    records=[];denominators={};input_manifest=json.loads((INPUTS/'manifest.json').read_text())
    for filename in input_manifest:
        bundle=json.loads((ROOT/filename).read_text());s=bundle['source'];content=bundle['content']
        require(digest(content)==s['representation_sha256'],'catalog_representation_hash_mismatch')
        if s['source_id']=='spbu-catalog-programs-pdf':
            rows=parse_spbu(s,content)
            denominators['spbu']=sum(440<float(b['x0'])<490 and b['text'] in ('очная','очно-заочная','заочная') for b in content)
        elif s['source_id']=='msu-catalog-seats':rows=parse_msu(s,content)
        elif s['institution_id']=='mephi':
            parsed=parse_catalog(content.encode(),s);rows=[];denominators['mephi']=parsed['expected_source_rows']
            for r in parsed['records']:
                row=record(s,r['name'],r['provenance']['locator'],code=r['official_code'],level=r['degree'],
                           notes=['Published profile; campaign and campus require individual confirmation.'])
                row['legacy_program_id']=r['id'];rows.append(row)
        else:rows=parse_html(s,content)
        records.extend(rows)
    # Keep each source fact, but provide a display index where explicit URLs establish identity.
    display={}
    for row in records:
        identity=row['program_url'] if row['kind']=='program_profile' else None
        key=(row['institution_id'],row['campus'],identity or row['id'],row['kind'])
        if key not in display:display[key]=copy.deepcopy(row)
        elif row['places'] is not None:display[key]=copy.deepcopy(row)
    # HSE can publish the same URL under multiple direction codes: keep those distinct.
    # Conflicting codes are not merged or distributed across seats automatically.
    for key,row in list(display.items()):
        matches=[r for r in records if (r['institution_id'],r['campus'],(r['program_url'] if r['kind']=='program_profile' else None) or r['id'],r['kind'])==key]
        codes={r['official_code'] for r in matches if r['official_code']}
        if len(codes)>1:
            del display[key]
            for r in matches:
                if r['official_code']:display[(*key,r['official_code'])]=copy.deepcopy(r)
    coverage=[];scope=json.loads((ROOT/'config/catalog_scope.json').read_text())
    inv=json.loads((OUT/'source_inventory.json').read_text())
    for ident in scope['institution_ids']:
        facts=[r for r in records if r['institution_id']==ident]
        entries=[r for r in display.values() if r['institution_id']==ident]
        count=sum(r['kind']=='program_profile' for r in entries)
        coverage.append(dict(institution_id=ident,source_observations=len(facts),display_entries=len(entries),
            program_profiles=count,marketing_tracks=sum(r['kind']=='marketing_track' for r in entries),
            known_bachelor_specialist=sum(r['degree'] in ('bachelor','specialist') and r['kind']=='program_profile' for r in entries),
            basic_higher_profiles=sum(r['degree']=='basic_higher' for r in entries),
            degree_unestablished=sum(r['degree'] is None for r in entries),
            rows_with_code=sum(r['official_code'] is not None for r in entries),
            rows_with_campaign_year=sum(r['campaign_year'] is not None for r in entries),
            visible_source_observations=len(facts),
            source_row_denominator=denominators.get(ident),
            target_program_denominator=None,target_completeness=None,
            status='partial' if facts else 'unavailable_or_unparsed',
            source_failures=[r for r in inv if r['institution_id']==ident and r['status']!='fetched'],
            missing=['Target program denominator not established','Exact exam rules and campaigns require further document review']))
    result=dict(schema_version=1,adapter_version=VERSION,records=records,display_index=list(display.values()),
                coverage=coverage,complete_for_ten_universities=False,forecasting_enabled=False)
    validate(result)
    if write:
        write_json(OUT/'dataset.json',result);write_json(OUT/'coverage.json',coverage)
        write_json(OUT/'public_index.json',[dict(id=r['id'],institution_id=r['institution_id'],name=r['name'],
            campus=r['campus'],official_code=r['official_code'],degree=r['degree'],kind=r['kind'],
            year=r['campaign_year'],source_url=r['provenance']['url']) for r in display.values()])
    return result


def validate(dataset):
    require(dataset['adapter_version']==VERSION,'catalog_version')
    ids=set()
    for r in dataset['records']:
        require(r['id'] not in ids,'duplicate_catalog_observation');ids.add(r['id'])
        require(r['name'] and r['provenance']['locator'],'catalog_identity_or_provenance_missing')
        require(len(r['provenance']['parent_sha256'])==64,'catalog_parent_hash_missing')
        require(r['degree'] in (None,'bachelor','specialist','basic_higher'),'catalog_degree')
        require(r['kind'] in ('program_profile','marketing_track','direction'),'catalog_kind')
        require(r['campaign_year'] is None or type(r['campaign_year']) is int,'catalog_year')
        require(r['exams'] is None and r['exams_status']=='not_extracted','unverified_exam_interpretation')
    require(len(dataset['coverage'])==10,'catalog_requires_ten_coverage_rows')
    require(dataset['forecasting_enabled'] is False,'catalog_not_forecasting_approval')
    return True


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['materialize','build','validate']);args=p.parse_args()
    if args.command=='materialize':print(json.dumps(materialize()));return
    if args.command=='build':d=build()
    else:
        d=json.loads((OUT/'dataset.json').read_text());validate(d)
        require(d==build(write=False),'catalog_facts_do_not_replay')
    print(json.dumps({r['institution_id']:dict(profiles=r['program_profiles'],display=r['display_entries'],status=r['status']) for r in d['coverage']},ensure_ascii=False))


if __name__=='__main__':main()
