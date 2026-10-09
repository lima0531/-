#!/usr/bin/env python3
"""Read-only boundary audit; no study model list or previous row count loaded."""
from pathlib import Path
from collections import Counter
import csv, hashlib, json, re, subprocess, sys, unicodedata, zipfile
import xml.etree.ElementTree as ET
import fitz

ROOT = Path('/workspace/purchase_tax_audit')
OUT = ROOT / 'round6/batch64_boundary'
SOURCE = ROOT / 'round5/originals/mf_batch64.doc'
sys.path.insert(0, str(ROOT / 'round3/archive'))
from word_piece_text import extract
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'

def norm(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', s or ''))

def savetext(name, text):
    (OUT / name).write_text(text, encoding='utf-8')

def savecsv(name, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)

def savejson(name, value):
    savetext(name, json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def celltext(tc):
    return '\n'.join(''.join(x.text or '' for x in p.iterfind('.//w:t', NS))
                     for p in tc.findall('w:p', NS))

def isheader(cs):
    return len(cs) >= 3 and norm(cs[0]) == '序号' and norm(cs[2]) == '车辆型号'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_sha != 'c4e238989e7e40ec2c3a6a899ead170b4a745bc72546ba6fd4a5731d8890c6cb':
        raise ValueError('Source differs from uploaded original fingerprint')
    for fmt in ['docx', 'pdf']:
        subprocess.run(['soffice', '-env:UserInstallation=file:///tmp/batch64_round6_lo_profile',
                        '--headless', '--convert-to', fmt, '--outdir', str(OUT), str(SOURCE)],
                       check=True, capture_output=True, text=True)
    text, native_proof = extract(SOURCE)
    savetext('原DOC_完整主文档.txt', text)
    # Bound by source class headings, then isolate table before narrative.
    heading = re.search(r'一、纯电动汽车\s*\n[（(]一[)）]乘用车\s*\n', text)
    if not heading:
        raise ValueError('Original power/class heading missing')
    section_start = heading.end()
    nextheading = re.search(r'\n[（(]二[)）]客车\s*\n', text[section_start:])
    if not nextheading:
        raise ValueError('Original next class heading missing')
    section_end = section_start + nextheading.start()
    section = text[section_start:section_end]
    narrative = section.find('勘误：')
    if narrative < 0:
        raise ValueError('Expected narrative boundary missing')
    table_text = section[:narrative]
    narrative_literals = re.findall(r'勘误：[\s\S]*?。', section[narrative:])
    narrative_rows = []
    for literal in narrative_literals:
        match = re.search(r'牌([A-Z][A-Z0-9-]+).*?纯电动续驶里程应为([\d.]+)km', literal)
        if not match:
            raise ValueError('BEV passenger narrative correction is not independently parsable')
        narrative_rows.append(dict(source_sha256=source_sha,
                                   observation_kind='仅续航文字勘误',
                                   model_raw=match[1], range_corrected_raw=match[2],
                                   included_as_parameter_observation=1,
                                   included_as_new_listing_table_row=0,
                                   source_cell_0based=text[:text.index(literal)].count('\t'),
                                   power_section='纯电动汽车', vehicle_class_section='乘用车',
                                   source_quote=literal))
    savecsv('乘用车独立文字勘误_与表格记录分开.csv', narrative_rows)
    logical_cells = table_text.split('\t')
    if logical_cells[-1].strip():
        raise ValueError('Native final row marker/boundary not empty')
    logical_cells = logical_cells[:-1]
    header_candidate = logical_cells[:10]
    if not isheader(header_candidate) or header_candidate[9] != '':
        raise ValueError('Native header/cell boundary unsupported')
    stride = len(header_candidate)
    if len(logical_cells) % stride:
        raise ValueError('Native table residue: possible overlooked row')
    native_rows = []
    for start in range(0, len(logical_cells), stride):
        block = logical_cells[start:start + stride]
        if block[-1] != '':
            raise ValueError('Native row-ending marker malformed')
        h = isheader(block)
        native_rows.append(dict(engine='CFB_CLX_native_main_story', source_sha256=source_sha,
                                physical_table_row_1based=start // stride + 1,
                                source_cell_start_0based=start,
                                source_model_cell_0based=start + 2,
                                source_sequence_text=block[0], model_raw=block[2],
                                firm_raw=block[1], trade_name_raw=block[3],
                                range_raw=block[4], curb_mass_raw=block[5],
                                battery_mass_raw=block[6], battery_energy_raw=block[7],
                                remarks_raw=block[8], power_section='纯电动汽车',
                                vehicle_class_section='乘用车', row_is_header=int(h),
                                row_is_data=int(not h),
                                extraction_reason='原文明确章节及表头；按完整原表列宽和行终止单元逐行枚举，未加载研究型号',
                                inclusion_reason='表头，排除车型计数' if h else '純电动乘用车原表数据行，纳入车型计数'))
    savecsv('原DOC_乘用车含表头逐行位置.csv', native_rows)
    # Fresh OOXML: inspect every table and every row throughout the document.
    z = zipfile.ZipFile(OUT / 'mf_batch64.docx')
    doc = ET.fromstring(z.read('word/document.xml'))
    body = doc.find('w:body', NS)
    numdoc = ET.fromstring(z.read('word/numbering.xml'))
    numbering = {}
    for num in numdoc.findall('w:num', NS):
        nid = num.get(W + 'numId')
        aid = num.find('w:abstractNumId', NS).get(W + 'val')
        abstract = next(a for a in numdoc.findall('w:abstractNum', NS)
                        if a.get(W + 'abstractNumId') == aid)
        level = abstract.find('w:lvl', NS)
        numbering[nid] = dict(numId=nid, abstractNumId=aid,
                              start=int(level.find('w:start', NS).get(W + 'val')),
                              format=level.find('w:numFmt', NS).get(W + 'val'),
                              label=level.find('w:lvlText', NS).get(W + 'val'))
    power = ''; vehicle_class = ''; ti = 0
    allrows = []; tables = []; flow = []; counters = Counter()
    for body_index, el in enumerate(body, 1):
        if el.tag == W + 'p':
            literal = ''.join(t.text or '' for t in el.iterfind('.//w:t', NS))
            normalized = norm(literal)
            ph = re.fullmatch(r'[一二三]、(纯电动汽车|插电式混合动力汽车|燃料电池汽车)', normalized)
            ch = re.fullmatch(r'\([一二三四]\)(乘用车|客车|货车|专用车)', normalized)
            if ph:
                power = ph[1]; vehicle_class = ''
            if ch:
                vehicle_class = ch[1]
            flow.append(dict(body_element_1based=body_index, element_type='paragraph',
                             table_1based='', paragraph_text=literal,
                             power_section=power, vehicle_class_section=vehicle_class))
        elif el.tag == W + 'tbl':
            ti += 1
            trs = el.findall('w:tr', NS)
            table_header_count = 0; table_data_count = 0
            for ri, tr in enumerate(trs, 1):
                tcs = tr.findall('w:tc', NS); cs = [celltext(tc) for tc in tcs]
                h = isheader(cs); table_header_count += h; table_data_count += not h
                num = tcs[0].find('.//w:numPr/w:numId', NS)
                nid = num.get(W + 'val') if num is not None else ''
                ilvl = tcs[0].find('.//w:numPr/w:ilvl', NS)
                autonumber = ''
                if nid:
                    if numbering[nid]['format'] != 'decimal':
                        raise ValueError('Unsupported autonumber format')
                    autonumber = numbering[nid]['start'] + counters[nid]
                    counters[nid] += 1
                selected = power == '纯电动汽车' and vehicle_class == '乘用车' and not h
                allrows.append(dict(engine='fresh_LO_DOCX_OOXML', source_sha256=source_sha,
                                    body_element_1based=body_index, table_1based=ti, table_0based=ti - 1,
                                    physical_table_row_1based=ri, physical_column_count=len(tcs),
                                    row_is_header=int(h), row_is_data=int(not h),
                                    header_repeat_on_each_page=int(tr.find('w:trPr/w:tblHeader', NS) is not None),
                                    source_sequence_text=cs[0], automatic_sequence=autonumber,
                                    automatic_numId=nid, automatic_ilvl=ilvl.get(W + 'val') if ilvl is not None else '',
                                    model_raw=cs[2], firm_raw=cs[1], trade_or_product_name_raw=cs[3],
                                    power_section=power, vehicle_class_section=vehicle_class,
                                    included_in_BEV_passenger_data=int(selected),
                                    extraction_reason='遍历整个文档全部body表和全部tr；未按研究型号筛选',
                                    inclusion_reason='表头，排除数据计数' if h else
                                    '本节纯电动乘用车数据行' if selected else
                                    '其他类别/动力章节数据行，排除纯电动乘用车范围',
                                    all_cell_text_json=json.dumps(cs, ensure_ascii=False)))
            tables.append(dict(table_1based=ti, table_0based=ti - 1, body_element_1based=body_index,
                               power_section=power, vehicle_class_section=vehicle_class,
                               physical_rows=len(trs), header_rows=table_header_count,
                               data_rows=table_data_count,
                               included_in_BEV_passenger_scope=int(power == '纯电动汽车' and vehicle_class == '乘用车')))
            flow.append(dict(body_element_1based=body_index, element_type='table',
                             table_1based=ti, paragraph_text='', power_section=power,
                             vehicle_class_section=vehicle_class))
    savecsv('全篇DOCX_所有表所有行物理位置与纳排理由.csv', allrows)
    savecsv('全篇DOCX_逐表章节边界与行数.csv', tables)
    savecsv('全篇DOCX_标题勘误与表格顺序.csv', flow)
    savejson('DOCX_自动编号定义.json', numbering)
    lotext = '\n'.join(''.join(x.text or '' for x in p.iterfind('.//w:t', NS))
                       for p in doc.iterfind('.//w:p', NS))
    text_equal = norm(lotext) == norm(text)
    if not text_equal:
        raise ValueError('Fresh DOCX main story differs from original CFB text')
    native_data = [x for x in native_rows if not x['row_is_header']]
    xml_data = [x for x in allrows if x['included_in_BEV_passenger_data']]
    if [norm(x['model_raw']) for x in native_data] != [norm(x['model_raw']) for x in xml_data]:
        raise ValueError('Native and fresh XML ordered model rows differ')
    # PDF is a pagination/numbering check, not a new independent source.
    pdf = fitz.open(OUT / 'mf_batch64.pdf')
    fragments = []; pdfrows = []; scope_done = False
    for pi, page in enumerate(pdf):
        if scope_done:
            break
        stoprects = page.search_for('（二）客车')
        stop_y = min(r.y0 for r in stoprects) if stoprects else float('inf')
        for pti, tab in enumerate(page.find_tables().tables, 1):
            if tab.bbox[1] >= stop_y:
                continue
            rows = tab.extract()
            if not rows or not isheader(rows[0]) or norm(rows[0][3]) != '通用名称':
                continue
            hcount = 0; dcount = 0
            for ri, cs in enumerate(rows, 1):
                h = isheader(cs); hcount += h; dcount += not h
                pdfrows.append(dict(engine='fresh_LO_rendered_PDF_geometry', source_sha256=source_sha,
                                    page_1based=pi + 1, page_table_1based=pti,
                                    physical_fragment_row_1based=ri, row_is_header=int(h),
                                    printed_sequence=cs[0] or '', model_raw=cs[2] or '',
                                    power_section='纯电动汽车', vehicle_class_section='乘用车',
                                    row_is_data=int(not h), extraction_reason='分页图形表格内完整原列；重复表头标注后排除数据计数',
                                    bbox=json.dumps(list(tab.rows[ri - 1].bbox))))
            fragments.append(dict(page_1based=pi + 1, page_table_1based=pti,
                                  physical_fragment_rows=len(rows), header_rows=hcount,
                                  data_rows=dcount, bbox=json.dumps(list(tab.bbox))))
        if stoprects:
            scope_done = True
        if pi < 2:
            page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(OUT / f'第{pi + 1}页_编号和章节.png')
    if not scope_done:
        raise ValueError('Rendered PDF did not reach next class heading')
    savecsv('PDF分页_乘用车全部表片段物理行.csv', pdfrows)
    savecsv('PDF分页_逐表片段计数.csv', fragments)
    pdf_data = [x for x in pdfrows if x['row_is_data']]
    same_pdf_models = [norm(x['model_raw']) for x in pdf_data] == [norm(x['model_raw']) for x in native_data]
    numeric_sequences = [int(norm(x['printed_sequence'])) for x in pdf_data]
    xml_sequences = [x['automatic_sequence'] for x in xml_data]
    contiguous_sequences = numeric_sequences == list(range(1, len(native_data) + 1))
    if not same_pdf_models or not contiguous_sequences or xml_sequences != numeric_sequences:
        raise ValueError('Rendered numbering/models do not match native data rows')
    # Materialize the complete passenger section as parameter observations:
    # table listings and narrative correction remain different record types.
    observation_fields = ['source_sha256', 'source_file', 'observation_kind',
                          'model_raw', 'model_key', 'firm_raw', 'trade_name_raw',
                          'product_name_raw', 'range_raw', 'curb_mass_raw',
                          'battery_mass_raw', 'battery_energy_raw', 'remarks_raw',
                          'catalogue_batch_marked_raw']
    observations = []
    for ordinal, row in enumerate(native_data, 1):
        observation = {k: row.get(k, '') for k in observation_fields}
        observation.update(source_file=SOURCE.name, source_sha256=source_sha,
                           observation_kind='目录列入', model_key=norm(row['model_raw']).upper(),
                           section_observation_ordinal=ordinal,
                           source_table_0based=0,
                           source_physical_row_1based=row['physical_table_row_1based'],
                           source_cell_0based=row['source_cell_start_0based'],
                           printed_data_sequence=numeric_sequences[ordinal - 1],
                           narrative_quote='', sparse_correction_record=0)
        observations.append(observation)
    for row in narrative_rows:
        observation = {k: '' for k in observation_fields}
        observation.update(source_file=SOURCE.name, source_sha256=source_sha,
                           observation_kind='仅续航文字勘误', model_raw=row['model_raw'],
                           model_key=norm(row['model_raw']).upper(), range_raw=row['range_corrected_raw'],
                           section_observation_ordinal=len(observations) + 1,
                           source_table_0based='', source_physical_row_1based='',
                           source_cell_0based=row['source_cell_0based'],
                           printed_data_sequence='', narrative_quote=row['source_quote'],
                           sparse_correction_record=1)
        observations.append(observation)
    # Existing raw parameters are a comparator, loaded after extraction only.
    raw_path = ROOT / 'round5/reconstruction/data_v1_5/研究数据/参数版本_原值与计算代理.csv'
    with raw_path.open(encoding='utf-8-sig') as f:
        comparator = [dict(x, source_file=Path(x['source_file']).name)
                      for x in csv.DictReader(f) if Path(x['source_file']).name == SOURCE.name]
    def observation_tuple(x):
        return tuple(norm(x.get(k, '')) for k in observation_fields)
    source_multiset = Counter(observation_tuple(x) for x in observations)
    comparator_multiset = Counter(observation_tuple(x) for x in comparator)
    missing = comparator_multiset - source_multiset
    extra = source_multiset - comparator_multiset
    comparator_ids = {observation_tuple(x): x['record_id'] for x in comparator}
    for x in observations:
        x['matched_v1_5_raw_record_id'] = comparator_ids.get(observation_tuple(x), '')
        x['normalized_raw_field_multiset_match'] = int(observation_tuple(x) in comparator_ids)
    savecsv('第64批_完整乘用小节41参数记录独立对账.csv', observations)
    observation_differences = []
    for direction, counter in [('existing_raw_only', missing), ('independent_source_only', extra)]:
        for values, count in counter.items():
            observation_differences.append(dict(direction=direction, multiplicity=count,
                                                **dict(zip(observation_fields, values))))
    with (OUT / '41参数观察记录_双向多重集差异.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, ['direction', 'multiplicity'] + observation_fields)
        w.writeheader(); w.writerows(observation_differences)
    raw_comparison = dict(existing_raw_parameter_file=str(raw_path),
                          existing_raw_parameter_file_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                          normalized_comparison_fields=observation_fields,
                          independently_extracted_parameter_observations=len(observations),
                          existing_raw_parameter_records=len(comparator),
                          source_observation_kind_counts=dict(Counter(x['observation_kind'] for x in observations)),
                          existing_raw_observation_kind_counts=dict(Counter(x['observation_kind'] for x in comparator)),
                          existing_only_multiset_records=sum(missing.values()),
                          source_only_multiset_records=sum(extra.values()),
                          all_source_records_matched=int(all(x['matched_v1_5_raw_record_id'] for x in observations)),
                          narrative_uncorrected_mass_energy_fields_remain_blank=True,
                          fields_filled_from_other_catalogue=False,
                          scientific_tables_modified=False)
    savejson('41参数观察记录_原值表双向对账.json', raw_comparison)
    if missing or extra:
        raise ValueError('Complete source section differs from existing raw parameter records')
    summary = dict(source_file=str(SOURCE), source_bytes=SOURCE.stat().st_size,
                   source_sha256=source_sha,
                   source_matches_historic_sha256=True,
                   independent_scope='只从原文动力/类别标题和原表结构确定范围；未读取研究型号或以前40行结论',
                   native_logical_cell_count_before_narrative=len(logical_cells),
                   native_row_stride=stride, native_physical_table_rows=len(native_rows),
                   native_header_rows=sum(x['row_is_header'] for x in native_rows),
                   native_data_rows=len(native_data),
                   native_BEV_passenger_table_first_model=native_data[0]['model_raw'],
                   native_BEV_passenger_table_last_model=native_data[-1]['model_raw'],
                   independent_BEV_passenger_narrative_corrections=narrative_rows,
                   total_BEV_passenger_parameter_observations_in_this_source=len(native_data) + len(narrative_rows),
                   parameter_observation_count_scope='40表格列入记录+1独立仅续航勘误=41参数观察记录；文字勘误不计新增车型列入',
                   complete_section_v1_5_raw_parameter_reconciliation=raw_comparison,
                   fresh_docx_all_body_tables=len(tables),
                   fresh_docx_all_physical_rows=len(allrows),
                   fresh_docx_BEV_passenger_tables=[x for x in tables if x['included_in_BEV_passenger_scope']],
                   fresh_docx_BEV_passenger_data_rows=len(xml_data),
                   fresh_docx_second_table=tables[1],
                   pdf_total_document_pages=len(pdf), PDF_BEV_passenger_fragments=fragments,
                   PDF_BEV_passenger_data_rows=len(pdf_data),
                   PDF_printed_automatic_sequence_first=numeric_sequences[0],
                   PDF_printed_automatic_sequence_last=numeric_sequences[-1],
                   PDF_sequences_contiguous=contiguous_sequences,
                   original_and_fresh_docx_complete_main_story_equal=text_equal,
                   native_DOC_DOCX_and_rendered_PDF_ordered_models_equal=same_pdf_models,
                   next_class_heading='（二）客车',
                   next_class_heading_source_char_0based=section_end,
                   correction_source_cell_0based=text[:section_start + narrative].count('\t'),
                   correction_included_as_new_table_model=False,
                   data_row_conclusion=len(native_data),
                   reported_two_fragments_27_plus_14_reproduced=False,
                   reported_41_is_physical_row_count_if_one_header_included=True,
                   explanatory_limit='本次上传同SHA原件的原表为1表、41物理行=1表头+40数据行。本地分页为两页20+20数据行，每页各重复1表头。用户所指27+14具体切分未复现，未凭猜测认定其误差来源；另一转换文件若有不同结构需单独比对。',
                   root_scientific_tables_modified=False)
    savejson('source_native_proof.json', native_proof)
    savejson('boundary_verification_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
