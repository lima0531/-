#!/usr/bin/env python3
"""Strict full-string parsing and conservative screens; never rewrite core points."""
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter
from decimal import Decimal as D
from pathlib import Path

OUT = Path(__file__).resolve().parent
R4 = OUT.parent
SOURCE = R4 / 'data_v1_4/推荐参数/推荐参数_配置版本长表.csv'
FIELDS = ['max_speed_30min_kmh', 'range_km', 'density_whkg', 'curb_mass_kg', 'consumption_kwh100km']
PATTERN = re.compile(r'(?P<number>\d+(?:\.\d+)?)(?:\((?P<annotation>CLTC|NEDC|CLTC工况|NEDC工况|CLTC工况,缩短法|NEDC工况,缩短法)\))?')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def parse(raw):
    """Only numbers separated outside recognised test-cycle parentheses are allowed."""
    s = re.sub(r'\s+', '', unicodedata.normalize('NFKC', raw))
    pieces, start, depth = [], 0, 0
    for i, c in enumerate(s):
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth < 0:
                raise ValueError('unbalanced parenthesis: '+raw)
        elif c in '/,;' and depth == 0:
            pieces.append(s[start:i]); start = i+1
    if depth:
        raise ValueError('unbalanced parenthesis: '+raw)
    pieces.append(s[start:])
    matches = [PATTERN.fullmatch(p) for p in pieces]
    if not all(matches):
        raise ValueError('unrecognised full-string content: '+raw)
    vals = [D(m.group('number')) for m in matches]
    annotations = [m.group('annotation') or '' for m in matches]
    return vals, annotations, s


def target(m):
    if m <= 1000:
        return D('.0112')*m+D('.4')
    if m <= 1600:
        return D('.0078')*m+D('3.8')
    return D('.0048')*m+D('8.60')


def ge_screen(vals, threshold):
    if min(vals) >= threshold:
        return '全部达到常规门槛'
    if max(vals) < threshold:
        return '全部低于常规门槛'
    return '外包络跨越常规门槛'


def write(name, rows, columns=None):
    with (OUT/name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns or list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    source_before = sha(SOURCE)
    with SOURCE.open(encoding='utf-8-sig', newline='') as f:
        allrows = list(csv.DictReader(f))
    selected = [x for x in allrows if x['four_requirement_numeric_inputs_complete'] != '1']
    assert len(selected) == 29 and len({x['model_key'] for x in selected}) == 18
    output, evidence, pending = [], [], []
    for r in selected:
        parsed = {}
        for field in FIELDS:
            raw = r[field+'_raw']
            vals, labels, normalised = parse(raw)
            parsed[field] = vals
            evidence.append({'observation_version_key': r['observation_version_key'], 'model_key': r['model_key'], 'config_id': r['config_id'], 'source_id': r['source_id'], 'source_sha256': r['source_sha256'], 'source_location': r[field+'_source_location'], 'field': field, 'raw': raw, 'nfkc_whitespace_removed': normalised, 'numbers': json.dumps([str(x) for x in vals]), 'annotations': json.dumps(labels, ensure_ascii=False), 'min': str(min(vals)), 'max': str(max(vals)), 'parse_method': 'full_string_grammar_only_no_annotation_digit_harvest', 'original_single_field': r[field+'_single'], 'original_single_field_updated': '0'})
        thresholds = [target(x) for x in parsed['curb_mass_kg']]
        min_y, max_y = min(thresholds), max(thresholds)
        energy_low, energy_high = min(parsed['consumption_kwh100km']), max(parsed['consumption_kwh100km'])
        energy = '所有选项均达到常规能耗门槛' if energy_high <= min_y else '所有选项均超过常规能耗门槛' if energy_low > max_y else '外包络跨越常规能耗门槛'
        screens = {k: ge_screen(parsed[k], D(t)) for k, t in [('max_speed_30min_kmh', '100'), ('range_km', '200'), ('density_whkg', '125')]}
        failed = [k for k, v in screens.items() if v == '全部低于常规门槛']
        crossed = [k for k, v in screens.items() if v == '外包络跨越常规门槛']
        if energy == '所有选项均超过常规能耗门槛':
            failed.append('consumption_kwh100km')
        if energy == '外包络跨越常规能耗门槛':
            crossed += ['consumption_kwh100km', 'curb_mass_kg']
        status = '至少一项在全部外包络不满足常规门槛' if failed else '四项声明值在全部外包络满足常规门槛' if not crossed else '外包络仍跨越门槛，需配置配对证据'
        result = {'observation_version_key': r['observation_version_key'], 'source_id': r['source_id'], 'source_sha256': r['source_sha256'], 'source_public_date': r['source_public_date'], 'model_key': r['model_key'], 'config_id': r['config_id'], 'firm_raw': r['firm_raw']}
        for field in FIELDS:
            result.update({field+'_raw': r[field+'_raw'], field+'_lower': str(min(parsed[field])), field+'_upper': str(max(parsed[field]))})
        result.update({'consumption_target_lower': str(min_y), 'consumption_target_upper': str(max_y), 'speed_screen': screens['max_speed_30min_kmh'], 'range_screen': screens['range_km'], 'density_screen': screens['density_whkg'], 'energy_screen': energy, 'four_requirement_interval_screen': status, 'all_failed_fields': ';'.join(failed), 'crossed_fields': ';'.join(crossed), 'need_new_original_numeric_values_for_envelope': '0' if not crossed else '仅跨越字段的具体配置配对证据', 'original_single_fields_updated': '0', 'full_configuration_match_verified': '0', 'policy_compliance_certified': '0', 'scope': '公开推荐声明值四条件保守外包络；不配对选项；未认证减免同配置或低温例外'})
        output.append(result)
        if crossed:
            pending.append({'observation_version_key': r['observation_version_key'], 'model_key': r['model_key'], 'config_id': r['config_id'], 'crossed_fields': ';'.join(crossed), 'needed_material': '匹配本推荐配置版本与减免申报配置的报告/申报页及字段配对关系', 'received_file': '', 'received_sha256': ''})
    write('29配置版本_四技术条件保守外包络核查.csv', output)
    write('145原字段_完整字符串解析与单元格证据.csv', evidence)
    write('仍跨门槛_具体配置字段待补.csv', pending, ['observation_version_key', 'model_key', 'config_id', 'crossed_fields', 'needed_material', 'received_file', 'received_sha256'])
    assert len(evidence) == 145 and all(x['min'] != '' for x in evidence)
    assert sha(SOURCE) == source_before
    # Boundary and anti-number-harvesting checks substantiate the parser and policy formula.
    assert target(D(1000)) == D('11.6000') and target(D(1600)) == D('16.2800')
    assert parse('505（CLTC工况，缩短法）')[0] == [D(505)]
    assert parse('530(CLTC); 490(NEDC)')[0] == [D(530), D(490)]
    assert parse('1610,1660')[0] == [D(1610), D(1660)]
    try:
        parse('505(2021标准)')
    except ValueError:
        pass
    else:
        raise AssertionError('annotation digits accidentally accepted')
    boundary = next(x for x in output if x['config_id'] == 'NC573180')
    assert boundary['consumption_kwh100km_upper'] == '21.2' and D(boundary['consumption_target_lower']) == D('21.2000')
    assert boundary['energy_screen'] == '所有选项均达到常规能耗门槛'
    summary = {'source': str(SOURCE), 'source_sha256': source_before, 'source_raw_fields_previously_verified': 'round3/technical/recommendation_original_verification.json; 3701 location-based original field comparisons', 'selected_versions': 29, 'selected_models': 18, 'full_string_fields_parsed': 145, 'results': dict(Counter(x['four_requirement_interval_screen'] for x in output)), 'crossing_versions_needing_numeric_pairing': len(pending), 'core_source_changed': False, 'new_report_or_vehicle_observations_added': 0, 'single_points_imputed': 0, 'configuration_or_legal_certification_added': 0, 'validation': 'full-string parsing, conservative envelope, policy segment boundaries, 21.2 exact energy equality, source hash unchanged all passed'}
    (OUT/'validation_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write('文件_SHA256.csv', [{'file': p.name, 'bytes': str(p.stat().st_size), 'sha256': sha(p)} for p in sorted(OUT.iterdir()) if p.is_file() and p.name != '文件_SHA256.csv'])
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
