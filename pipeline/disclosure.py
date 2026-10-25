"""Compact institutional disclosure evidence; no admission year inferred from cohorts."""
import re
from lxml import html,etree
from .mephi import text


def mipt_excerpt(raw):
    root=html.fromstring(raw,parser=html.HTMLParser(encoding='utf-8',no_network=True));wrapper=html.Element('html')
    for ti,table in enumerate(root.xpath('//table'),1):
        rows=table.xpath('.//tr')
        if not rows:continue
        headers=[text(c) for c in rows[0].xpath('./th|./td')][:6]
        if len(headers)<6:continue
        if headers[3]!='Уровень образования' or headers[4]!='Образовательная программа, направленность, профиль':continue
        selected=[]
        for ri,row in enumerate(rows[1:],2):
            code=row.xpath('./td[@itemprop="eduCode"]')
            if len(code)!=1 or not re.fullmatch(r'\d{2}\.(03|05)\.\d{2}',text(code[0])):continue
            values=[text(row.xpath('./td')[0])]
            for prop in ('eduCode','eduName','eduLevel','eduProf','eduForm'):
                cells=row.xpath('./td[@itemprop="'+prop+'"]')
                if len(cells)!=1:raise ValueError('mipt_disclosure_semantic_field_missing')
                values.append(text(cells[0]))
            selected.append((ri,values))
        if not selected:continue
        t=etree.SubElement(wrapper,'table',{'data-source-table':str(ti)})
        tr=etree.SubElement(t,'tr')
        for value in headers:etree.SubElement(tr,'th').text=value
        for ri,values in selected:
            tr=etree.SubElement(t,'tr',{'data-source-row':str(ri)})
            for value in values:etree.SubElement(tr,'td').text=value
    if not len(wrapper):raise ValueError('mipt_disclosure_tables_missing')
    return html.tostring(wrapper,encoding='unicode')


def cu_program_excerpt(content):
    start=content.find('Направление подготовки:');end=content.find('ДОКУМЕНТ ПОДПИСАН',start)
    section=content.find('1.1.');section_end=content.find('Основная профессиональная образовательная программа представляет',section)
    if min(start,end,section,section_end)<0:raise ValueError('cu_program_document_structure_changed')
    return content[start:end].strip()+'\n\n'+content[section:section_end].strip()


def itmo_excerpt(raw):
    root=html.fromstring(raw,parser=html.HTMLParser(encoding='utf-8',no_network=True));wrapper=html.Element('html')
    found=[]
    for ti,table in enumerate(root.xpath('//table'),1):
        rows=table.xpath('.//tr')
        if not rows:continue
        headers=[text(c) for c in rows[0].xpath('./th|./td')][:6]
        if len(headers)<6 or headers[1]!='Год приема':continue
        selected=[]
        for ri,tr in enumerate(rows[1:],2):
            codes=tr.xpath('./td[@itemprop="eduCode"]')
            if len(codes)!=1 or not re.fullmatch(r'\d{2}\.(03|05)\.\d{2}',text(codes[0])):continue
            cells=tr.xpath('./td');year=text(cells[1])
            if not re.fullmatch(r'20\d{2}',year):raise ValueError('itmo_intake_year_missing')
            values=[text(codes[0]),year]
            for prop in ('eduName','eduProf','eduLevel','eduForm'):
                ns=tr.xpath('./td[@itemprop="'+prop+'"]')
                if len(ns)!=1:raise ValueError('itmo_disclosure_semantic_field_missing')
                values.append(text(ns[0]))
            selected.append((ri,values))
        if selected:found.append((ti,headers,selected))
    if len(found)!=1:raise ValueError('itmo_intake_table_ambiguous')
    ti,headers,selected=found[0];latest=max(int(v[1]) for _,v in selected)
    t=etree.SubElement(wrapper,'table',{'data-source-table':str(ti),'data-intake-year':str(latest)})
    tr=etree.SubElement(t,'tr')
    for value in headers:etree.SubElement(tr,'th').text=value
    for ri,values in selected:
        if int(values[1])!=latest:continue
        tr=etree.SubElement(t,'tr',{'data-source-row':str(ri)})
        for value in values:etree.SubElement(tr,'td').text=value
    return html.tostring(wrapper,encoding='unicode')
