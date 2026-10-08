#!/usr/bin/env python3
"""Fully enumerate batch 64 BEV passenger tables before loading comparators.

CFB/CLX and LibreOffice OOXML are independent extraction paths.  Conversion
is a local format operation; converted files are companions, never originals.
The table flow and headers determine the population; no known-model seed is
used to extract rows.  v1.4 is read only, and no scientific data are changed.
"""
from pathlib import Path
from collections import Counter
import csv, hashlib, json, re, subprocess, sys, zipfile
import xml.etree.ElementTree as ET

ROOT = Path('/workspace/purchase_tax_audit')
OUT = ROOT / 'round5/batch64'
ORIGINAL = ROOT / 'round5/originals/mf_batch64.doc'
SOURCE62 = ROOT / 'round3/archive/recovered/免征目录/mf_batch62.doc'
BASE = ROOT / 'round4/data_v1_4'
sys.path.insert(0, str(ROOT / 'round4/catalogues'))
from independent_catalogue_tables import cfb_rows, zip_rows, norm, NS
from word_piece_text import extract

SHA64 = 'c4e238989e7e40ec2c3a6a899ead170b4a745bc72546ba6fd4a5731d8890c6cb'
SHA62 = '7694ac7207998b6af7c895cdd2c1d752421df436d4b28f83195261dd47f6509c'
CELL_FIELDS = ['sequence_raw', 'firm_raw', 'model_raw', 'trade_name_raw',
               'range_raw', 'curb_mass_raw', 'battery_mass_raw',
               'battery_energy_raw', 'remarks_raw']
PARAM_FIELDS = ['model_key', 'kind', 'range_raw', 'curb_mass_raw',
                'battery_mass_raw', 'battery_energy_raw', 'remarks_raw',
                'trade_name_raw', 'product_name_raw',
                'catalogue_batch_marked_raw', 'firm_raw']

def load(p):
    return list(csv.DictReader(p.open(encoding='utf-8-sig')))

def savecsv(name, rows, fields=None):
    if fields is None:
        fields = list(rows[0]) if rows else []
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)

def savejson(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def converted(p):
    subprocess.run(['soffice', '-env:UserInstallation=file:///tmp/batch64_final_lo_profile',
                    '--headless', '--convert-to', 'docx', '--outdir', str(OUT), str(p)],
                   capture_output=True, text=True, check=True)
    result = OUT / (p.stem + '.docx')
    if not result.exists():
        raise ValueError('LibreOffice did not create expected companion')
    return result

def lo_text(p):
    root = ET.fromstring(zipfile.ZipFile(p).read('word/document.xml'))
    return '\n'.join(''.join(t.text or '' for t in par.iterfind('.//w:t', NS))
                     for par in root.iterfind('.//w:p', NS))

def rowdiff(a, b, fields, comparison):
    if len(a) != len(b):
        raise ValueError(f'{comparison}: row counts differ {len(a)} != {len(b)}')
    out = []
    for ordinal, (x, y) in enumerate(zip(a, b), 1):
        for field in fields:
            if norm(x.get(field, '')) != norm(y.get(field, '')):
                out.append(dict(comparison=comparison, row_ordinal=ordinal,
                                model_key=x['model_key'], field=field,
                                left_raw=x.get(field, ''), right_raw=y.get(field, '')))
    return out

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest() != SHA64:
        raise ValueError('Batch 64 historic fingerprint mismatch')
    if hashlib.sha256(SOURCE62.read_bytes()).hexdigest() != SHA62:
        raise ValueError('Referred batch 62 historic fingerprint mismatch')
    # Extraction is completed before any existing research table is loaded.
    text64, textproof64 = extract(ORIGINAL)
    got64, proof64 = cfb_rows(ORIGINAL)
    docx64 = converted(ORIGINAL)
    lo64, loproof64 = zip_rows(docx64)
    lotext64 = lo_text(docx64)
    (OUT / 'cfb_main_story.txt').write_text(text64, encoding='utf-8')
    (OUT / 'libreoffice_main_story.txt').write_text(lotext64, encoding='utf-8')
    engine_differences = rowdiff(got64, lo64, CELL_FIELDS, 'batch64_CFB_vs_LO')
    main_story_equal = norm(text64) == norm(lotext64)
    if not main_story_equal:
        raise ValueError('Whole main story differs between CFB and LO text')
    clauses = []
    for m in re.finditer(r'勘误：[\s\S]*?。', text64):
        literal = m.group()
        clauses.append(dict(source_file=ORIGINAL.name, source_sha256=SHA64,
                            source_char_0based=m.start(),
                            source_cell_0based=text64[:m.start()].count('\t'),
                            original_quote=literal,
                            lo_literal_equal=norm(literal) in norm(lotext64)))
    bev_clauses = [x for x in clauses if '纯电动乘用车部分' in x['original_quote']]
    if len(bev_clauses) != 1:
        raise ValueError('Unexpected BEV correction count')
    correction = bev_clauses[0]
    matched = re.search(r'第六十二批.*?第(\d+)项.*?牌([A-Z][A-Z0-9-]+).*?纯电动续驶里程应为([\d.]+)km',
                        correction['original_quote'])
    if not matched:
        raise ValueError('Cannot parse literal correction scope')
    ref_ordinal, ref_model, corrected_range = int(matched[1]), matched[2], matched[3]
    correction.update(model_key=ref_model, referred_batch='62',
                      referred_BEV_passenger_item=ref_ordinal,
                      changed_field='range_raw', corrected_value=corrected_range,
                      change_type='field_specific_replacement',
                      unchanged_fields='curb_mass_raw;battery_mass_raw;battery_energy_raw',
                      interpretation='原文仅更正续驶里程；其他原表字段未声明变更。未更正字段继承必须保留62批字段来源，不能将64批稀疏勘误记录的空白当成车型缺值。')
    got62, proof62 = cfb_rows(SOURCE62)
    docx62 = converted(SOURCE62)
    lo62, loproof62 = zip_rows(docx62)
    referred = got62[ref_ordinal - 1]
    referred_lo = lo62[ref_ordinal - 1]
    if referred['model_key'] != ref_model or referred_lo['model_key'] != ref_model:
        raise ValueError('Narrative reference ordinal does not resolve to the same original model')
    engine_differences.extend(rowdiff([referred], [referred_lo], CELL_FIELDS, 'batch62_referred_row_CFB_vs_LO'))
    context_start = max(0, correction['source_cell_0based'] - 10)
    cells = text64.split('\t')
    context = [dict(source_cell_0based=i, cell_raw=cells[i])
               for i in range(context_start, min(len(cells), correction['source_cell_0based'] + 10))]
    effective = dict(referred, range_raw=corrected_range,
                     range_source_file='mf_batch64.doc', range_source_sha256=SHA64,
                     unchanged_fields_source_file='mf_batch62.doc', unchanged_fields_source_sha256=SHA62,
                     effective_record_kind='字段级勘误重构候选，仅新增旁表证据，未写入v1.4',
                     configuration_certificate='未取得跨目录配置身份证明；原文明确绑定62批同一项，不采用2023-12-26记录补值')
    for i, row in enumerate(got64, 1):
        row.update(source_file=ORIGINAL.name, source_sha256=SHA64,
                   source_batch='64', source_BEV_passenger_row_ordinal=i,
                   independent_LO_location=lo64[i - 1]['location'])
    # Only now load comparators. Existing values never determine extraction.
    parameter_path = BASE / '研究数据/参数版本_原值与计算代理.csv'
    enumeration_path = BASE / '目录覆盖/原件逐表独立枚举.csv'
    parameters = [x for x in load(parameter_path) if Path(x['source_file']).name == ORIGINAL.name]
    param_listing = [dict(x, kind=x['observation_kind']) for x in parameters
                     if x['observation_kind'] == '目录列入']
    # Research rows use record-id ordering rather than physical source order.
    # Align only after enumeration, and require uniqueness before using a map.
    param_models = [x['model_key'] for x in param_listing]
    got_models = [x['model_key'] for x in got64]
    if len(set(param_models)) != len(param_models) or len(set(got_models)) != len(got_models):
        raise ValueError('Duplicate model rows require multiset matching instead of row map')
    if Counter(param_models) != Counter(got_models):
        raise ValueError('Existing parameter model multiset differs from independently enumerated table')
    param_by_model = {x['model_key']: x for x in param_listing}
    param_aligned = [param_by_model[x['model_key']] for x in got64]
    comparison_differences = rowdiff(got64, param_aligned, PARAM_FIELDS, 'batch64_CFB_vs_v1.4_parameters')
    observed_models = Counter(x['model_key'] for x in got64)
    enumerated = [x for x in load(enumeration_path) if Path(x['source_file']).name == ORIGINAL.name]
    expected_models = Counter(x['model_key'] for x in enumerated)
    model_multiset_equal = observed_models == expected_models
    narrative_records = [x for x in parameters if x['observation_kind'] == '仅续航文字勘误']
    if len(narrative_records) != 1:
        raise ValueError('Unexpected existing narrative record count')
    nr = narrative_records[0]
    narrative_issues = []
    for field, expected in [('model_key', ref_model), ('range_raw', corrected_range),
                            ('source_sha256', SHA64), ('source_location', 'source_cell_0based=' + str(correction['source_cell_0based']))]:
        if nr[field] != expected:
            narrative_issues.append(dict(field=field, retained=nr[field], source=expected))
    actual_science_blank = {x: nr[x] == '' for x in ['curb_mass_raw', 'battery_mass_raw', 'battery_energy_raw']}
    differences = engine_differences + comparison_differences
    savecsv('第64批_纯电动乘用车独立全表40行.csv', got64)
    savecsv('第64批_全部文字勘误2条.csv', clauses)
    savecsv('第64批_SGM6500BEBEV_原文限定字段勘误.csv', [correction])
    savecsv('第62批_SGM6500BEBEV_被更正原表全列.csv', [dict(referred, source_file=SOURCE62.name, source_sha256=SHA62, source_BEV_passenger_row_ordinal=ref_ordinal)])
    savecsv('第64批_勘误source_cell410周围原文.csv', context)
    savecsv('SGM6500BEBEV_字段级更正后的参数_证据旁表.csv', [effective])
    savecsv('逐字段对账差异.csv', differences, ['comparison', 'row_ordinal', 'model_key', 'field', 'left_raw', 'right_raw'])
    proofs = {'batch64_cfb': proof64, 'batch64_lo_ooxml': loproof64,
              'batch62_cfb': proof62, 'batch62_lo_ooxml': loproof62,
              'cfb_main_story': textproof64,
              'whole_main_story_whitespace_normalized_equal': main_story_equal,
              'whole_main_story_normalized_characters': len(norm(text64)),
              'conversion': 'soffice headless DOC -> DOCX in isolated /tmp/batch64_final_lo_profile; XML flow/table parser separate from CFB/CLX parser'}
    savejson('extraction_proofs.json', proofs)
    summary = dict(source_sha256=SHA64, source_bytes=ORIGINAL.stat().st_size,
                   recovered_historical_exact=True, independently_enumerated_BEV_passenger_table_rows=len(got64),
                   narrative_BEV_corrections=len(bev_clauses), all_powertrain_narrative_corrections=len(clauses),
                   dual_engine_comparison_fields=CELL_FIELDS,
                   dual_engine_batch64_field_comparisons=len(got64) * len(CELL_FIELDS),
                   dual_engine_batch62_referred_field_comparisons=len(CELL_FIELDS),
                   dual_engine_differences=len(engine_differences),
                   base_parameter_field_comparisons=len(got64) * len(PARAM_FIELDS),
                   base_parameter_differences=len(comparison_differences),
                   existing_enumeration_model_multiset_equal=model_multiset_equal,
                   narrative_record_differences=narrative_issues,
                   narrative_sparse_unmodified_fields_are_blank=actual_science_blank,
                   field_specific_correction_from='502', field_specific_correction_to=corrected_range,
                   preserved_curb_mass_from_batch62='2620', preserved_battery_mass_from_batch62='620',
                   preserved_battery_energy_from_batch62='95.7',
                   corrected_record_source_cell=correction['source_cell_0based'],
                   future_information_used=False, base_tables_modified=False,
                   methodological_finding='当前仅续航文字勘误是稀疏更正记录。原文直接指定第62批第6项，续航更正不撤销或清空该原项电池质量/能量。采用整行最新记录冻结参数会把未更正字段误计为缺值；字段级继承可由公告前原文支持，须由主流程另做显式版本化实现和状态/暴露验证。',
                   base_parameter_file_sha256=hashlib.sha256(parameter_path.read_bytes()).hexdigest(),
                   base_enumeration_file_sha256=hashlib.sha256(enumeration_path.read_bytes()).hexdigest())
    summary['checks_passed'] = (not differences and model_multiset_equal and not narrative_issues and main_story_equal)
    savejson('verification_summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary['checks_passed']:
        raise SystemExit('Differences require review')

if __name__ == '__main__':
    main()
