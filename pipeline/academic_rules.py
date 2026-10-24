"""Documented annual EGE rules. Unsupported rights/bases are never inferred."""
import argparse,copy,json,re,subprocess
from collections import defaultdict
from pathlib import Path
from lxml import html,etree
from .mephi import grid,text
from .sources import SnapshotStore,digest,write_json
from .validate import ROOT,require

VERSION='academic-rules-v1';OUT=ROOT/'data/normalized/rules_v1';INPUTS=ROOT/'data/rules_inputs'
SUBJECTS={'математика':'mathematics','физика':'physics','информатика':'informatics','русский язык':'russian',
          'химия':'chemistry','биология':'biology','история':'history','обществознание':'social_studies','иностранный язык':'foreign_language'}


def materialize():
    inventory=json.loads((OUT/'source_inventory.json').read_text());inputs=[]
    for entry in inventory:
        if entry['status']!='fetched':continue
        s=entry['snapshot'];raw=SnapshotStore.read(s);sid=s['source_id']
        if sid=='mephi-exam-rules-pdf-2026':
            content=subprocess.run(['pdftotext','-layout',str(ROOT/s['path']),'-'],capture_output=True,text=True,check=True).stdout[:6500]
        else:
            root=html.fromstring(raw,parser=html.HTMLParser(encoding='utf-8',no_network=True));wrapper=html.Element('html')
            if sid=='mephi-exam-rules-2026':nodes=root.xpath('//table')[0:1]
            else:
                nodes=[tr for tr in root.xpath('//table//tr') if tr.xpath('./td') and text(tr.xpath('./td')[0]) in ('1','2','3','51','57')]
                require(len(nodes)==5,'supported_achievement_rows_changed')
                table=etree.SubElement(wrapper,'table');body=etree.SubElement(table,'tbody')
                for n in nodes:body.append(copy.deepcopy(n))
                nodes=[]
            for n in nodes:wrapper.append(copy.deepcopy(n))
            content=html.tostring(wrapper,encoding='unicode')
        inputs.append(dict(source=s,content=content,representation_sha256=digest(content)))
    store=SnapshotStore();s=next(s for s in store.manifest['snapshots'] if s['source_id']=='mephi-rules')
    root=html.fromstring(store.read(s),parser=html.HTMLParser(encoding='utf-8',no_network=True))
    paragraphs=[text(n) for n in root.xpath('//p|//li') if 'индивидуальные достижения' in text(n)
                and ('не более 10' in text(n) or 'составляет 5' in text(n)) and len(text(n))<1500]
    require(len(paragraphs)>=2,'achievement_cap_evidence_missing')
    content='\n'.join(dict.fromkeys(paragraphs))
    inputs.append(dict(source=s,content=content,representation_sha256=digest(content)))
    write_json(INPUTS/'mephi-2026.json',inputs)


def build(write=True):
    inputs=json.loads((INPUTS/'mephi-2026.json').read_text());byid={b['source']['source_id']:b for b in inputs}
    for b in inputs:require(digest(b['content'])==b['representation_sha256'],'academic_source_representation_mismatch')
    pdf=byid['mephi-exam-rules-pdf-2026'];require('2026' in pdf['content'] and '01.03.02' in pdf['content'],'academic_rule_year_not_documented')
    cap=byid['mephi-rules'];cap_match=re.search(r'не более\s+(\d+)',cap['content'])
    require(cap_match is not None,'general_achievement_cap_missing');achievement_cap=int(cap_match.group(1))
    achievements=byid['mephi-achievement-rules-2026'];root=html.fromstring(achievements['content'])
    rows={text(tr.xpath('./td')[0]):[text(c) for c in tr.xpath('./td')] for tr in root.xpath('//tr')}
    require(rows['51'][2].isdigit(),'honors_rule_not_numeric')
    require('Российской Федерации' in rows['51'][1] and 'отличием' in rows['51'][1],'honors_conditions_changed')
    badge=rows['57'];badge_points={}
    for key,word in [('gto_gold','золотой'),('gto_silver','серебряный'),('gto_bronze','бронзовый')]:
        m=re.search(r'(\d+)\s*\('+word,badge[2]);require(m is not None,'gto_points_changed');badge_points[key]=int(m.group(1))
    require('возрастной группы' in badge[1] and 'предшествующем году' in badge[1],'gto_age_condition_changed')
    supported_achievements={'honors_rf':dict(points=int(rows['51'][2]),family='honors',requires=['russian_document','with_honors']),
        **{k:dict(points=v,family='gto',requires=['badge_document_present','age_group_eligible_for_campaign']) for k,v in badge_points.items()}}
    for key,index in [('vosh_unused','1'),('rsosh_winner_unused','2'),('rsosh_prize_unused','3')]:
        require(rows[index][2].isdigit(),'olympiad_id_points_changed')
        require('не учитывались' in rows[index][1],'olympiad_id_conditions_changed')
        conditions=['diploma_present','not_used_for_special_rights']
        if index in ('2','3'):conditions.append('grade_11_diploma')
        supported_achievements[key]=dict(points=int(rows[index][2]),family='olympiad_'+index,requires=conditions)
    exam=byid['mephi-exam-rules-2026'];root=html.fromstring(exam['content'],parser=html.HTMLParser(encoding='utf-8'))
    tables=root.xpath('//table');require(len(tables)==1,'academic_exam_table_count');g=grid(tables[0])
    require([c['text'] for c in g[0]][:4]==['ОСП','Код','Наименование направления подготовки (специальности)','Уровень высшего образования'],'academic_exam_headers_changed')
    fields=defaultdict(list)
    for n,row in enumerate(g[1:],1):
        v=[c['text'] if c else '' for c in row];require(len(v)==9,'academic_exam_row_width')
        require(v[0]=='НИЯУ МИФИ (г.Москва)','unexpected_exam_campus')
        code=v[1].rstrip('.');require(re.fullmatch(r'\d{2}\.(03|05)\.\d{2}',code),'invalid_exam_direction')
        fields[code].append(dict(values=v,locator=f'table=1; data-row={n}'))
    official={r['official_code'] for r in json.loads((ROOT/'data/normalized/mephi/official_fields.json').read_text())}
    rules=[];unsupported=[]
    for code,entries in sorted(fields.items()):
        for category,column in [('general_budget',6),('paid',7)]:
            if code not in official:
                unsupported.append(dict(code=code,category=category,reason='offering_or_applicant_basis_not_confirmed'));continue
            if any(not e['values'][column] for e in entries):
                unsupported.append(dict(code=code,category=category,reason='minimums_not_published_for_category'));continue
            require(len(entries)==3,'unexpected_number_of_ege_slots');slots=[];evidence=[]
            for e in sorted(entries,key=lambda x:int(x['values'][8])):
                v=e['values'];names=v[4].casefold().split('/');minimums=v[column].split('/')
                require(len(names)==len(minimums),'exam_alternatives_minimums_mismatch');slot=[]
                for name,minimum in zip(names,minimums):
                    require(name in SUBJECTS and minimum.isdigit(),'unknown_exam_or_minimum')
                    slot.append(dict(key=SUBJECTS[name],minimum=int(minimum),maximum=100))
                slots.append(slot);evidence.append(e['locator'])
            payload=dict(institution_id='mephi',campus_id='mephi-moscow',year=2026,official_code=code,
                name=entries[0]['values'][2],category=category,applicant_basis='school_ege',slots=slots,
                achievementCap=achievement_cap,source_status='documented_score_constraints',
                evidence=dict(exams=dict(source_id=exam['source']['source_id'],sha256=exam['source']['sha256'],locators=evidence),
                              annual_pdf=dict(source_id=pdf['source']['source_id'],sha256=pdf['source']['sha256']),
                              achievement_cap=dict(source_id=cap['source']['source_id'],sha256=cap['source']['sha256'])))
            rules.append(dict(id='rule-'+digest([payload,VERSION])[:24],**payload))
    result=dict(adapter_version=VERSION,year=2026,institution_id='mephi',rules=rules,
        supported_achievements=supported_achievements,unsupported_scopes=unsupported,
        supported_categories=['general_budget','paid'],supported_applicant_basis='school_ege',
        bvi_and_quotas='manual_review_required',ranking_ties='additional_official_criteria_required',
        sources=[dict(id=b['source']['source_id'],url=b['source']['url'],sha256=b['source']['sha256'],
                      representation_sha256=b['representation_sha256']) for b in inputs])
    if write:
        write_json(OUT/'dataset.json',result)
        write_json(OUT/'public_rules.json',dict(year=2026,institution_id='mephi',supported_achievements=supported_achievements,
             rules=[{k:r[k] for k in ('id','official_code','category','name','slots','achievementCap')} for r in rules],
             sources=[b['url'] for b in result['sources']]))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['materialize','build','validate']);a=p.parse_args()
    if a.command=='materialize':materialize();raise SystemExit
    if a.command=='build':d=build()
    else:
        d=json.loads((OUT/'dataset.json').read_text());require(d==build(write=False),'academic_rules_do_not_replay')
    print(json.dumps(dict(year=d['year'],rule_versions=len(d['rules']),directions=len({r['official_code'] for r in d['rules']}),unsupported_scopes=d['unsupported_scopes'])))
