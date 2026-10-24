"""Source-specific catalog adapters. Missing campaign/code/campus stay null."""
import re
from urllib.parse import urljoin,urlsplit
from lxml import html
from .sources import digest

VERSION='catalog-v1'
CODE=re.compile(r'\b\d{2}\.(?:03|05)\.\d{2}\b')


def text(node):return ' '.join(node.text_content().split())


def degree(code):return None if not code else ('bachelor' if code[3:5]=='03' else 'specialist')


def record(source,name,locator,*,url=None,campus=None,code=None,level=None,year=None,kind='program_profile',seats=None,notes=None):
    name=' '.join(name.split())
    if not name or len(name)>600:raise ValueError('invalid_catalog_name')
    p=dict(source_id=source['source_id'],url=source['url'],parent_sha256=source['sha256'],
           representation_sha256=source['representation_sha256'],locator=locator,adapter_version=VERSION)
    identity=[source['institution_id'],source['sha256'],locator,name,code,VERSION]
    return dict(id='catalog-'+digest(identity)[:24],institution_id=source['institution_id'],name=name,
                campus=campus,official_code=code,degree=level or degree(code),campaign_year=year,
                kind=kind,program_url=url,places=seats,exams=None,exams_status='not_extracted',
                eligibility_status='not_individually_verified',notes=notes or [],provenance=p)


def parse_html(source,content):
    root=html.fromstring(content,parser=html.HTMLParser(encoding='utf-8',no_network=True))
    tree=root.getroottree();ident=source['institution_id'];rows=[]
    if ident=='hse' and source['source_id'].endswith('programs'):
        campus_map={'msk':'Москва','spb':'Санкт-Петербург','nn':'Нижний Новгород','perm':'Пермь'}
        for a in root.xpath('//p[@class="text"]/a[@href]'):
            u=a.get('href')
            if not re.fullmatch(r'https://(?:www|spb|nnov|perm)\.hse\.ru/ba/[^/?#]+/',u):continue
            campuses=[v for n in a.iterancestors() for k,v in campus_map.items() if k in n.get('class','').split()]
            if len(set(campuses))!=1:raise ValueError('hse_program_campus_ambiguous')
            rows.append(record(source,text(a),tree.getpath(a),url=u,campus=campuses[0]))
    elif ident=='hse' and source['source_id'].endswith('seats'):
        tables=root.xpath('//table');
        if len(tables)!=1 or '2026' not in text(root):raise ValueError('hse_seats_year_or_layout_changed')
        code=None
        for tr in tables[0].xpath('.//tbody/tr'):
            cells=tr.xpath('./td')
            if len(cells)==1:
                codes=CODE.findall(text(tr))
                if codes:code=codes[0]
                continue
            if len(cells)!=8:raise ValueError('hse_seats_column_count_changed')
            if code is None:raise ValueError('hse_seats_direction_missing')
            anchors=cells[0].xpath('.//a[starts-with(@href,"https://www.hse.ru/ba/")]')
            name=text(cells[0]);u=anchors[0].get('href') if len(anchors)==1 else None
            if name.casefold().startswith(('итого','всего:')):continue
            def count(cell):
                clone=html.fromstring(html.tostring(cell))
                for note in clone.xpath('.//sup'):note.drop_tree()
                raw=text(clone)
                return int(raw) if raw.isdigit() else None
            rows.append(record(source,name,tree.getpath(tr),url=u,campus='Москва',code=code,year=2026,
                        seats=dict(budget_total=count(cells[2]),paid=count(cells[6]),
                                   budget_raw=text(cells[2]),paid_raw=text(cells[6])),
                        notes=['Budget total includes quotas; dash remains missing, not zero.']))
    elif ident=='innopolis':
        for a in root.xpath('//a[contains(concat(" ",normalize-space(@class)," ")," subject-card ")]'):
            titles=a.xpath('.//h3');
            if len(titles)!=1:raise ValueError('innopolis_program_title_ambiguous')
            codes=CODE.findall(text(a));code=codes[0] if len(set(codes))==1 else None
            rows.append(record(source,text(titles[0]),tree.getpath(a),url=urljoin(source['url'],a.get('href')),
                               code=code,level='bachelor',notes=['Published bachelor profile; grant selection is separate.']))
    elif ident=='nsu':
        for a in root.xpath('//a[@href]'):
            nodes=a.xpath('.//*[starts-with(@field,"text")]')
            if len(nodes)!=1:continue
            clone=html.fromstring(html.tostring(nodes[0]))
            for br in clone.xpath('.//br'):br.tail='\n'+(br.tail or '')
            names=[n.strip() for n in clone.text_content().splitlines() if n.strip()]
            for i,name in enumerate(names):
                rows.append(record(source,name,tree.getpath(a)+f'; program-line={i+1}',
                                   notes=['Catalog lists bachelor and specialist together; degree/year not established.',
                                          'Department catalog: '+a.get('href')]))
        # Standalone linked programs have no descriptive list.
        for a in root.xpath('//a[contains(@href,"education.nsu.ru/")]'):
            if a.xpath('.//*[starts-with(@field,"text")]'):continue
            u=a.get('href').rstrip('/')
            if u.endswith(('/mechatronics','/ai')):
                rows.append(record(source,text(a),tree.getpath(a),url=a.get('href')))
    elif ident=='bmstu':
        for li in root.xpath('//li[@id]'):
            code=li.get('id');titles=li.xpath('./h3')
            if not CODE.fullmatch(code) or len(titles)!=1:continue
            degree_text=' '.join(text(n) for n in li.xpath('./p'))
            pilot='Пилотный проект' in degree_text
            level='basic_higher' if pilot else degree(code)
            for a in li.xpath('./ul/li/a[@href]'):
                rows.append(record(source,text(a),tree.getpath(a),url=urljoin(source['url'],a.get('href')),
                                   campus='Мытищинский филиал',code=code,level=level,
                                   notes=['Pilot designation retained separately from bachelor/specialist.'] if pilot else []))
    elif ident=='cu':
        for n in root.xpath('//h3'):
            name=text(n)
            if name in ('Искусственный интеллект','Бизнес и аналитика','Разработка','Дизайн'):
                rows.append(record(source,name,tree.getpath(n),url=source['url'],level='bachelor',kind='marketing_track',
                                   notes=['Marketing track, not a verified legal program or competition.']))
    else:raise ValueError('unsupported_html_catalog_source')
    unique={}
    for row in rows:
        key=(row['name'],row['campus'],row['program_url'],row['official_code'],row['kind'])
        unique.setdefault(key,row)
    if not unique:raise ValueError('catalog_adapter_produced_no_rows')
    return list(unique.values())


def parse_spbu(source,blocks):
    forms=[b for b in blocks if 440<float(b['x0'])<490 and b['text'] in ('очная','очно-заочная','заочная')]
    names=[b for b in blocks if 265<=float(b['x0'])<440 and float(b['x1'])<442
           and b['text']!='Наименование образовательной программы']
    if not forms or len(names)!=len(forms):raise ValueError('spbu_program_column_layout_changed')
    code_blocks=[b for b in blocks if CODE.fullmatch(b['text']) and float(b['x0'])<80]
    rows=[];used=set()
    for name in sorted(names,key=lambda b:float(b['y0'])):
        center=(float(name['y0'])+float(name['y1']))/2
        nearest=min(forms,key=lambda b:abs((float(b['y0'])+float(b['y1']))/2-center))
        key=nearest['locator']
        if key in used:raise ValueError('spbu_program_form_mapping_ambiguous')
        used.add(key)
        close=[b for b in code_blocks if abs((float(b['y0'])+float(b['y1']))/2-center)<12]
        code=close[0]['text'] if len(close)==1 else None
        rows.append(record(source,name['text'],name['locator'],code=code,year=2026,
                           notes=['PDF program-name column; exams and seat columns not yet interpreted.']))
    return rows


def parse_msu(source,content):
    rows=[]
    pattern=re.compile(r'образовательн(?:ая|ые)\s+программ(?:а|ы)\s+"([^"]+)"',re.I)
    for i,match in enumerate(pattern.finditer(content)):
        name=' '.join(match.group(1).split())
        if len(name)<2:raise ValueError('msu_empty_program_title')
        rows.append(record(source,name,f'pdftotext-raw; character={match.start()}; ordinal={i+1}',
                           year=2026,
                           notes=['Explicit educational program title; degree/code/campus not inferred across merged cells.']))
    if not rows:raise ValueError('msu_program_pattern_changed')
    return rows
