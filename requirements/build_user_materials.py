#!/usr/bin/env python3
"""Produce source-linked collection requests without changing v1_3 scientific data."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
AUDIT = OUT.parents[1]
R3 = AUDIT / 'round3'
BASE = AUDIT / 'round4/data_v1_4'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(name: str, rows: list[dict[str, str]], fields=None) -> None:
    fields = fields or list(rows[0])
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    OUT.mkdir(exist_ok=True, parents=True)
    risk_source = BASE / '研究数据/公告前风险集_连续处理强度输入.csv'
    param_source = BASE / '研究数据/参数版本_原值与计算代理.csv'
    risk = read(risk_source)
    params = {x['record_id']: x for x in read(param_source)}
    assert len(risk) == 3328
    ready = [x for x in risk if x['descriptive_continuous_did_input_ready'] == '1']
    unmarked = [x for x in ready if not x['range_cycle_explicit']]
    assert len(ready) == 2424 and len(unmarked) == 2207
    assert len({x['model_key'] for x in unmarked}) == 2207
    assert sum(x['range_cycle_explicit'] == 'CLTC' for x in ready) == 217

    copied = [
        (R3 / 'requirements/285推荐配置_所需身份与检测材料清单.csv', '285配置版本_跨目录身份材料待补清单.csv'),
        (R3 / 'technical/再申报92型号_逐车材料字段待补清单.csv', '92再申报型号_逐车材料待补清单.csv'),
        (R3 / 'technical/低温报告优先核查_19配置版本.csv', '19配置版本_低温报告优先待补清单.csv'),
        (AUDIT / 'round4/public_gaps/历史两份原件_精确提取清单.csv', '2份历史原件_嵌套归档精确路径.csv'),
    ]
    provenance = []
    for src, dest in copied:
        shutil.copyfile(src, OUT / dest)
        assert sha(src) == sha(OUT / dest)
        provenance.append({'artifact': dest, 'source': str(src.relative_to(AUDIT)), 'source_sha256': sha(src), 'method': 'byte_copy_no_new_test_or_vehicle_data'})
    configs = read(OUT / copied[0][1])
    lowtemp = read(OUT / copied[2][1])
    vehicles = read(OUT / copied[1][1])
    assert (len(configs), len({x['config_id'] for x in configs}), len({x['model_key'] for x in configs})) == (285, 278, 170)
    assert len(lowtemp) == 19 and len({x['model_key'] for x in lowtemp}) == 12
    assert len(vehicles) == 92 and len({x['model_key'] for x in vehicles}) == 92

    cycle_rows = []
    for r in sorted(unmarked, key=lambda x: x['model_key']):
        ids = [x.strip() for x in r['exposure_record_ids'].split(';') if x.strip()]
        observations = [params[x] for x in ids]
        assert all(x['model_key'] == r['model_key'] for x in observations)
        cycle_rows.append({
            'model_key': r['model_key'],
            'freeze_cutoff': '2023-12-10',
            'numeric_ready_v1_3': '1',
            'range_cycle_label_in_frozen_source': '',
            'exposure_record_ids': r['exposure_record_ids'],
            'source_batches': ';'.join(x['source_batch'] for x in observations),
            'source_files': ';'.join(x['source_file'] for x in observations),
            'source_sha256s': ';'.join(x['source_sha256'] for x in observations),
            'source_locations': json.dumps([x['source_location'] for x in observations], ensure_ascii=False),
            'frozen_range_raw': ';'.join(x['range_raw'] for x in observations),
            'observed_date_upper': r['exposure_max_observation_upper'],
            'needed_materials': '对应公告前同配置的原始试验报告；报告编号/日期/版本；采用标准与工况；试验配置与目录记录对应证据',
            'holder_or_channel': '整车申报企业技术/认证部门、原检测机构、授权产品公告/申报档案',
            'use_condition': '仅在开展同工况可比暴露或解释续航门槛时补；不阻塞目录事件状态分析',
            'report_id_received': '',
            'test_standard_and_revision_received': '',
            'test_cycle_received': '',
            'test_configuration_key_received': '',
            'material_file_received': '',
            'material_sha256_received': '',
            'can_use_later_catalogue_to_backfill': '0',
            'same_cycle_comparability_verified': '0',
        })
    write('2207数值可用型号_公告前试验工况待核清单.csv', cycle_rows)
    provenance.append({'artifact': '2207数值可用型号_公告前试验工况待核清单.csv', 'source': str(risk_source.relative_to(AUDIT)), 'source_sha256': sha(risk_source), 'additional_source': str(param_source.relative_to(AUDIT)), 'additional_source_sha256': sha(param_source), 'method': 'filter_ready_1_and_cycle_blank_then_join_exact_record_id'})

    archive = [
        {'file_name': 'mf_batch01.pdf', 'expected_bytes': '442883', 'expected_sha256': 'eac13628c37f01c4da157a2d1916d97acc81fdc295f18e1783549075ce7e5aa7', 'historical_source': '免征目录第1批', 'preferred_action': '从已经上传的40MB完整归档解压提取此文件，单独上传', 'reason': '完整归档下载工具单文件上限32MiB；当前未取得这份历史原件以做全表独立核查', 'do_not_require': '无需重搜全网或重传整个大包；若不同版本请保留实际字节与来源，不强填目标SHA', 'received_path': '', 'received_sha256': ''},
        {'file_name': 'mf_batch64.doc', 'expected_bytes': '597504', 'expected_sha256': 'c4e238989e7e40ec2c3a6a899ead170b4a745bc72546ba6fd4a5731d8890c6cb', 'historical_source': '免征目录第64批，含SGM6500BEBEV续航文字勘误', 'preferred_action': '从已经上传的40MB完整归档解压提取此文件，单独上传', 'reason': '公开附件当前不可取得；须核对完整目录和部分勘误语义、是否可承接前版同配置电池参数', 'do_not_require': '无需补找第26批两份原件；其精确历史字节已公开回收', 'received_path': '', 'received_sha256': ''},
    ]
    write('仅剩2份历史原件_从现有归档提取清单.csv', archive)
    fields = []
    for model, rid, field, unit, status, request, nuance in [
        ('JX6550T-M5BEV', 'old-48-Word97--0-20', 'battery_energy_raw', 'kWh', '公告前48批原表对应电池总能量字段空', '该48批申报配置对应的总能量原始申报页/检测报告或2023-12-10以前已存在的官方更正', '2023-12-26减免目录出现65.17kWh；发布时间在冻结点后，不能直接回填'),
        ('SGM6500BEBEV', 'old-text-correction-64-SGM6500BEBEV', 'battery_mass_raw;battery_energy_raw', 'kg;kWh', 'latest仅续航文字勘误记录未携带电池字段，须先判断勘误承接范围', '先提供64批原件完整表及勘误文字；确认是否仅改续航、与62批为同配置后才能决定是否承接620kg/95.7kWh；如仍无法判定再补同配置原始申报/检测材料', '62批已有620kg/95.7kWh；不能把部分勘误的空字段误称为整车型未知，也不能未经同配置/勘误语义核实就自动承接'),
    ]:
        p = params[rid]
        fields.append({'model_key': model, 'record_id': rid, 'source_batch': p['source_batch'], 'source_file': p['source_file'], 'source_sha256': p['source_sha256'], 'source_location': p['source_location'], 'public_date_upper': p['public_date_upper_bound'], 'affected_fields': field, 'units': unit, 'current_gap_status': status, 'precise_request': request, 'holder_or_channel': '先查既有档案/主管部门原表；仍缺时找整车申报企业技术/认证部门或检测机构', 'version_boundary': nuance, 'request_unique_point_for_tolerance_or_multivalue': '0', 'material_file_received': '', 'material_sha256_received': ''})
    write('2型号_公告前科学字段与勘误待核清单.csv', fields)

    technical_materials = [
        ('车辆法定类别（含M1，如结论需要）', '具体产品/配置', '产品公告、出厂合格证或认证证书中的类别字段、适用标准、型号及配置版本、有效期间、来源与指纹', '用于认定法定类别时需要；来源乘用车小节仅定义研究队列，不能代替独立M1证明'),
        ('30分钟最高车速', '配置与报告版本', '对应配置30分钟最高车速报告/申报值、单位、试验标准与版本、机构、日期、编号和来源', '完整技术资格认定时核对；不能用最高车速替代30分钟最高车速'),
        ('续驶里程', '配置与报告版本', '对应配置续驶里程、工况、标准版本、报告编号/日期/机构、配置证据、原单位与来源', '完整技术资格或同工况比较时核对；政策后报告不能自动回填公告前暴露'),
        ('电池系统质量能量密度', '电池系统配置与申报/检测版本', '申报系统密度及质量/能量测量定义、总能量和总质量、系统部件身份、报告及标准版本、日期来源', '完整技术资格认定时核对；目录1000×能量/质量代理不能直接冒充推荐声明密度'),
        ('百公里能耗及整备质量', '同一车辆配置与试验版本', '对应配置能耗、工况、整备质量及各质量选项含义、测量/申报报告、标准版本、机构/日期/编号', '完整技术资格认定时核对同配置能耗Y(m)；多值不能任意配对'),
    ]
    write('配置技术资格与M1_所需证明字段规范.csv', [dict(zip(['evidence_item', 'grain', 'required_fields', 'use_boundary'], x)) | {'received_material': '', 'received_material_sha256': '', 'certification_added': '0'} for x in technical_materials])

    interval_source = AUDIT / 'round4/parameters/381单值不足_原因与保守区间核查.csv'
    interval_rows = read(interval_source)
    assert len(interval_rows) == 381
    crossing = [r for r in interval_rows if '区间跨越阈值' in (r['range_interval_screen'], r['density_interval_screen'])]
    priority_crossing = [r for r in crossing if r['two_parameter_interval_screen'] == '区间跨越阈值，具体配置仍待匹配']
    secondary_crossing = [r for r in crossing if r['two_parameter_interval_screen'] == '至少一项数值在整个外包络低于常规阈值']
    assert (len(crossing), len(priority_crossing), len(secondary_crossing)) == (36, 32, 4)
    for name, rows, purpose in [
        ('32型号_区间跨阈值优先配置材料清单.csv', priority_crossing, '要确定两项数值是否同时达到常规阈值，优先补具体配置及电池能量/质量对应证据'),
        ('4型号_单项跨阈值补充清单.csv', secondary_crossing, '已有另一项在整个外包络低于阈值；仅在要细分单项数值层时补，不阻塞联合门槛低于判定'),
    ]:
        augmented = []
        for r in sorted(rows, key=lambda x: x['model_key']):
            augmented.append({**r, 'needed_materials': '公告前该申报记录的具体配置版本、各斜线选项/公差的定义、电池质量和总能量的对应关系、企业申报页或检测报告、来源与版本日期', 'collection_purpose': purpose, 'holder_or_channel': '整车申报企业技术/认证部门、原检测机构、授权申报档案', 'received_file': '', 'received_sha256': ''})
        write(name, augmented)
        provenance.append({'artifact': name, 'source': str(interval_source.relative_to(AUDIT)), 'source_sha256': sha(interval_source), 'method': 'filter_conservative_interval_crossing_no_point_value_created'})

    tasks = [
        ('P0', '2份历史原件', '2文件', 'mf_batch01.pdf；mf_batch64.doc', '完成缺失原件全表审计并解释64批勘误', '已有40MB完整归档的持有人', '仅剩2份历史原件_从现有归档提取清单.csv', '优先从现有归档提取即可；第26批两份无需再找'),
        ('P1', '公告前数值/勘误证据', '2型号，2类任务', 'JX6550T-M5BEV总能量；SGM6500BEBEV勘误范围及电池参数承接', '进一步处理冻结暴露单值不足中的实际空字段/部分勘误', '申报企业或检测机构；SGM先查64批原件', '2型号_公告前科学字段与勘误待核清单.csv', '不以政策后值回填；公差/多值另做区间筛查，无需381型号各找一个确定值'),
        ('P1条件配置判定', '区间跨阈值的具体配置', '32型号优先；另4仅单项细分', '公告前对应配置版本、斜线选项/公差含义、电池能量与质量对应证据', '要进一步确定两项门槛或细分单项结果时补', '申报企业技术/认证部门、检测机构', '32型号_区间跨阈值优先配置材料清单.csv；4型号_单项跨阈值补充清单.csv', '381单值不足中300联合达到、47联合至少一项必低已可区间判断；32仍跨阈值，2待原字段/勘误证据'),
        ('P2', '跨目录配置身份', '285版本/278配置ID/170型号', '减免申报配置版本↔推荐配置ID桥、电池/电机部件、有效时间、可核查来源', '仅在把推荐技术参数连接至减免配置并判断配置资格时需要', '整车申报企业认证部门、授权申报系统', '285配置版本_跨目录身份材料待补清单.csv', '这285不是全3328型号；同型号不能认证同配置'),
        ('P2条件法律/完整技术认定', '法定类别及同配置四条件证明', '具体配置；独立类别认证范围视目标而定', '类别/M1证明；对应配置30分钟车速、续航、系统密度、能耗与整备质量的申报或检测证据及标准/报告版本', '仅在认定法定类别和完整技术资格时需要', '企业认证部门、产品合格证或公告/认证系统、检测机构', '配置技术资格与M1_所需证明字段规范.csv', '公开推荐数字已取得且外包络可核不表示同配置或法律资格已认证'),
        ('P2优先', '低温例外报告', '19版本/12型号优先', '匹配配置的GB/T18386.1-2021附录A报告、机构/日期/编号、常温低温里程、衰减率、配置桥', '仅在适用低温例外或解释未达常规门槛却可能符合例外时需要', '申报企业、原检测机构', '19配置版本_低温报告优先待补清单.csv', '这19只是条件数值筛查候选，不是已证明符合低温例外；无需为全部285版本机械索取低温报告'),
        ('P2', '92再申报型号逐车证据', '92型号；车辆数未知', '稳定车辆匿名键、具体配置/整改版本、制造日期、开票日期、对应重新列入事件、校验后减免税标识', '仅在回答具体车辆是否享受减免税时需要', '车辆合格证/电子信息、销售发票、授权税务或企业业务系统', '92再申报型号_逐车材料待补清单.csv', '清单92行是型号需求范围，不是92辆；目录/月末状态不能代替逐车日期'),
        ('条件任务', '续航试验口径', '2207数值可用但未标工况型号', '公告前同配置原报告的标准版本、工况、报告版本和日期、配置身份', '需要同工况可比暴露/阈值解释时补；当前目录状态分析可继续', '申报企业、检测机构、授权产品档案', '2207数值可用型号_公告前试验工况待核清单.csv', '2424数值可用中217已明确CLTC，2207未标；有CLTC标签也尚非完整同工况认证'),
        ('可选公开补证', '首批发布日期和标准登记', '首批1项；标准登记其余字段', '主管部门首批真实公开日期；GB/T18386.1-2021发布日、当前状态、替代关系登记证据', '原始日期登记/标准完整档案审计；不阻塞2023–24目录科学分析', '工信部原公告档案、国家标准登记平台；有正常浏览器访问时保存原页及URL', '参见../public_gaps/standard/标准登记_待人工补字段.csv及本轮公开来源续查记录', '标准正式实施日2021-10-01已补；这些是当前公开访问未取得，不是非公开实测数据'),
        ('仅市场政策效应研究', '真实结果与观察分母', '型号/配置×月份；实际范围待研究目标确定', '销量/生产/注册登记/成交价所研究结果、覆盖分母、0与未覆盖区别、时间范围、配置型号桥和来源', '只在研究销量、停产、市场退出或价格效应时必要', '企业业务系统、行业统计或有授权数据供应商', '需要用户亲自提供的数据.md', '现有2022–2024目录状态面板不含上述结果；未做该研究时无需扩采'),
    ]
    write('需要用户亲自提供_按用途与优先级.csv', [dict(zip(['priority', 'material', 'scope', 'required_fields', 'needed_when', 'holder_or_channel', 'row_checklist', 'boundary'], row)) for row in tasks])
    write('输入来源与SHA256.csv', provenance, sorted({k for r in provenance for k in r}))
    rec_interval_source = AUDIT / 'round4/recommendation_interval/validation_summary.json'
    rec_interval = json.loads(rec_interval_source.read_text(encoding='utf-8'))
    provenance.append({'artifact': '需要用户亲自提供的数据.md（29推荐配置旁表说明）', 'source': str(rec_interval_source.relative_to(AUDIT)), 'source_sha256': sha(rec_interval_source), 'method': 'reported_29_full_string_interval_screens_no_numeric_backfill'})
    write('输入来源与SHA256.csv', provenance, sorted({k for r in provenance for k in r}))
    summary = {'base_scientific_version': 'v1_4', 'generated_utc': datetime.now(timezone.utc).isoformat(), 'new_test_observations_added': 0, 'new_vehicle_observations_added': 0, 'base_cohort': 3328, 'risk_active': 2805, 'numeric_ready': 2424, 'numeric_ready_cycle_blank': 2207, 'numeric_ready_explicit_cltc': 217, 'recommendation_versions': 285, 'recommendation_config_ids': 278, 'recommendation_models': 170, 'low_temperature_priority_versions': 19, 'low_temperature_priority_models': 12, 'reapplication_models': 92, 'remaining_historical_files': 2, 'raw_empty_or_partial_correction_models': 2, 'interval_crossing_priority_models': 32, 'interval_crossing_additional_single_condition_models': 4, 'recommendation_29_interval': rec_interval['results'], 'recommendation_29_needing_new_raw_numeric_values': 0, 'scientific_core_changed': False, 'material_list_is_collected_data': False, 'validation': 'all assertions passed; input lists copied byte-for-byte; 2207 exact record links resolved; 32+4 conservative crossing models derived; recommendation 29 interval summary source linked'}
    (OUT / 'requirements_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    manifest = []
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name != '文件_SHA256.csv':
            manifest.append({'file': p.name, 'bytes': str(p.stat().st_size), 'sha256': sha(p)})
    write('文件_SHA256.csv', manifest)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
