#!/usr/bin/env python3
"""Apply an explicitly identified same-entry field correction, preserving raw data.

This is deliberately separate from configuration matching.  The original 64th
catalogue says exactly which item in the 62nd catalogue has its range corrected.
Only that item's uncorrected fields are retained in the effective observation.
No subsequent catalogue observation enters the announcement information set.
"""
from pathlib import Path
from decimal import Decimal
import argparse, collections, copy, csv, hashlib, json, shutil

MODEL = 'SGM6500BEBEV'
TARGET = 'old-62-Word97--0-7'
CORRECTION = 'old-text-correction-64-SGM6500BEBEV'
PARAM = '研究数据/参数版本_原值与计算代理.csv'
VIEW = '研究数据/参数版本_字段勘误生效视图.csv'
SNAP = '研究数据/重建样本_两截点参数与暴露.csv'
RISK = '研究数据/公告前风险集_连续处理强度输入.csv'
PANEL = '研究数据/车型月度面板_2022至2024.csv'
JOIN = '官方技术清单/重建3328_官方清单标记与资格轨迹.csv'
LAYER = '官方技术清单/五档数值层_逐型号归属与判据.csv'
OLD_LAYER = '官方技术清单/五档数值层_逐型号归属与判据2877行.csv'
GROUP = '官方技术清单/公告前风险集_官方标记与数值层对账.csv'
TRAJ = '研究数据/政策后资格轨迹与重申报标签.csv'
EXTRA = ['composition_kind', 'target_record_id', 'corrected_fields',
         'inherited_fields', 'field_source_record_ids_json',
         'field_source_sha256_json', 'field_observation_upper_bounds_json',
         'correction_scope_verified', 'original_field_parse_status_json', 'effective_values_scope']


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert len(reader.fieldnames) == len(set(reader.fieldnames))
    return reader.fieldnames, rows


def write(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def latest(rows, cutoff):
    possible = [r for r in rows if not r['public_date_lower_bound'] or r['public_date_lower_bound'] <= cutoff]
    certain = [r for r in possible if r['public_date_upper_bound'] <= cutoff]
    required_lower = max((r['public_date_lower_bound'] for r in certain), default='')
    return [r for r in possible if min(r['public_date_upper_bound'], cutoff) >= required_lower]


def parameter(rows, cutoff):
    candidates = latest(rows, cutoff)
    observed = bool(candidates) and all(r['public_date_upper_bound'] <= cutoff for r in candidates)
    result = {'ids': '|'.join(sorted(r['record_id'] for r in candidates)),
              'count': str(len(candidates)), 'all_observed': str(int(observed)),
              'lower': min((r['public_date_lower_bound'] or '0001-01-01' for r in candidates), default=''),
              'upper': max((r['public_date_upper_bound'] for r in candidates), default='')}
    for prefix in ['range', 'curb_mass', 'battery_mass', 'battery_energy', 'density_proxy']:
        points = {r[prefix + '_point'] for r in candidates}
        result[prefix + '_point'] = next(iter(points)) if observed and len(points) == 1 else ''
        for suffix, func in [('lower', min), ('upper', max)]:
            values = [r[prefix + '_' + suffix] for r in candidates]
            result[prefix + '_' + suffix] = str(func(Decimal(v) for v in values)) if values and all(values) else ''
    return result


def shortfall(value, threshold):
    return str(max(Decimal(0), (Decimal(threshold) - Decimal(value)) / Decimal(threshold))) if value else ''


def layer(ready, distance, density):
    if not ready:
        return '单值不足'
    r, d = Decimal(distance) < 200, Decimal(density) < 125
    if r and d:
        return '两项数值低于常规阈值'
    if r:
        return '续航单项低于常规阈值'
    if d:
        return '密度代理单项低于常规阈值'
    return '两项数值均达到常规阈值'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=Path(__file__).resolve().parents[2] / 'round4/data_v1_4')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--correction-original', type=Path, default=Path(__file__).resolve().parents[1] / 'originals/mf_batch64.doc')
    args = parser.parse_args()
    base, out = args.base.resolve(), args.output.resolve()
    data = out / 'data_v1_5'
    assert base != data and base not in data.parents and not data.exists(), 'Fresh output required; never mutate prior versions.'
    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(base, data)
    originals = {str(p.relative_to(base)): (p.read_bytes(), read(p)) for p in sorted(base.rglob('*.csv'))}
    pf, raw = originals[PARAM][1]
    byid = {r['record_id']: r for r in raw}
    assert len(raw) == len(byid) == 7203
    target, correction = byid[TARGET], byid[CORRECTION]
    assert target['model_key'] == correction['model_key'] == MODEL
    assert target['source_batch'] == '62' and correction['source_batch'] == '64'
    assert target['range_raw'] == '502' and correction['range_raw'] == '608'
    assert target['curb_mass_raw'] == '2620' and target['battery_mass_raw'] == '620' and target['battery_energy_raw'] == '95.7'
    assert target['public_date_upper_bound'] == '2023-02-20' and correction['public_date_upper_bound'] == '2023-04-17'
    assert sha(args.correction_original) == correction['source_sha256'] == 'c4e238989e7e40ec2c3a6a899ead170b4a745bc72546ba6fd4a5731d8890c6cb'
    assert all(not correction[p + '_raw'] for p in ['curb_mass', 'battery_mass', 'battery_energy'])
    effective = []
    for original in raw:
        row = dict(original)
        field_sources = {name: [original] for name in ['range', 'curb_mass', 'battery_mass', 'battery_energy', 'density_proxy']}
        row.update(composition_kind='original_observation', target_record_id='', corrected_fields='', inherited_fields='', correction_scope_verified='0',
                   effective_values_scope='原记录数值；不认证配置、完整技术资格或因果识别')
        if row['record_id'] == CORRECTION:
            for prefix in ['curb_mass', 'battery_mass', 'battery_energy']:
                for suffix in ['point', 'lower', 'upper', 'values_new', 'parse_status_new']:
                    row[prefix + '_' + suffix] = target[prefix + '_' + suffix]
                field_sources[prefix] = [target]
            for suffix, energy_suffix, mass_suffix in [('point', 'point', 'point'), ('lower', 'lower', 'upper'), ('upper', 'upper', 'lower')]:
                row['density_proxy_' + suffix] = str(Decimal(1000) * Decimal(row['battery_energy_' + energy_suffix]) / Decimal(row['battery_mass_' + mass_suffix]))
            field_sources['density_proxy'] = [target]
            row.update(composition_kind='explicit_same_entry_field_correction', target_record_id=TARGET, corrected_fields='range',
                       inherited_fields='curb_mass|battery_mass|battery_energy', correction_scope_verified='1',
                       effective_values_scope='第64批明指第62批纯电动乘用车第6项仅续航502更正为608；保留同一原条目未更正字段，原raw不变；不是跨配置匹配')
        row['field_source_record_ids_json'] = dump({key: [r['record_id'] for r in records] for key, records in field_sources.items()})
        row['field_source_sha256_json'] = dump({key: [r['source_sha256'] for r in records] for key, records in field_sources.items()})
        row['field_observation_upper_bounds_json'] = dump({key: [r['public_date_upper_bound'] for r in records] for key, records in field_sources.items()})
        row['original_field_parse_status_json'] = dump({prefix: original[prefix + '_parse_status_new'] for prefix in ['range', 'curb_mass', 'battery_mass', 'battery_energy']})
        effective.append(row)
    write(data / VIEW, pf + EXTRA, effective)
    effective_by_id = {row['record_id']: row for row in effective}
    changed_effective_columns = []
    for original in raw:
        updated = effective_by_id[original['record_id']]
        for col in pf:
            if original[col] != updated[col]:
                assert original['record_id'] == CORRECTION
                changed_effective_columns.append(col)
        for col in ['range_raw', 'curb_mass_raw', 'battery_mass_raw', 'battery_energy_raw', 'source_sha256', 'source_location', 'record_id',
                    'full_configuration_match_verified', 'entity_verified', 'low_temperature_evidence_obtained', 'same_cycle_comparability_verified']:
            assert original[col] == updated[col]
    allowed = {p + '_' + s for p in ['curb_mass','battery_mass','battery_energy'] for s in ['point','lower','upper','values_new','parse_status_new']}
    allowed |= {'density_proxy_' + s for s in ['point','lower','upper']}
    assert set(changed_effective_columns) == allowed
    model_params = collections.defaultdict(list)
    for row in effective:
        model_params[row['model_key']].append(row)
    # Generic point reconstruction verifies all previously unaffected models and
    # determines the corrected model; no frozen value is typed into output rows.
    sf, snapshots = copy.deepcopy(originals[SNAP][1])
    point_mismatches = []
    for row in snapshots:
        expected = parameter(model_params[row['model_key']], row['cutoff'])
        assert row['possible_latest_record_ids'] == expected['ids']
        assert row['all_possible_latest_observed_before_cutoff'] == expected['all_observed']
        for prefix in ['range', 'curb_mass', 'battery_mass', 'battery_energy', 'density_proxy']:
            actual, value = row[prefix + '_point'], expected[prefix + '_point']
            equal = actual == value == '' or bool(actual and value and Decimal(actual) == Decimal(value))
            if row['model_key'] != MODEL:
                if not equal:
                    point_mismatches.append({'model_key': row['model_key'], 'cutoff': row['cutoff'], 'field': prefix + '_point', 'actual': actual, 'expected': value})
            elif row['cutoff'] == '2023-12-10':
                for suffix in ['point', 'lower', 'upper']:
                    row[prefix + '_' + suffix] = expected[prefix + '_' + suffix]
        if row['model_key'] == MODEL and row['cutoff'] == '2023-12-10':
            row['point_scope'] = '全部可能最新记录数值一致；第64批仅续航更正，未更正字段来自其明指第62批同一条目；不证明跨期同配置'
            for prefix, threshold in [('range', '200'), ('density_proxy', '125')]:
                row[prefix + '_relative_shortfall'] = shortfall(row[prefix + '_point'], threshold)
                row[prefix + '_shortfall_lower'] = shortfall(row[prefix + '_upper'], threshold)
                row[prefix + '_shortfall_upper'] = shortfall(row[prefix + '_lower'], threshold)
            r, d = row['range_relative_shortfall'], row['density_proxy_relative_shortfall']
            row['two_parameter_point_available'] = str(int(bool(r and d)))
            row['joint_max_relative_shortfall'] = str(max(Decimal(r), Decimal(d))) if r and d else ''
            row['ordinary_two_parameter_screen'] = '两项数值达到常规阈值' if r == d == '0' else '至少一项数值低于常规阈值' if r and d else '单值不足'
    assert not point_mismatches, point_mismatches[:10]
    write(data / SNAP, sf, snapshots)
    snapmap = {(r['model_key'], r['cutoff']): r for r in snapshots}
    rf, risk = copy.deepcopy(originals[RISK][1])
    for row in risk:
        if row['model_key'] != MODEL:
            continue
        p = snapmap[(MODEL, '2023-12-10')]
        row['continuous_exposure_range'] = p['range_relative_shortfall']
        row['continuous_exposure_density_proxy'] = p['density_proxy_relative_shortfall']
        row['continuous_exposure_joint_max'] = p['joint_max_relative_shortfall']
        ready = row['membership_announcement_cohort'] == row['announcement_active_observed'] == p['two_parameter_point_available'] == '1'
        row['descriptive_continuous_did_input_ready'] = str(int(ready))
        row['exclusion_from_numeric_primary_reason'] = '' if ready else '两项单值暴露不足'
    write(data / RISK, rf, risk)
    riskmap = {r['model_key']: r for r in risk}
    mf, panel = copy.deepcopy(originals[PANEL][1])
    monthly_changed = []
    for row in panel:
        if row['model_key'] != MODEL:
            continue
        expected = parameter(model_params[MODEL], row['month_end'])
        assert row['parameter_possible_latest_ids'] == expected['ids'] and row['parameter_latest_upper'] == expected['upper']
        assert row['range_record_point'] == expected['range_point']
        if row['density_proxy_record_point'] != expected['density_proxy_point']:
            monthly_changed.append(row['month'])
        row['density_proxy_record_point'] = expected['density_proxy_point']
        rr = riskmap[MODEL]
        for dst, src in [('exposure_range_locked_preannouncement', 'continuous_exposure_range'),
                         ('exposure_density_proxy_locked_preannouncement', 'continuous_exposure_density_proxy'),
                         ('exposure_joint_max_locked_preannouncement', 'continuous_exposure_joint_max'),
                         ('descriptive_continuous_did_input_ready', 'descriptive_continuous_did_input_ready')]:
            row[dst] = rr[src]
    assert monthly_changed == [f'2023-{m:02}' for m in range(4, 12)]
    assert parameter(model_params[MODEL], '2023-02-28')['range_point'] == '502'
    assert parameter(model_params[MODEL], '2023-03-31')['range_point'] == '502'
    assert parameter(model_params[MODEL], '2023-04-30')['range_point'] == '608'
    write(data / PANEL, mf, panel)
    jf, joined = copy.deepcopy(originals[JOIN][1])
    for row in joined:
        if row['model_key'] == MODEL:
            rr = riskmap[MODEL]
            row['numeric_input_ready'] = rr['descriptive_continuous_did_input_ready']
            row['range_exposure_pre20231210'] = rr['continuous_exposure_range']
            row['density_proxy_exposure_pre20231210'] = rr['continuous_exposure_density_proxy']
    write(data / JOIN, jf, joined)
    lf, layers = copy.deepcopy(originals[LAYER][1])
    for row in layers:
        if row['model_key'] == MODEL:
            p = snapmap[(MODEL, '2023-12-10')]
            ready = riskmap[MODEL]['descriptive_continuous_did_input_ready'] == '1'
            row.update(numeric_input_ready=str(int(ready)), range_point_km=p['range_point'], density_proxy_point_Wh_per_kg=p['density_proxy_point'],
                       numeric_layer=layer(ready, p['range_point'], p['density_proxy_point']), insufficient_reason='' if ready else '两项单值暴露不足')
            row['raw_threshold_predicate'] = f"numeric_input_ready=1; range_point < 200: {int(Decimal(p['range_point']) < 200)}; density_proxy_point < 125: {int(Decimal(p['density_proxy_point']) < 125)}" if ready else 'numeric_input_ready != 1；保持未知，不以0替代缺值'
    write(data / LAYER, lf, layers)
    write(data / OLD_LAYER, lf, layers)
    gf, groups = copy.deepcopy(originals[GROUP][1])
    joinmap = {r['model_key']: r for r in joined}
    _, trajectories = originals[TRAJ][1]
    trajmap = {r['model_key']: r for r in trajectories}
    for row in groups:
        keys = {r['model_key'] for r in layers if r['numeric_layer'] == row['numeric_layer']}
        marked = {k for k in keys if joinmap[k]['official_nonconformance_list_presence_observed'] == '1'}
        withdrawn = {k for k in keys if trajmap[k]['post2024_withdrawal_observed'] == '1'}
        reapplied = {k for k in marked if trajmap[k]['reapplication_observed_by_2024_year_end'] == '1'}
        n, d = len(marked), len(keys)
        row.update(risk_models=str(d), official_marked=str(n), official_unmarked=str(d-n),
                   marked_fraction=format(Decimal(n)/Decimal(d), '.6f') if d else '', marked_fraction_numerator=str(n),
                   marked_fraction_denominator=str(d), marked_fraction_exact=f'{n}/{d}',
                   **{'2024_withdrawal_observed':str(len(withdrawn)), 'marked_and_withdrawal_observed':str(len(marked & withdrawn)), 'marked_and_reapplication_observed':str(len(reapplied))})
    write(data / GROUP, gf, groups)
    # Export exact cell-level changes. Copy all unchanged original files byte for
    # byte; assertions guard against accidental CSV formatting or science drift.
    diffs = []
    changed_tables = []
    for rel, (old_bytes, (fields, old_rows)) in originals.items():
        path = data / rel
        new_fields, new_rows = read(path)
        assert fields == new_fields and len(old_rows) == len(new_rows)
        table_diffs = []
        for i, (old, new) in enumerate(zip(old_rows, new_rows), 2):
            for col in fields:
                if old[col] != new[col]:
                    if rel != GROUP:
                        assert old.get('model_key') == new.get('model_key') == MODEL, (rel, col, old.get('model_key'))
                    table_diffs.append({'table': rel, 'csv_line_1based': i, 'model_key': new.get('model_key', ''),
                                        'time': new.get('cutoff', new.get('month', new.get('numeric_layer', ''))), 'field': col, 'before': old[col], 'after': new[col]})
        if not table_diffs:
            path.write_bytes(old_bytes)
            assert sha(path) == hashlib.sha256(old_bytes).hexdigest()
        else:
            changed_tables.append({'table':rel, 'changed_rows':len({r['csv_line_1based'] for r in table_diffs}), 'changed_cells':len(table_diffs),
                                   'before_sha256':hashlib.sha256(old_bytes).hexdigest(), 'after_sha256':sha(path)})
            diffs.extend(table_diffs)
    assert (data / PARAM).read_bytes() == (base / PARAM).read_bytes()
    assert set(r['table'] for r in changed_tables) == {SNAP, RISK, PANEL, JOIN, LAYER, OLD_LAYER, GROUP}
    counts = dict(collections.Counter(r['numeric_layer'] for r in layers))
    assert len(risk) == 3328 and len(panel) == 119808 and len(layers) == 2805
    assert sum(r['descriptive_continuous_did_input_ready'] == '1' for r in risk) == 2425
    assert counts['单值不足'] == 380 and counts['两项数值均达到常规阈值'] == 1822
    source_audit = []
    for field, dates in json.loads(next(r for r in effective if r['record_id'] == CORRECTION)['field_observation_upper_bounds_json']).items():
        assert all(date <= '2023-12-10' for date in dates)
        source_audit.append({'field':field,'source_observation_upper_bounds':dates,'all_observed_before_announcement_cutoff':True})
    result = {'version':'v1.5', 'source_original_sha256_verified':sha(args.correction_original),
              'raw_parameter_rows':len(raw), 'effective_parameter_rows':len(effective), 'raw_parameter_file_byte_unchanged':True,
              'corrected_record_id':CORRECTION, 'target_record_id':TARGET, 'corrected_fields':['range'], 'inherited_fields':['curb_mass','battery_mass','battery_energy'],
              'effective_view_original_columns_changed':changed_effective_columns, 'all_effective_view_original_raw_fields_and_identity_certification_flags_unchanged':True,
              'affected_model_key':MODEL, 'changed_tables':changed_tables, 'changed_cells':len(diffs),
              'monthly_current_density_changed':monthly_changed, 'announcement_risk_models':len(layers), 'numeric_ready_models':2425,
              'layer_counts':counts, 'qualification_states_changed':0, 'source_field_no_future_leakage':source_audit,
              'all_non_SGM_original_scientific_cells_unchanged':True, 'unaffected_parameter_points_recomputed_mismatches':len(point_mismatches),
              'configuration_identity_certified':0,'full_technical_qualification_certified':0,'causal_identification_certified':0,
              'remaining_companion_work':'Root updates 380 insufficiency companion, source registry, requirements, final validation and final manifest.'}
    write(out / 'effective_correction_cell_differences.csv', ['table','csv_line_1based','model_key','time','field','before','after'], diffs)
    (out / 'effective_correction_rebuild_summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    shutil.copyfile(base / 'README.md', data / 'README_版本v1_4.md')
    (data / 'README.md').write_text('''# 数据 v1.5：原件补齐及特定字段勘误生效视图

科学参数的主读取入口改为 `研究数据/参数版本_字段勘误生效视图.csv`，共7203行；`研究数据/参数版本_原值与计算代理.csv`仍完整保留v1.4原始字节与原raw字段，供取证和历史复现。

第64批目录原件明确：第62批纯电动乘用车第6项SGM6500BEBEV的续航应为608km。生效视图仅把第64批这条更正记录未更正的整备质量、电池质量与总能量保留为其明指第62批同一原条目数值；并据此计算密度代理。两个文件、两条原记录和逐字段公开观察日均保留在来源图中。这是针对明确原条目的字段更正，不构成跨配置身份认证。原raw仍空白的继承字段须结合`composition_kind`、`inherited_fields`、`original_field_parse_status_json`解释；生效解析值不声称这些空白原格含数字。

续航608只从第64批公开观察日2023-04-17起进入当期参数，不回溯到2023年2月、3月。公告前冻结截点2023-12-10使用更正记录与其被更正原条目，未使用2023-12-26减免目录的新记录补齐。

本轮原件明确更正使1型号公告前单值可用：3328型号、在册风险集2805保持不变；冻结单值可用2425、单值不足380；两项均达到常规阈值1822。SGM6500BEBEV公告前密度代理为154.3548387096774193548387097Wh/kg，两项短缺暴露均为0。月度面板该型号36个月的冻结暴露/ready同步；2023年4—11月8条当期密度同步。资格事件6801、逐原件连接6873、三截点状态和所有型号的在册/撤销状态保持原文件字节。2024撤销观察仍503（风险集496、风险集外7）。

配置身份、完整技术条件、低温适用性及因果识别的认证标记仍为0。目录密度是1000×电池总能量/总质量的计算代理，不能替代推荐目录声明值。名称伴随更正、区间旁表和其他边界继承v1.4；最终原件登记与380不足原因旁表由round5配套核查更新。文件名中的2877等旧计数属于历史名称，使用无旧计数的规范别名及本README口径。`README_版本v1_4.md`和`README_版本v1_3.md`是历史版本记录，不作为v1.5当前结论。
''', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
