"""Historical source observations with separate units, populations and ML limits."""
import argparse,copy,json,re,subprocess
from urllib.parse import urljoin
from collections import Counter
from pathlib import Path
from lxml import html,etree
from .sources import SnapshotStore,digest,write_json
from .validate import ROOT,require

VERSION='historical-sources-v1'
OUT=ROOT/'data/normalized/history_v1';INPUTS=ROOT/'data/history_inputs'
CODE=re.compile(r'\b\d{2}\.(?:03|05)\.\d{2}\b')


def clean(n):return ' '.join(n.text_content().split())


def observation(s,year,name,metric,unit,category,raw,locator,*,code=None,url=None,notes=None,status=None):
    value=None
    if status is None:
        normalized=' '.join(raw.split())
        if re.fullmatch(r'\d+(?:[.,]\d+)?',normalized):status='numeric';value=float(normalized.replace(',','.'))
        elif re.fullmatch(r'\d+\s+и более',normalized):status='lower_bound';value=float(normalized.split()[0])
        elif normalized in ('','-','—','–'):status='not_published'
        elif 'бви' in normalized.casefold() and 'только' in normalized.casefold():status='bvi_only'
        else:status='manual_review'
    elif status=='numeric':value=float(raw.replace(',','.'))
    p=dict(source_id=s['source_id'],url=s['url'],parent_sha256=s['sha256'],
           representation_sha256=s['representation_sha256'],locator=locator,adapter_version=VERSION)
    payload=dict(institution_id=s['institution_id'],year=year,name=name,official_code=code,program_url=url,
        metric=metric,unit=unit,category=category,status=status,value=value,raw_value=raw,
        group_id=None,group_mapping_status='unresolved',division=None,parent_observation_id=None,
        notes=notes or [],provenance=p)
    return dict(id='history-source-'+digest([s['sha256'],locator,metric,category,VERSION])[:24],**payload)


def materialize():
    rows=json.loads((OUT/'source_inventory.json').read_text());paths=[]
    for row in rows:
        if row['status']!='fetched':continue
        s=copy.deepcopy(row['snapshot']);s['institution_id']=row['institution_id'];sid=s['source_id'];raw=SnapshotStore.read(s)
        content=None
        if sid.startswith('hse-history-'):
            root=html.fromstring(raw,parser=html.HTMLParser(encoding='utf-8',no_network=True));wrapper=html.Element('html')
            title=etree.SubElement(wrapper,'title');title.text=' '.join(root.xpath('//title/text()'))
            for table in root.xpath('//table'):
                if any('проход' in clean(c).casefold() or clean(c)=='Балл' for c in table.xpath('.//tr[1]/th|.//tr[1]/td')):
                    wrapper.append(copy.deepcopy(table))
            notes=[]
            for textnode in root.xpath('//text()'):
                t=' '.join(str(textnode).split())
                if t.startswith('*') and ('мест' in t.casefold() or 'зачисл' in t.casefold()) and len(t)<2000:notes.append(t)
            for note in dict.fromkeys(notes):etree.SubElement(wrapper,'p',{'data-footnote':'true'}).text=note
            content=html.tostring(wrapper,encoding='unicode')
        elif sid=='nsu-history-mm-2025':
            root=html.fromstring(raw,parser=html.HTMLParser(encoding='utf-8',no_network=True))
            # Preserve only the published aggregate block, excluding staff/student contacts.
            for remove in root.xpath('//script|//style'):remove.drop_tree()
            for br in root.xpath('//br'):br.tail=' '+(br.tail or '')
            visible=clean(root);start=visible.find('Проходные баллы')
            if start<0:raise ValueError('nsu_historical_block_missing')
            window=visible[start:start+1600]
            matches=list(re.finditer(r'20\d{2}\s*[—–-]\s*\d+',window))
            if not matches:raise ValueError('nsu_historical_values_missing')
            node=html.Element('p');node.text=window[:matches[-1].end()]
            content=html.tostring(node,encoding='unicode')
        elif sid=='bmstu-history-2025':
            content=subprocess.run(['pdftotext','-layout',str(ROOT/s['path']),'-'],capture_output=True,text=True,check=True).stdout
        elif s['institution_id']=='innopolis':
            # Catalog excerpt contains titles and numeric feature cards, without marketing descriptions.
            b=json.loads((ROOT/'data/catalog_inputs/innopolis-catalog-programs.json').read_text())
            content=b['content']
        if content is not None:
            s['representation_sha256']=digest(content)
            path=INPUTS/(sid+'.json');write_json(path,dict(source=s,content=content));paths.append(str(path.relative_to(ROOT)))
    write_json(INPUTS/'manifest.json',paths);return paths


def parse_hse(s,content):
    root=html.fromstring(content,parser=html.HTMLParser(encoding='utf-8',no_network=True))
    title=' '.join(root.xpath('//title/text()'));years=set(re.findall(r'\b20\d{2}\b',title))
    require(len(years)==1,'hse_history_year_ambiguous');year=int(years.pop())
    require(str(year)==s['source_id'].rsplit('-',1)[-1],'hse_history_source_year_mismatch')
    notes=[clean(p) for p in root.xpath('//p[@data-footnote]')]
    tables=root.xpath('//table');require(len(tables)==1,'hse_history_table_count')
    trs=tables[0].xpath('.//tr');headers=[clean(c) for c in trs[0].xpath('./td|./th')]
    serial=headers[0]=='№';name_i=1 if serial else 0
    score_columns=[(i,'paid' if 'платн' in h.casefold() else 'budget_unspecified') for i,h in enumerate(headers)
                   if 'проход' in h.casefold() or h=='Балл']
    require(score_columns,'hse_history_score_columns_missing');rows=[];code=None
    for n,tr in enumerate(trs[1:],1):
        cells=tr.xpath('./td|./th')
        if not cells:continue
        if tr.xpath('.//h4'):continue
        if len(cells)==1:
            codes=CODE.findall(clean(tr))
            if codes:code=codes[0]
            continue
        if len(cells)<=max(i for i,_ in score_columns):raise ValueError('hse_history_row_width_changed')
        if not serial and not clean(cells[-1]) and not clean(cells[-2]):continue
        name=clean(cells[name_i]);require(name,'hse_history_empty_name')
        if name.casefold().startswith(('итого','всего')):continue
        links=cells[name_i].xpath('.//a[@href]');url=links[0].get('href') if len(links)==1 else None
        for i,category in score_columns:
            raw=clean(cells[i]);status=None;extra=[]
            if '*' in raw:
                # Priority enrollment includes quotas AND olympiad admissions, not BVI alone.
                if any('приоритет' in note.casefold() and ('квот' in note.casefold() or 'поступ' in note.casefold()) for note in notes):
                    status='priority_only';extra=notes
                else:status='manual_review';extra=['Footnote requires interpretation.']+notes
            rows.append(observation(s,year,name,'cutoff','competition_points',category,raw,
                f'table=1; source-row={n}; column={i+1}',code=code,url=url,notes=extra,status=status))
    require(rows,'empty_hse_history');return rows


def parse_nsu(s,content):
    root=html.fromstring(content,parser=html.HTMLParser(encoding='utf-8'));t=clean(root)
    matches=list(re.finditer(r'\b(20\d{2})\s*[—–-]\s*(\d+)\b',t));require(matches,'nsu_no_historical_years')
    label='Математика и механика. Прикладная математика и информатика (область источника)'
    return [observation(s,int(m.group(1)),label,'cutoff','unspecified_points','budget_unspecified',m.group(2),
                       f'aggregate-block; character={m.start()}',notes=['Shared published scope; no per-program or per-year competition identity inferred.']) for m in matches]


def parse_bmstu(s,content):
    require('2025' in content and 'О/К' in content and 'Средний' in content,'bmstu_history_headers_changed')
    rows=[]
    pattern=re.compile(r'^(\d{2}\.(?:03|05)\.\d{2})\s+(.+?)\s{2,}(Бакалавр|Специалитет)\s+([\d,.-]+|—)\s+([\d,.-]+|—)\s+([\d,.-]+|—)\s+([\d,.-]+|—)\s*$')
    for i,line in enumerate(content.splitlines(),1):
        m=pattern.match(line)
        if not m:continue
        code,name,level,*values=m.groups()
        for value,(metric,category) in zip(values,[('minimum_entrance_total','general_budget'),('minimum_entrance_total','targeted'),('mean_entrance_total','general_budget'),('mean_entrance_total','targeted')]):
            rows.append(observation(s,2025,name.strip(),metric,'exam_total_points',category,value,f'pdftotext-layout; line={i}; {metric}/{category}',
                                   code=code,notes=['Source defines sum of EGE/internal exams; not mean EGE per subject. Campus: Mytishchi branch.']))
    require(rows,'bmstu_history_rows_missing');return rows


def parse_innopolis(s,content):
    root=html.fromstring(content,parser=html.HTMLParser(encoding='utf-8'));rows=[]
    for a in root.xpath('//a[contains(@class,"subject-card")]'):
        titles=a.xpath('.//h3');require(len(titles)==1,'innopolis_history_title')
        for feature in a.xpath('.//*[contains(concat(" ",normalize-space(@class)," ")," subject-card__features-card ")]'):
            label_nodes=feature.xpath('.//*[contains(@class,"features-card-text")]')
            value_nodes=feature.xpath('.//*[contains(@class,"features-card-title")]')
            if len(label_nodes)!=1 or len(value_nodes)!=1:continue
            label=clean(label_nodes[0]);value=clean(value_nodes[0]);year=re.search(r'20\d{2}',clean(feature))
            if 'проходн' not in label.casefold() or not year:continue
            rows.append(observation(s,int(year.group()),clean(titles[0]),'cutoff',
                'exam_total_points' if 'ЕГЭ' in label else 'unspecified_points',
                'budget_unspecified' if 'бюджет' in label else 'funding_unspecified',value,
                feature.getroottree().getpath(feature),url=urljoin(s['url'],a.get('href')),notes=[label,'Grant selection is not inferred from this threshold.']))
    require(rows,'innopolis_historical_features_missing');return rows


def build(write=True):
    records=[];errors=[]
    # Keep MEPhI original observations and separate mean metrics with their own units.
    base=json.loads((ROOT/'data/normalized/mephi/history.json').read_text())
    for r in base['records']:
        p=r['provenance'];s=dict(source_id=p['source_id'],url=p['url'],sha256=p['snapshot_sha256'],
            representation_sha256=digest(base),institution_id='mephi')
        row=observation(s,r['year'],r['official_name'],'cutoff','competition_points',r['competition_category'],
                        r['cutoff_raw'],p['locator'],code=r['official_code'],status=r['threshold_status'] if r['threshold_status']!='numeric' else 'numeric')
        row.update(division=r['division'],parent_observation_id=r['id'])
        records.append(row)
        for metric,unit in [('mean_ege_score','exam_points'),('mean_entrance_total','exam_total_points')]:
            if r[metric] is not None:
                mean=observation(s,r['year'],r['official_name'],metric,unit,r['competition_category'],str(r[metric]),p['locator'],code=r['official_code'])
                mean.update(division=r['division'],parent_observation_id=r['id']);records.append(mean)
    for filename in json.loads((INPUTS/'manifest.json').read_text()):
        b=json.loads((ROOT/filename).read_text());s=b['source'];content=b['content']
        require(digest(content)==s['representation_sha256'],'historical_representation_hash_mismatch')
        parser={'hse':parse_hse,'nsu':parse_nsu,'bmstu':parse_bmstu,'innopolis':parse_innopolis}[s['institution_id']]
        try:records.extend(parser(s,content))
        except ValueError as e:errors.append(dict(source_id=s['source_id'],status='manual_review',reason=str(e)))
    ids=[r['id'] for r in records];require(len(ids)==len(set(ids)),'duplicate_historical_observation')
    for r in records:
        require((r['status'] in ('numeric','lower_bound'))==(r['value'] is not None),'historical_value_status_conflict')
        require(r['value'] is None or r['value']>=0,'historical_negative_value')
        require(r['group_id'] is None,'historical_unverified_group')
        require(r['unit'] in ('competition_points','exam_total_points','exam_points','unspecified_points'),'historical_unit')
        require(r['unit']!='exam_points' or r['value'] is None or r['value']<=100,'mean_ege_scale')
    institutions=json.loads((ROOT/'config/catalog_scope.json').read_text())['institution_ids'];coverage=[]
    for ident in institutions:
        found=[r for r in records if r['institution_id']==ident]
        coverage.append(dict(institution_id=ident,observations=len(found),years=sorted({r['year'] for r in found}),
            metrics=dict(Counter(r['metric'] for r in found)),units=dict(Counter(r['unit'] for r in found)),
            admission_probability_ready=False,threshold_analysis_only=bool(found),
            limitations=['Competition identity, category completeness, comparability and final enrollment not established.']))
    possible_duplicates={}
    for row in records:
        key=(row['institution_id'],row['year'],row['name'],row['official_code'],row['division'],row['metric'],row['category'],row['unit'])
        possible_duplicates.setdefault(key,[]).append(row['id'])
    duplicate_scopes=[dict(scope=list(key),record_ids=ids,status='preserved_scope_requires_review') for key,ids in possible_duplicates.items() if len(ids)>1]
    result=dict(adapter_version=VERSION,records=records,coverage=coverage,parse_errors=errors,
        possible_duplicate_scopes=duplicate_scopes,
        duplicate_ids=0,complete_for_ten_universities=False,forecasting_enabled=False)
    if write:
        write_json(OUT/'dataset.json',result);write_json(OUT/'coverage.json',coverage)
        write_json(OUT/'metrics.json',dict(observations=len(records),institutions_with_data=sum(bool(r['observations']) for r in coverage),
                                         units=dict(Counter(r['unit'] for r in records)),statuses=dict(Counter(r['status'] for r in records)),
                                         possible_duplicate_scopes=len(duplicate_scopes),parse_errors=len(errors)))
        write_json(OUT/'public_index.json',public_index(result))
        write_json(OUT/'ml_readiness.json',dict(
            admission_probability_ready=False,confirmed_competition_groups=0,
            reason='No independently verified same-year competition populations and final enrollment distributions.',
            exploratory_threshold_candidates=sum(r['metric']=='cutoff' and r['status']=='numeric' and r['unit']=='competition_points'
                and bool(r['program_url']) and bool(r['official_code']) for r in records),
            excluded_from_exact_cutoff_targets=dict(means=sum(r['metric'].startswith('mean_') for r in records),
                censored_lower_bounds=sum(r['status']=='lower_bound' for r in records),
                priority_or_bvi=sum(r['status'] in ('priority_only','bvi_only') for r in records),
                ambiguous_units=sum(r['unit']=='unspecified_points' for r in records)),
            requirements=['Explicit yearly scope reconciliation','Separate metrics and units','Hold out future years',
                          'Do not treat descriptive threshold accuracy as calibrated admission probabilities']))
    return result


def public_index(dataset):
    return [dict(id=r['id'],institution_id=r['institution_id'],year=r['year'],
        name=r['name'],official_code=r['official_code'],metric=r['metric'],category=r['category'],
        unit=r['unit'],status=r['status'],value=r['value'],source_url=r['provenance']['url'])
        for r in dataset['records'] if r['metric'] in ('cutoff','minimum_entrance_total')]


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['materialize','build','validate']);a=p.parse_args()
    if a.command=='materialize':print(json.dumps(materialize()));raise SystemExit
    if a.command=='build':d=build()
    else:
        d=json.loads((OUT/'dataset.json').read_text());require(d==build(write=False),'historical_facts_do_not_replay')
    print(json.dumps(dict(observations=len(d['records']),errors=d['parse_errors'],coverage={r['institution_id']:r['observations'] for r in d['coverage']})))
