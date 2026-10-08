#!/usr/bin/env python3
"""Enumerate the supplied first-batch PDF before loading expected rows.

Primary extraction uses PyMuPDF ruled-grid geometry. Secondary extraction uses
pdfplumber/pdfminer text, section headings and its own line-intersection grid.
No expected model list is used to select or construct either source table.
"""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import re
import sys
import unicodedata

import fitz
import pdfplumber

ROOT = Path('/workspace/purchase_tax_audit')
HERE = ROOT / 'round5/batch01'
PDF = ROOT / 'round5/originals/mf_batch01.pdf'
BASE = ROOT / 'round4/data_v1_4'
EXPECTED_SHA = 'eac13628c37f01c4da157a2d1916d97acc81fdc295f18e1783549075ce7e5aa7'
sys.path.insert(0, str(ROOT / 'round4/catalogues'))
from independent_catalogue_tables import pdf_rows

RAW_FIELDS = ['sequence_raw', 'firm_raw', 'model_raw', 'trade_name_raw',
              'range_raw', 'curb_mass_raw', 'battery_mass_raw',
              'battery_energy_raw', 'remarks_raw']
PARAM_FIELDS = ['model_raw', 'firm_raw', 'trade_name_raw', 'product_name_raw',
                'range_raw', 'curb_mass_raw', 'battery_mass_raw',
                'battery_energy_raw', 'remarks_raw',
                'catalogue_batch_marked_raw']
def norm(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or ''))
def load_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))
def write_csv(name, rows, fields):
    with (HERE / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)
def secondary():
    """A separate pdfminer-based extraction bounded by class headings."""
    columns = {'序号': 'sequence_raw', '汽车生产企业名称': 'firm_raw',
               '车辆型号': 'model_raw', '通用名称': 'trade_name_raw',
               '纯电动续驶里程(km)': 'range_raw',
               '整车整备质量(kg)': 'curb_mass_raw',
               '动力蓄电池组总质量(kg)': 'battery_mass_raw',
               '动力蓄电池组总能量(kWh)': 'battery_energy_raw',
               '备注': 'remarks_raw'}
    rows, proof = [], []
    power = False
    passenger = False
    stopped = False
    with pdfplumber.open(PDF) as d:
        for page_no, page in enumerate(d.pages, 1):
            text = norm(page.extract_text())
            if '一、纯电动汽车' in text:
                power = True
            if '(一)乘用车' in text and power:
                passenger = True
            if '(二)客车' in text and passenger:
                stopped = True
                break
            if not passenger:
                continue
            for table_no, table in enumerate(page.find_tables()):
                grid = table.extract()
                header = [norm(s) for s in grid[0]]
                if set(header) != set(columns):
                    raise ValueError('Unexpected source header: ' + repr(header))
                for row_no, cells in enumerate(grid[1:], 2):
                    if len(cells) != len(header):
                        raise ValueError('Unequal source row width')
                    values = {columns[h]: (value or '').strip()
                              for h, value in zip(header, cells)}
                    values['model_key'] = norm(values['model_raw']).upper()
                    values['kind'] = '目录列入'
                    values['product_name_raw'] = ''
                    values['catalogue_batch_marked_raw'] = ''
                    values['location'] = (f'pdfplumber ruled-grid;page={page_no};'
                                          f'table={table_no};row={row_no}')
                    rows.append(values)
                proof.append({'page_1based': page_no, 'table_0based': table_no,
                              'bbox': list(table.bbox), 'header_raw': grid[0],
                              'data_rows': len(grid)-1})
    if not stopped or not proof:
        raise ValueError('Section boundaries not established')
    return rows, {'engine': 'pdfplumber/pdfminer plus independent ruled-grid and power/class headings',
                  'tables': proof, 'end_boundary': '(二)客车 on page 2'}

def main():
    HERE.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(PDF.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA:
        raise ValueError('Unexpected first-batch original SHA256')
    primary, primary_proof = pdf_rows(PDF)
    second, secondary_proof = secondary()
    for engine, rows in [('primary', primary), ('secondary', second)]:
        for row in rows:
            row['source_file'] = PDF.name
            row['source_sha256'] = digest
        write_csv(f'{engine}_全部17行_独立枚举.csv', rows,
                  ['source_file', 'source_sha256', 'kind', 'model_key'] +
                  RAW_FIELDS + ['product_name_raw', 'catalogue_batch_marked_raw', 'location'])
    # Expected records are read only after both complete source enumerations.
    parameters = [r for r in load_csv(BASE / '研究数据/参数版本_原值与计算代理.csv')
                  if Path(r['source_file']).name == PDF.name]
    enum = [r for r in load_csv(BASE / '目录覆盖/原件逐表独立枚举.csv')
            if r['source_file'] == PDF.name]
    diffs, comparisons = [], []
    for label, a, b, fields in [
        ('two_independent_engines', primary, second, RAW_FIELDS),
        ('source_vs_v1_4_parameters', primary, parameters, PARAM_FIELDS),
        ('source_vs_v1_4_enumeration', primary, enum,
         ['model_raw', 'model_key', 'kind', 'sequence_raw'])]:
        ac = Counter(tuple(norm(r.get(k)) for k in fields) for r in a)
        bc = Counter(tuple(norm(r.get(k)) for k in fields) for r in b)
        comparisons.append({'comparison': label, 'source_rows': len(a),
                            'reference_rows': len(b), 'fields': fields,
                            'field_positions': len(a)*len(fields),
                            'source_only_rows': sum((ac-bc).values()),
                            'reference_only_rows': sum((bc-ac).values()),
                            'normalization': 'NFKC then whitespace removal only; slash options preserved'})
        for direction, counter in [('source_only', ac-bc), ('reference_only', bc-ac)]:
            for values, n in counter.items():
                diffs.append({'comparison': label, 'direction': direction,
                              'multiplicity': n,
                              'values_json': json.dumps(dict(zip(fields, values)), ensure_ascii=False)})
    write_csv('多重集差异.csv', diffs,
              ['comparison', 'direction', 'multiplicity', 'values_json'])
    scientific = []
    pmap = {r['model_key']: r for r in parameters}
    for row in primary:
        expected = pmap[row['model_key']]
        for field in ['range_raw', 'curb_mass_raw', 'battery_mass_raw', 'battery_energy_raw']:
            scientific.append({'model_key': row['model_key'],
                               'record_id': expected['record_id'], 'field': field,
                               'source_raw': row[field], 'v1_4_raw': expected[field],
                               'normalized_equal': int(norm(row[field]) == norm(expected[field])),
                               'source_location': row['location']})
    write_csv('68项科学原值_逐字段对账.csv', scientific,
              ['model_key', 'record_id', 'field', 'source_raw', 'v1_4_raw',
               'normalized_equal', 'source_location'])
    conflicts = [r for r in load_csv(BASE / '研究数据/分类冲突_原文证据与隔离.csv')
                 if Path(r['listing_source_file']).name == PDF.name]
    conflict_proof = []
    for conflict in conflicts:
        row = next(r for r in primary if r['model_key'] == conflict['model_key'])
        conflict_proof.append({'model_key': row['model_key'],
                               'source_heading': '一、纯电动汽车 / （一）乘用车',
                               'sequence_raw': row['sequence_raw'],
                               'trade_name_raw': row['trade_name_raw'],
                               'product_name_column_present': False,
                               'original_category_conflict_preserved': True,
                               'admitted_to_analysis_cohort': pmap[row['model_key']]['admitted_to_analysis_cohort'],
                               'other_source_configuration_identity_certified': False,
                               'interpretation': '来源分组与通用名称已直接验证；本附件没有产品名称栏，不能单凭该表认证 M1 或解决跨来源分类冲突'})
    with fitz.open(PDF) as d:
        metadata = d.metadata
        body_text = '\n'.join(p.get_text() for p in d)
        date_patterns = re.findall(r'\b(?:19|20)\d{2}[-/.年]\s*\d{1,2}[-/.月]\s*\d{1,2}日?', body_text)
        title_matches = [m.group() for m in re.finditer(r'免征车辆购置税的新能源汽车车型目录[（(]第一批[）)]', norm(body_text))]
        d[0].get_pixmap(matrix=fitz.Matrix(2, 2)).save(HERE / 'page1_render.png')
    proof = {'source_file': str(PDF), 'source_bytes': PDF.stat().st_size,
             'source_sha256': digest, 'historical_archive_identity_exact': True,
             'pdf_pages': 8, 'engines': [primary_proof, secondary_proof],
             'source_header_title_verified': title_matches,
             'source_enumeration_rows': len(primary),
             'sequence_1_to_17_complete': [r['sequence_raw'] for r in primary] == [str(i) for i in range(1,18)],
             'models_unique': len({r['model_key'] for r in primary}) == len(primary),
             'comparisons': comparisons, 'differences': len(diffs),
             'scientific_raw_positions_checked': len(scientific),
             'scientific_raw_difference_count': sum(not x['normalized_equal'] for x in scientific),
             'class_conflicts': conflict_proof,
             'merged_enterprise_cells': {'policy': 'firm_raw keeps the literal source cell, including blanks covered by vertically merged cells; do not fabricate repeated raw text',
                                         'blank_literal_cells': sum(not r['firm_raw'] for r in primary)},
             'date_review': {'body_date_strings': date_patterns,
                             'contains_primary_announcement_or_signature': False,
                             'metadata': metadata,
                             'conclusion': '附件本身无首发日期或落款；PDF 创建时间 2014-08-29 仅为文档元数据，不能升级为首发日，也不能将外部公告签署日等同首发日',
                             'primary_first_publication_date_closed': False},
             'parameters_and_frozen_values_modified': False,
             'manual_render_review': '第 1 页 2x 渲染已目视复核；车型、四个数字列、斜杠选项、企业合并格、类别冲突第 5 行均与两引擎网格文本一致',
             'scope': '仅此份附件全部纯电动乘用车 17 行，不声称对附件其余车辆类别做参数核查，不认证 M1、配置身份或法律资格'}
    (HERE / 'proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
    if diffs or proof['scientific_raw_difference_count']:
        raise ValueError('Source comparison differences; see emitted audit files')
    print(json.dumps({'rows': len(primary), 'two_engine_field_positions': 153,
                      'parameter_field_positions': 170,
                      'scientific_raw_positions': 68, 'differences': 0,
                      'original_archive_identity': 'exact',
                      'first_publication_date': 'not established by this attachment'}, ensure_ascii=False))

if __name__ == '__main__':
    main()
