"""MEPhI semantic HTML adapter. Never identifies a competition by degree code alone."""
import re
from urllib.parse import urljoin

from lxml import html

from .sources import digest

ADAPTER_VERSION = 'mephi-html-v1'
CODE = re.compile(r'(?<!\d)\d{2}\.\d{2}\.\d{2}(?!\d)')


class ParseError(ValueError):
    pass


def text(node):
    return ' '.join(node.text_content().replace('\xa0', ' ').split())


def document(data):
    # HTML parser does not execute scripts; external resources are never loaded.
    return html.fromstring(data, parser=html.HTMLParser(encoding='utf-8', no_network=True))


def body(document):
    nodes = document.xpath('//*[contains(concat(" ",normalize-space(@class)," ")," field-name-body ")]')
    return nodes[0] if nodes else document


def discover(data, base_url):
    return sorted({urljoin(base_url, a.get('href')) for a in body(document(data)).xpath('.//a[@href]')
                   if urljoin(base_url, a.get('href')).startswith('https://admission.mephi.ru/')})


def grid(table):
    """Expand spans while retaining the origin cell. Shared seat cells stay one fact."""
    occupied, output = {}, []
    for r, row in enumerate(table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr')):
        c = 0
        for cell in row.xpath('./td|./th'):
            while (r, c) in occupied:
                c += 1
            rowspan, colspan = int(cell.get('rowspan', '1')), int(cell.get('colspan', '1'))
            if not (1 <= rowspan <= 200 and 1 <= colspan <= 30):
                raise ParseError('invalid_table_span')
            for dr in range(rowspan):
                for dc in range(colspan):
                    if (r + dr, c + dc) in occupied:
                        raise ParseError('overlapping_table_span')
                    occupied[r + dr, c + dc] = dict(text=text(cell), origin=[r, c], node=cell)
            c += colspan
        width = max((cc for rr, cc in occupied if rr == r), default=-1) + 1
        output.append([occupied.get((r, cc)) for cc in range(width)])
    return output


def number(raw):
    raw = raw.strip().replace('\xa0', '').replace(' ', '')
    if not re.fullmatch(r'\d+(?:[.,]\d+)?', raw):
        return None
    value = float(raw.replace(',', '.'))
    return int(value) if value.is_integer() else value


def threshold(raw, kind=''):
    a, b = raw.casefold().strip(), kind.casefold().strip()
    value = number(raw)
    if 'только бви' in b or 'только бви' in a:
        return ('manual_review', None) if value is not None else ('bvi_only', None)
    if any(x in a for x in ('не проводился', 'не осуществлялся', 'не было приема', 'отсутствовала')):
        return 'not_offered', None
    if value is not None:
        return 'numeric', value
    if a in ('', '-', '—', '–', 'нет', 'н/д'):
        return 'not_published', None
    return 'manual_review', None


def provenance(snapshot, table, row, table_index, row_index):
    return dict(source_id=snapshot['source_id'], url=snapshot['url'], snapshot_sha256=snapshot['sha256'],
                snapshot_path=snapshot['path'], adapter_version=ADAPTER_VERSION,
                table_index=table_index, row_index=row_index,
                locator=table.getroottree().getpath(row),
                raw_fragment=html.tostring(row, encoding='unicode', with_tail=False),
                raw_cells=[text(c) for c in row.xpath('./th|./td')])


def table_year(table):
    container_year = None
    for ancestor in table.iterancestors():
        if re.fullmatch(r'20\d{2}', ancestor.get('id', '')):
            container_year = int(ancestor.get('id'))
            break
    headings = table.xpath('preceding::*[self::h2 or self::h3 or self::h4]')
    heading_year = None
    for heading in reversed(headings):
        match = re.search(r'в\s+(20\d{2})\s+году', text(heading))
        if match:
            heading_year = int(match[1])
            break
    if container_year and heading_year and container_year != heading_year:
        raise ParseError('conflicting_table_year')
    if container_year is None and heading_year is None:
        raise ParseError('missing_table_year')
    year = container_year or heading_year
    header_text = ' '.join(text(c) for c in table.xpath('.//tr[1]/*'))
    header_years = set(map(int, re.findall(r'20\d{2}', header_text)))
    if header_years and header_years != {year}:
        raise ParseError('header_year_conflict')
    return year


def parse_history(data, snapshot):
    root, records, errors, counts = body(document(data)), [], [], {}
    for table_index, table in enumerate(root.xpath('.//table')):
        rows = table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr')
        if not rows:
            continue
        headers = [text(c).casefold() for c in rows[0].xpath('./th|./td')]
        if not any(h.startswith('проходной балл') for h in headers):
            continue
        try:
            year = table_year(table)
            if year in counts:
                raise ParseError('multiple_history_tables_for_year_requires_review')
            expanded = grid(table)
            def index(predicate):
                return next((i for i, h in enumerate(headers) if predicate(h)), None)
            code_i = index(lambda h: h == 'код направления')
            name_i = index(lambda h: h in ('направление', 'направление/специальность', 'наименование'))
            cutoff_i = index(lambda h: h.startswith('проходной балл'))
            type_i = index(lambda h: h == 'тип проходного балла')
            division_i = index(lambda h: h in ('сае', 'факультет', 'институт'))
            mean_ege_i = index(lambda h: h == 'средний балл егэ')
            mean_total_i = index(lambda h: 'средняя сумма' in h)
            if name_i is None or cutoff_i is None:
                raise ParseError('unknown_history_headers')
            counts[year] = len(rows) - 1
            for ri, row in enumerate(rows[1:], 1):
                cells = expanded[ri]
                def value(i):
                    if i is None:
                        return None
                    if i >= len(cells) or cells[i] is None:
                        raise ParseError(f'short_history_row:{year}:{ri}')
                    return cells[i]['text']
                raw_name = value(name_i)
                code_match = CODE.search(value(code_i) if code_i is not None else raw_name)
                code = code_match[0] if code_match else None
                name = CODE.sub('', raw_name, count=1).lstrip(" '\u2019") if code_i is None else raw_name
                status, cutoff = threshold(value(cutoff_i), value(type_i) or '')
                p = provenance(snapshot, table, row, table_index, ri)
                mean_ege_raw, mean_total_raw = value(mean_ege_i), value(mean_total_i)
                warnings = ['historical_competition_group_not_established']
                if code is None:
                    warnings.append('code_not_published')
                if status == 'manual_review':
                    warnings.append('unrecognized_or_conflicting_threshold')
                row_key = digest([snapshot['url'], year, ri])
                record = dict(id='mephi-h-' + digest([row_key, snapshot['sha256'], ADAPTER_VERSION])[:24],
                    row_key=row_key, year=year, institution_id='mephi', campus_id='mephi-moscow',
                    official_code=code, official_name=name, division=value(division_i),
                    competition_category='budget_unspecified', competition_group_id=None,
                    group_mapping_status='unresolved', threshold_status=status,
                    cutoff=cutoff, cutoff_unit='competition_points',
                    threshold_type_raw=value(type_i), cutoff_raw=value(cutoff_i),
                    mean_ege_score=number(mean_ege_raw) if mean_ege_raw is not None else None,
                    mean_ege_status='published' if mean_ege_i is not None else 'not_published',
                    mean_entrance_total=number(mean_total_raw) if mean_total_raw is not None else None,
                    mean_entrance_total_status='published' if mean_total_i is not None else 'not_published',
                    mean_label_raw=headers[mean_ege_i if mean_ege_i is not None else mean_total_i] if mean_ege_i is not None or mean_total_i is not None else None,
                    review_status='pending_group_mapping', warnings=warnings, provenance=p)
                records.append(record)
        except (ParseError, ValueError) as error:
            errors.append(dict(table_index=table_index, status='parse_error', error=str(error), source_url=snapshot['url']))
    if not counts:
        raise ParseError('no_history_tables_found')
    return dict(records=records, errors=errors, expected_rows_by_year=counts)


def subject_tags(code, name):
    tags = set()
    if code.startswith('01.') or code == '03.03.01':
        tags.add('Mathematics')
    if code.startswith(('09.', '10.')) or any(x in name.casefold() for x in ('программ', 'науки о данных', 'вычислит')):
        tags.add('Computer Science')
    if any(x in name.casefold() for x in ('машинное обучение', 'искусственн', 'нейронн')):
        tags.add('Artificial Intelligence / ML')
    if code.startswith(('11.', '12.', '14.', '15.', '16.', '18.', '22.', '27.')):
        tags.add('Engineering')
    if code.startswith(('03.', '14.', '16.')):
        tags.add('Physics')
    return sorted(tags or {'Other'})


def parse_catalog(data, snapshot, campaign_year=2026):
    records, expected = [], 0
    for ti, table in enumerate(body(document(data)).xpath('.//table')):
        expanded = grid(table)
        if not expanded or not any(c and c['text'] == 'Код' for c in expanded[0]):
            continue
        headers = [c['text'] if c else '' for c in expanded[0]]
        if len(headers) != 5 or 'Институт' not in headers[2]:
            raise ParseError('unknown_catalog_headers')
        rows = table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr')
        expected += len(rows) - 1
        for ri, (row, cells) in enumerate(zip(rows[1:], expanded[1:]), 1):
            if len(cells) != 5 or not all(cells):
                raise ParseError('short_catalog_row')
            code_match = CODE.fullmatch(cells[0]['text'])
            if not code_match or code_match[0][3:5] not in ('03', '05'):
                raise ParseError('invalid_catalog_code')
            code, name, division = code_match[0], cells[3]['text'], cells[2]['text']
            program_links = [urljoin(snapshot['url'], a.get('href')) for a in cells[3]['node'].xpath('.//a[@href]')]
            plans = [urljoin(snapshot['url'], a.get('href')) for a in cells[4]['node'].xpath('.//a[@href]')]
            stable_id = 'mephi-p-' + digest(['mephi-moscow', code, division, name])[:24]
            records.append(dict(id=stable_id, year=campaign_year, official_code=code,
                field_name_raw=cells[1]['text'], name=name, division=division,
                campus_id='mephi-moscow', degree='bachelor' if code[3:5] == '03' else 'specialist',
                tags=subject_tags(code, name), classification_status='heuristic_reviewable',
                program_urls=program_links, curriculum_urls=plans,
                campaign_association='current_site_navigation_not_individual_confirmation',
                admission_status='requires_campaign_reconciliation',
                provenance=provenance(snapshot, table, row, ti, ri)))
    if not records:
        raise ParseError('no_catalog_rows')
    if len({r['id'] for r in records}) != len(records):
        raise ParseError('duplicate_program_identity_requires_review')
    return dict(records=records, expected_source_rows=expected)


def parse_seats(data, snapshot, campaign_year=2026):
    allocations, totals = [], {}
    root = body(document(data))
    if not re.search(rf'{campaign_year}/{campaign_year + 1}', text(root)):
        raise ParseError('seat_campaign_year_not_confirmed')
    for ti, table in enumerate(root.xpath('.//table')):
        rows, expanded = table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr'), grid(table)
        header = ' '.join(c['text'] for c in expanded[0] if c)
        budget = 'Направления (специальности)' in header and 'УГСН' in header
        paid = f'план приема {campaign_year}' in header.casefold()
        if not budget and not paid:
            raise ParseError('unknown_seat_table')
        by_origin = {}
        for ri, cells in enumerate(expanded[1:], 1):
            values = [c['text'] if c else '' for c in cells]
            if budget:
                if any('ИТОГО' in v for v in values):
                    totals[values[0]] = number(values[-1])
                    continue
                if len(cells) != 4 or cells[2] is None or not CODE.fullmatch(values[2]):
                    raise ParseError('invalid_budget_row')
                codes, names, seat_cell = [values[2]], [values[1]], cells[3]
            else:
                if not cells or not values[0] or values[0] == 'Бакалавриат/специалитет':
                    continue
                if len(cells) != 2:
                    raise ParseError('invalid_paid_row')
                codes, names, seat_cell = CODE.findall(values[0]), [values[0]], cells[1]
                if not codes:
                    raise ParseError('paid_row_missing_code')
            if seat_cell is None or number(seat_cell['text']) is None:
                raise ParseError('seat_value_not_numeric')
            origin = tuple(seat_cell['origin'])
            if origin not in by_origin:
                row_key = digest([snapshot['url'], campaign_year, ti, origin])
                by_origin[origin] = dict(id='mephi-a-' + digest([row_key, snapshot['sha256'], ADAPTER_VERSION])[:24],
                    row_key=row_key, year=campaign_year, campus_id='mephi-moscow',
                    funding='federal_budget_total' if budget else 'paid',
                    places=number(seat_cell['text']), codes=[], field_names=[],
                    scope_label=values[0] if budget else names[0],
                    applicant_basis='foreign_applicants' if 'иностран' in values[0].casefold() else 'not_established',
                    competition_group_status='candidate_from_allocation_not_confirmed',
                    provenance=provenance(snapshot, table, rows[ri], ti, ri), member_row_indices=[])
            item = by_origin[origin]
            item['codes'].extend(codes)
            item['field_names'].extend(names)
            item['member_row_indices'].append(ri)
        allocations.extend(by_origin.values())
    if not allocations:
        raise ParseError('no_seat_allocations')
    return dict(records=allocations, published_totals=totals,
                sum_budget=sum(a['places'] for a in allocations if a['funding'] == 'federal_budget_total'),
                sum_paid=sum(a['places'] for a in allocations if a['funding'] == 'paid'))


def parse_moscow_fields_pdf_text(extracted, snapshot):
    page = extracted.split('\f')[0]
    if 'НИЯУ МИФИ (Москва)' not in page or '2026/2027' not in page:
        raise ParseError('unknown_moscow_field_document')
    records, current = [], None
    for line_number, line in enumerate(page.splitlines(), 1):
        match = CODE.search(line)
        if match:
            if current:
                records.append(current)
            current = dict(official_code=match[0], official_name='', year=2026,
                provenance=dict(source_id=snapshot['source_id'], url=snapshot['url'],
                    snapshot_sha256=snapshot['sha256'], snapshot_path=snapshot['path'],
                    adapter_version=ADAPTER_VERSION, page=1, first_line=line_number,
                    raw_lines=[]))
            remainder = line[match.end():]
        elif current:
            remainder = line
        else:
            continue
        if current:
            current['provenance']['raw_lines'].append(line)
            name_part = re.sub(r'\s+Очная\s*$', '', remainder).strip()
            if name_part:
                current['official_name'] = (current['official_name'] + ' ' + name_part).strip()
    if current:
        records.append(current)
    if not records or len({r['official_code'] for r in records}) != len(records):
        raise ParseError('empty_or_duplicate_pdf_fields')
    return records
