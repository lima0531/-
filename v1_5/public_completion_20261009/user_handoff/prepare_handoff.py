#!/usr/bin/env python3
"""Freeze bounded public results and assemble local inquiry packets; no HTTP or messages."""
import csv
import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
AUDIT = OUT.parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(name, rows, columns=None):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns or list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def js_text(p):
    return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m[1], 16)), p.read_text())


def body_text(p):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', p.read_text())))


def main():
    input_paths = []
    sibling_paths = {
        'JX': AUDIT / 'round9/public_jx_extended/jx_extended_summary.json',
        'configuration': AUDIT / 'round9/public_configuration/public_configuration_summary.json',
        'lowtemp': AUDIT / 'round9/public_lowtemp/public_lowtemp_summary.json',
        'cycle': AUDIT / 'round9/public_cycle/public_cycle_summary.json',
    }
    siblings = {k: json.loads(p.read_text()) for k, p in sibling_paths.items()}
    input_paths += list(sibling_paths.values())
    assert siblings['JX']['new_energy_field_closed'] == 0
    assert siblings['configuration']['new_closures']['cross_tax_recommendation_identity_versions'] == 0
    assert siblings['configuration']['remaining']['joint_crossing_models'] == 32
    assert siblings['configuration']['remaining']['single_crossing_models'] == 4
    assert siblings['lowtemp']['newly_obtained_matching_full_reports'] == 0
    assert siblings['lowtemp']['remaining_configuration_versions'] == 19
    assert siblings['cycle']['backlog_models_after'] == 2208
    assert siblings['cycle']['source_files_fully_scanned'] == 71
    assert siblings['cycle']['new_explicit_cycle_labels_obtained'] == 0

    grouping = json.loads((OUT / 'enterprise_grouping_summary.json').read_text())
    enterprises = read(OUT / '企业合并_询证总表.csv')
    tasks = read(OUT / '原始询证任务_逐用途来源与企业路由.csv')
    versions = read(OUT / '企业合并_285配置版本_身份与低温一次询证.csv')
    models = read(OUT / '企业合并_车型材料用途与来源.csv')
    before = {AUDIT / r['file']: r['sha256'] for r in read(OUT / '输入文件_SHA256.csv')}
    assert all(sha(p) == fp for p, fp in before.items())
    input_paths += list(before)
    overlap_path = AUDIT / 'round8/final_gap_status/计数与交叉核查.json'
    overlap = json.loads(overlap_path.read_text())
    input_paths.append(overlap_path)
    assert overlap['joint_and_single_crossing_intersection'] == 0
    assert overlap['joint_and_single_crossing_union'] == 36
    assert overlap['lowtemp_versions_subset_of_identity_versions']

    def contact(firm, url='', entry='', phone='', mail='', source='', receipt='', quote='',
                entity='', status='已核官网入口', boundary='', attempted=''):
        p = AUDIT / source if source else None
        rp = AUDIT / receipt if receipt else None
        if p:
            assert p.is_file()
            input_paths.append(p)
        if rp:
            assert rp.is_file()
            input_paths.append(rp)
        rc = json.loads(rp.read_text()) if rp else {}
        relevant = [t for t in tasks if t['firm_routing_name'] == firm]
        low = [v for v in versions if v['firm_routing_name'] == firm and v['low_temperature_report_priority'] == '1']
        return {
            'firm_as_historical_source': firm,
            'priority': 'P1核心原空字段' if firm == '江铃汽车股份有限公司' else 'P3低温例外条件任务',
            'target_models': ';'.join(sorted({t['model_key'] for t in relevant if t['purpose_scope'] in ['JX原空能量', '19低温优先']})),
            'lowtemp_version_rows': len(low),
            'lowtemp_config_ids': ';'.join(sorted({v['recommendation_config_id'] for v in low})),
            'verified_homepage_url': url, 'verified_service_or_contact_entry': entry,
            'general_public_phone': phone, 'general_public_email': mail,
            'technical_or_certification_department_direct_contact_verified': '0',
            'current_site_entity_or_brand_observed': entity,
            'route_status': status, 'holder_route': '请客服/官网转产品技术、认证/准入或历史申报材料保管部门；由企业确认原检测机构',
            'current_contact_is_historical_holder_certified': '0', 'route_boundary': boundary,
            'attempted_unverified_url': attempted,
            'source_file': source, 'source_sha256': sha(p) if p else '',
            'receipt_file': receipt, 'receipt_sha256': sha(rp) if rp else '',
            'retrieved_utc': rc.get('retrieved_utc', ''), 'http_or_fetch_status': rc.get('http_status', rc.get('status', '未核实入口')),
            'literal_evidence_excerpt': quote, 'messages_or_forms_sent': '0',
        }

    jmc = AUDIT / 'round8/jx_public_final_pass/raw/jmc_common.js'
    baw = OUT / 'contact_sources/baw_contact.txt'
    sgmw = OUT / 'contact_sources/sgmw_after_sale.txt'
    jmev = OUT / 'contact_sources/jmev_about.txt'
    assert '400-880-1099' in js_text(jmc) and 'mailto:smc@jmc.com.cn' in js_text(jmc)
    assert '400-990-1951' in body_text(baw) and '北京汽车制造厂（青岛）有限公司' in body_text(baw)
    assert '4008895050' in body_text(sgmw) and '4008612345' in body_text(sgmw)
    assert '400-1799-909' in body_text(jmev) and '江西江铃集团新能源汽车有限公司' in body_text(jmev)
    contacts = [
        contact('江铃汽车股份有限公司', 'https://www.jmc.com.cn/', 'https://www.jmc.com.cn/services.html',
                '400-880-1099', 'smc@jmc.com.cn', 'round8/jx_public_final_pass/raw/jmc_common.js',
                'round8/jx_public_final_pass/raw/jmc_common.js.receipt.json',
                '商：400-880-1099；mailto:smc@jmc.com.cn（官网公共前端原样字符串，未执行JS）',
                '江铃汽车官网商系公共入口', boundary='商系一般联系入口用于转部门；不认证目标车型为法律上的商用车/M1，亦不是技术认证部门专线。与江西江铃集团新能源企业分开。'),
        contact('北京汽车制造厂有限公司', 'https://www.baw.com.cn/', 'https://www.baw.com.cn/contact_us.html',
                '400-990-1951', 'bawzs@baw.com.cn', 'round9/user_handoff/contact_sources/baw_contact.txt',
                'round9/user_handoff/contact_sources/baw_contact.receipt.json',
                '北京汽车制造厂（青岛）有限公司；服务热线：400-990-1951（24小时）；邮箱：bawzs@baw.com.cn（国内）',
                '北京汽车制造厂（青岛）有限公司', boundary='当前官网联系主体与历史原文企业名不同，仅作品牌关联转接。请其确认历史材料保管或承接依据；国内一般邮箱未认证为技术部门邮箱。'),
        contact('广汽丰田汽车有限公司', 'https://www.gac-toyota.com.cn/', 'https://www.gac-toyota.com.cn/',
                source='round9/public_lowtemp/portals/gac_toyota.html', receipt='round9/public_lowtemp/portals/gac_toyota.html.receipt.json',
                quote='HTML title：广汽丰田；官网前端含产品及服务模块', entity='广汽丰田品牌官网',
                boundary='官网首页已核；电话/邮箱和具体联系组件本次未取得，留空。联系组件HTTP403不等于不存在。'),
        contact('上汽通用五菱汽车股份有限公司', 'https://www.sgmw.com.cn/', 'https://www.sgmw.com.cn/dealerSearch',
                '4008895050；4008612345', source='round9/user_handoff/contact_sources/sgmw_after_sale.txt',
                receipt='round9/user_handoff/contact_sources/sgmw_after_sale.receipt.json',
                quote='服务热线：4008895050 4008612345；版权所有：上汽通用五菱汽车股份有限公司',
                entity='上汽通用五菱汽车股份有限公司', boundary='一般服务热线/经销商服务商查询；官网pr邮箱标为媒体联系，因此未列为技术询证邮箱。'),
        contact('江西江铃集团新能源汽车有限公司', 'https://www.jmev.com/', 'https://www.jmev.com/about/',
                '400-1799-909', source='round9/user_handoff/contact_sources/jmev_about.txt',
                receipt='round9/user_handoff/contact_sources/jmev_about.receipt.json',
                quote='客服热线 400-1799-909；©2023 江西江铃集团新能源汽车有限公司',
                entity='江西江铃集团新能源汽车有限公司', boundary='一般客服转接入口；不与江铃汽车股份有限公司合并。'),
        contact('东风小康汽车有限公司', receipt='round9/public_lowtemp/portals/dfxiaokang.html.receipt.json',
                status='候选域名本次访问失败，未核实官网入口', attempted='https://www.dfxiaokang.com/',
                boundary='隧道HTTP403，仅是本次访问失败；官网、联系人和历史持有人身份未知，留空。'),
        contact('四川野马汽车股份有限公司', receipt='round9/public_lowtemp/portals/yema.html.receipt.json',
                status='候选域名本次访问失败，未核实官网入口', attempted='https://www.yemacar.com/',
                boundary='候选域名身份及入口未核；本次隧道HTTP403，不推出企业或报告不存在。'),
        contact('湖南江南汽车制造有限公司', status='未取得可核官网入口', boundary='没有已核公司官网/联系人，本次不猜域名电话或当前承接主体。'),
        contact('江苏吉麦新能源车业有限公司', status='未取得可核官网入口', boundary='没有已核公司官网/联系人，本次不猜品牌域名、电话或当前承接主体。'),
    ]
    assert len(contacts) == 9 and sum(r['lowtemp_version_rows'] for r in contacts) == 19
    assert sum(bool(r['verified_homepage_url']) for r in contacts) == 5
    assert sum(bool(r['general_public_phone']) for r in contacts) == 4
    write('优先9家企业_公开询证入口.csv', contacts)
    by_contact = {r['firm_as_historical_source']: r for r in contacts}

    institution_source = AUDIT / 'round9/public_lowtemp/公开检测机构询证入口_不认定原报告归属.csv'
    institutions = read(institution_source)
    input_paths.append(institution_source)
    for r in institutions:
        for key in ['evidence_file', 'public_contact_source']:
            p = AUDIT / 'round9/public_lowtemp' / r[key]
            assert p.exists()
            input_paths.append(p)
            r[key + '_sha256'] = sha(p)
            r[key] = str(p.relative_to(AUDIT))
        r['matching_report_institution_confirmed'] = '0'
        r['first_action'] = '先由申报企业确认原报告机构及编号，再询问该机构档案/业务部门；不向任意机构请求代认证历史事实'
    write('公开检测机构_企业确认原机构后再转接.csv', institutions)

    schema = [
        {'purpose': 'P1 JX原空能量', 'unit': '1型号1原空字段；另需身份/版本配对证明',
         'effective_fields': 'JX6550T-M5BEV税48历史配置；原battery总能量(kWh)及单位；电池系统/电芯型号与生产商；对应总质量(kg)/配置；原申报或试验版本、形成与适用日期；页码/表头/单位和可核文件来源',
         'match_rule': '若提供NC010086，L173C01和L173G01分别答能量/质量/版本，并给税48与推荐配置的正式对应关系；416kg不得在未认证配置下直接套入两系统',
         'closes': '仅在明确对应税48目标版本时关闭原空字段证据；多配置或公差仍可能不满足单值准备',
         'does_not_close': '2023目录65.17、兄弟型号数据或density乘416倒推都不能填2021原空；只有158.98/157.18密度不够'},
        {'purpose': 'P2 32联合跨界', 'unit': '32型号；对应具体配置数量待材料决定',
         'effective_fields': '完整同一配置标识；电池总能量/总质量配对及选装项、公差和附注含义；对应续驶里程/试验口径；原申报版本和证明页',
         'match_rule': '两数值必须在同配置配对，不能取多个选项的有利组合；逐版本给出技术适用期',
         'closes': '具体配置两项阈值能分类；如用于跨目录/法规资格还需身份桥和四条件材料',
         'does_not_close': '已知公差/多值不等于原字段缺失；无需为其余343区间可判断型号索取确定单值'},
        {'purpose': 'P2b 4单项细分', 'unit': '4额外型号，与32交集0',
         'effective_fields': '仅当研究要分别判定单项时，补该跨阈值项的同配置能量/质量或续航及版本、配对/公差说明',
         'match_rule': '读取原需求表标明的跨界项；另一项全包络失败已经足以判定联合失败',
         'closes': '单项结果细分', 'does_not_close': '4型号不属于尚未知联合结果的32，不应当作联合分析必补'},
        {'purpose': 'P3 跨目录身份与常规四条件/M1', 'unit': '285版本/278配置ID/170型号；43原文企业',
         'effective_fields': '税目录记录/版本与推荐配置ID、申报/公告批次、有效期的正式映射；整车型号、车辆类别/M1；储能系统/电机及选装组合；同配置30分钟最高车速、续航、声明系统密度、能耗和整备质量；四条件报告/申报证明及机构编号',
         'match_rule': '同型号同企业同日期仍不认证同配置；允许一份正式证明覆盖多行但须列完整覆盖范围',
         'closes': '身份桥与对应技术/类别证据分别验证；28/29公开声明外包络通过不等于取得测试或税资格证明',
         'does_not_close': '无M1证据不能仅按车型名称猜法律类别；public声明参数不当检验报告'},
        {'purpose': 'P3低温例外', 'unit': '19版本/12型号/8企业，是285版本的子集',
         'effective_fields': 'GB/T18386.1-2021附录A适用试验版本；报告原编号、机构、车辆/系统配置；常温与低温里程或原报告可核合规取值依据；衰减率及不超过35%证明；对应税/推荐配置桥',
         'match_rule': '同配置报告才能使用120km/95Wh/kg例外；30min速度和能耗仍核；19是配置数不一定19份独立报告',
         'closes': '逐配置匹配附录A材料和身份后验证低温证据标志',
         'does_not_close': '营销冬测、CCC、其他型号报告、2026网页或修改单线索不替代2022目标报告'},
        {'purpose': 'P4 再申报逐车资格', 'unit': '92型号，实际车辆数量未知',
         'effective_fields': '稳定匿名车辆键/VIN脱敏键；合格证/制造日期来源；具体配置与生产批次；购车/发票日期及对应政策口径；实际减免税标志/办理结果、关联再申报版本/生效日期',
         'match_rule': '车辆键在所有表保持稳定可连；制造日期和购车/发票日期分别给，不取车型公告日替代',
         'closes': '仅取得逐车证据的车辆资格可判；不得把92车型自动算成92辆',
         'does_not_close': '型号重入目录不是该型号所有存量车辆有资格；实际结果数据只有做车辆政策分析才必需'},
        {'purpose': 'P5 2208工况/试验可比性', 'unit': '2208 numeric-ready型号，五字段来源已精确连接',
         'effective_fields': '先提供能耗标签全部历史版本/原标签、标签配置ID、通告/启用/废止日期；若标签不能证明试验口径，再提供对应原报告/申报版本、适用试验标准完整年版/修改单、具体工况/测试方法、续航和能耗值、被试配置及日期',
         'match_rule': '按源记录/日期/配置分别匹配；SGM记录续航勘误608与原62其他字段各自来源保持；标签只有最新现款不能回填2023',
         'closes': '明确适用原版本工况/标准后才可按同工况比较；得到标签不保证其有所有科学字段',
         'does_not_close': '不能由批次年份或一般标准实施日猜该车工况；仅做目录时点分析无需先补全2208'},
    ]
    write('有效交回材料_按用途验收字段.csv', schema)
    common_cols = ['firm_name', 'purpose_scope', 'model_key', 'tax_batch_or_record_id', 'recommendation_config_id',
                   'historical_configuration_version', 'battery_system_variant', 'battery_manufacturer', 'motor_variant',
                   'curb_mass_kg', 'battery_total_mass_kg', 'battery_total_energy_kwh', 'range_km',
                   'declared_system_density_wh_per_kg', 'max_speed_30min_km_per_h', 'energy_consumption_kwh_per_100km',
                   'vehicle_class_m1_evidence', 'lowtemp_normal_range_km', 'lowtemp_range_km', 'lowtemp_degradation_percent',
                   'test_cycle', 'test_standard_full_version_and_amendment', 'report_id', 'report_institution',
                   'test_date', 'document_formation_date', 'technical_applicable_from', 'technical_applicable_to',
                   'historical_public_availability_date', 'public_availability_proof', 'file_name', 'page_or_cell', 'units_and_tolerance_explanation',
                   'source_unit_or_url', 'configuration_bridge_file_and_location', 'coverage_list_if_one_document_covers_multiple_rows', 'holder_or_issuer_verification_route', 'notes_unknown_or_not_applicable']
    write('交回表_配置技术工况_空白模板.csv', [], common_cols)
    write('交回表_逐车资格_空白模板.csv', [], ['firm_name', 'model_key', 'anonymous_stable_vehicle_key',
          'manufacturing_date', 'manufacturing_date_source', 'vehicle_configuration_id', 'production_batch',
          'tax_reapplication_version_and_effective_date', 'purchase_date', 'invoice_date', 'date_definition_for_policy',
          'actual_tax_exemption_indicator_or_result', 'official_result_source', 'source_unit_or_url', 'file_name', 'page_or_cell', 'notes_unknown_or_not_applicable'])

    general = '''# 合并询证模板（由用户自行联系，尚未发送）

主题：请转产品技术/认证或历史申报档案部门，协助核实附件指定车型配置

您好，我们正在核查新能源汽车购置税目录的历史配置与技术证据。附件按贵单位原文名称归并，已列车型、配置ID、原申报文件和观察日期。烦请仅就附件所选研究用途答复；如需由原检测机构提供，请确认原机构与报告编号，或说明可供核验的授权/档案查询路径。当前接收单位若与原申报主体不同，请先说明材料保管或承接关系。

请优先提供已有原申报表/原检测报告PDF或扫描件，以及方便匹配的Excel/CSV。材料需保留型号和配置版本、表头/单位、机构/报告编号、日期、相关整页和覆盖范围；涉及多个电池、质量或能耗选项时，请分别给配对关系及公差说明。无需为所有公开公差项另报一个确定单值。个人姓名、住址和完整VIN可脱敏，但车辆和配置的匿名关联键需稳定。

请把“试验/报告形成日期、该配置技术适用日期”和“该材料何时已公开或可取得的证明”分开填写。若用于2023-12-10公告前公开信息冻结分析，还需证明对应字段当时已公开或可取得；今天收到一份私人历史报告可支持历史技术事实，不能自动成为当时的公开输入。未知项请写“未知/未持有”，不要填0。

附件：《本企业_配置版本身份与低温.csv》（如有）及《本企业_型号用途与来源.csv》（如有）。字段解释见《有效交回材料_按用途验收字段.csv》，回复可用两份空白交回模板。单份报告若覆盖多配置，请列完整覆盖清单，避免重复出具。谢谢。
'''
    (OUT / '通用询证模板_用户自行发送.md').write_text(general, encoding='utf-8')

    packet_index = []
    for i, e in enumerate(enterprises, 1):
        firm = e['firm_routing_name']
        packet_id = f'P{i:03d}'
        folder = OUT / '企业附件' / packet_id
        folder.mkdir(parents=True, exist_ok=True)
        vs = [v for v in versions if v['firm_routing_name'] == firm]
        ms = [m for m in models if m['firm_routing_name'] == firm]
        if vs:
            write(f'企业附件/{packet_id}/本企业_配置版本身份与低温.csv', vs)
        if ms:
            write(f'企业附件/{packet_id}/本企业_型号用途与来源.csv', ms)
        ct = by_contact.get(firm, {})
        index = {'packet_id': packet_id, 'firm_routing_name': firm, 'packet_directory': f'企业附件/{packet_id}',
                 'identity_version_rows': len(vs), 'lowtemp_priority_flags_inside_identity_rows': sum(v['low_temperature_report_priority'] == '1' for v in vs),
                 'model_purpose_packet_rows': len(ms), 'purpose_scopes': e['purpose_scopes'],
                 'verified_entry': ct.get('verified_service_or_contact_entry', ''), 'general_phone': ct.get('general_public_phone', ''),
                 'general_email': ct.get('general_public_email', ''), 'contact_scope': ct.get('route_boundary', '本轮未核实该企业官网联系人；留空，不猜历史承接主体'),
                 'send_status': '草稿/附件未发送；先选研究用途再联系，不要求一次补全条件扩展'}
        packet_index.append(index)
        (folder / '附件使用说明.md').write_text(f'# {packet_id} — {firm}\n\n本目录仅是按原文/上下文企业名合并的本地询证附件，未发送。合并型号和版本不认证同配置，也不认证当前收件主体与历史主体相同。\n\n适用用途：{e["purpose_scopes"]}。身份版本{len(vs)}行，其中低温优先{index["lowtemp_priority_flags_inside_identity_rows"]}行已内置；型号用途附件{len(ms)}行。请先筛选本研究要完成的用途，再使用[通用模板](../../通用询证模板_用户自行发送.md)联系相应档案保管方。\n\n公开联系入口：{index["verified_entry"] or "未取得已核入口"}。{index["contact_scope"]}。\n', encoding='utf-8')
    write('企业附件索引_154路由分组.csv', packet_index)
    lookup = {r['firm_routing_name']: r for r in packet_index}
    for i, ct in enumerate(contacts, 1):
        firm = ct['firm_as_historical_source']
        idx = lookup[firm]
        extra = ''
        if firm == '江铃汽车股份有限公司':
            extra = '''优先事项：JX6550T-M5BEV第48批税目录（2021-11-05观察）的电池总能量原字段为空。请给对应历史配置的原总能量kWh、配对电池质量/系统及版本证明。公开推荐NC010086有L173C01（158.98Wh/kg）与L173G01（157.18Wh/kg）两系统，请分别答复，并提供该推荐配置与税48历史配置的正式桥。税表416kg与两系统尚未认证对应，不能乘密度倒推原能量；2023目录65.17不能替代2021原申报。\n\n有效材料到位后计划1个工作日完成首次核验；补到能量的证据闭合和是否形成唯一配置单值分别评估。\n\n'''
        else:
            extra = f'本企业低温优先配置共{ct["lowtemp_version_rows"]}版本，已包含在身份版本附件，请一次处理两用途。需同配置附录A原报告、原机构/编号、常温/低温里程及衰减率依据、配置桥和适用日期。请先确认原报告保管方，19版本不保证对应19份独立报告。\n\n'
        text = f'# {firm} — 优先询证草稿\n\n{extra}一般公开入口：{ct["verified_service_or_contact_entry"] or "未核实，留空"}；电话：{ct["general_public_phone"] or "未核实"}；邮箱：{ct["general_public_email"] or "未核实"}。{ct["route_boundary"]}\n\n本企业附件：[索引 {idx["packet_id"]}](../{idx["packet_directory"]}/附件使用说明.md)。请转产品技术/认证、原申报档案部门；由企业确认原检测机构。\n\n' + general
        path = OUT / '优先询证草稿' / f'{i:02d}_{idx["packet_id"]}.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    source_rows = []
    for p in sorted(set(input_paths)):
        source_rows.append({'file_relative_to_audit': str(p.relative_to(AUDIT)), 'sha256': sha(p), 'bytes': p.stat().st_size,
                            'purpose': '逐行来源/公开接洽入口/本轮有界核查回执；公开入口不等于原报告持有人认证'})
    write('询证来源与回执_SHA256.csv', source_rows)
    summary = {
        'generated_utc': datetime.now(timezone.utc).isoformat(), 'scientific_version': 'v1.5',
        'status': '交接材料完成；本轮公开探查有界收尾；未对外发送；不改科学数据',
        'source_task_rows_different_grains_not_missing_total': 2641,
        'enterprise_routing_groups_not_certified_current_legal_entities': 154,
        'company_model_purpose_packet_rows': 2289,
        'identity_versions': 285, 'identity_config_ids': 278, 'identity_models': 170, 'identity_written_firms': 43,
        'lowtemp_versions_inside_identity': 19, 'lowtemp_models': 12, 'lowtemp_firms': 8,
        'joint_crossing_models': 32, 'extra_single_crossing_models_joint_failure_known': 4, 'joint_single_intersection': 0,
        'distinct_threshold_followup_models': 36, 'threshold_followup_route_groups': 19,
        'vehicle_reapplication_model_targets': 92, 'actual_vehicle_count': None,
        'unknown_cycle_numeric_ready_model_targets': 2208, 'cycle_originals_fully_scanned_same_sha': 71,
        'core_original_blank_models': 1, 'core_original_blank_fields': 1, 'core_original_blank_model': 'JX6550T-M5BEV',
        'priority_company_contact_rows': 9, 'verified_brand_homepage_rows': 5, 'verified_general_phone_rows': 4,
        'verified_direct_technical_department_rows': 0, 'unverified_company_entrance_rows': 4,
        'generic_institution_entry_rows_not_original_report_attribution': 4,
        'public_channels_to_try_first': ['https://yhgscx.miit.gov.cn/ 全部历史旧/新标签；正常人工验证', 'https://service.miit-eidc.org.cn/miitxxgk/gonggao/xxgk/index?querylb=qy'],
        'public_label_records_obtained_this_round': 0,
        'manual_public_priority_models': ['JX6550T-M5BEV', 'GTM6470BFEBEV', 'CC7000CG00FBEV'],
        'new_closures': {'JX_energy': 0, 'threshold_configuration_numeric': 0, 'identity_versions': 0, 'matching_lowtemp_reports': 0, 'original_lowtemp_report_ids': 0, 'explicit_cycle_labels': 0, 'test_standard_revisions': 0},
        'freeze_date': '2023-12-10',
        'historical_technical_facts_and_then_public_information_are_separate': True,
        'field_evidence_closed_does_not_guarantee_numeric_ready_increment': True,
        'acquisition_finish_date_predictable': False,
        'JX_first_review_after_effective_material_plan_workdays': 1,
        'conditional_extended_scopes_required_for_basic_catalogue_analysis': False,
        'probe_summary_sources': {k: {'file': str(p.relative_to(AUDIT)), 'sha256': sha(p)} for k, p in sibling_paths.items()},
        'all_scientific_input_hashes_unchanged': all(sha(p) == fp for p, fp in before.items()),
        'messages_emails_forms_or_calls_sent': 0,
    }
    (OUT / 'handoff_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    README = '''# 剩余材料：按企业执行的交接

目录核心数据已经可用于当前目录和时点分析。历史原件106份已齐；当前唯一真实原空是 **JX6550T-M5BEV第48批历史配置的电池总能量，1型号1字段**。本轮JX、配置、低温和工况公开专项新增闭合均为0，未将未命中或访问失败解释成材料不存在。其他事项按研究用途选做，不需要把所有扩展材料找齐才结束当前目录分析。

先做这三步：

1. **先尝试现有公开查询入口。** [能源消耗量查询](https://yhgscx.miit.gov.cn/)可在本人正常验证后查询旧版/新版、全部历史标签；优先JX6550T-M5BEV、GTM6470BFEBEV和CC7000CG00FBEV。保留车型、标签配置ID、通告/启用/废止日期、原标签、URL与查询时间。是否实际收录目标、是否含能量或足以证明工况未知；本轮取得目标标签0份。最新现款不能直接填历史2023。参见[人工官网查询与交回格式](../public_configuration/人工官网查询_操作与交回格式.md)，无需一开始逐个向2208型号索取报告。
2. **公开材料仍不足时，先向江铃技术/认证或原申报档案部门索取JX历史配置能量。** [9家优先企业入口](优先9家企业_公开询证入口.csv)给出已核一般入口；JX商系一般电话400-880-1099，公共邮箱smc@jmc.com.cn，请转技术/认证，尚未认证部门专线。材料应对应税48历史配置；若以推荐NC010086为桥，L173C01和L173G01分别给能量/质量/版本及正式跨目录配置桥。两公开密度158.98/157.18不能乘税表416kg倒推原能量。详见[已有JX核查](../../round8/jx_public_final_pass/README.md)和本目录优先询证草稿。江铃汽车股份与江西江铃集团新能源是不同询证路由。
3. **按用途选择企业附件，再一次联系一个档案保管方。** 打开[154企业路由分组索引](企业附件索引_154路由分组.csv)，进入相应P编号文件夹，筛选本研究用途。企业只收一份合并附件；身份与低温同版本已合并。采用[通用模板](通用询证模板_用户自行发送.md)，先让企业确认原报告机构/编号，再使用[检测机构公开入口](公开检测机构_企业确认原机构后再转接.csv)。这些通用检测机构尚未认证出具目标报告。

| 用途 | 仍需什么 | 何时才需要补 |
|---|---|---|
| 核心原空 | JX1型号1电池能量字段，及原配置/版本对应证明 | 当前最高优先；有效材料到位后计划1工作日首次核验 |
| 精确阈值分类 | 32联合结果未知型号的同配置配对数值 | 要把区间跨界结果分到具体配置时 |
| 单项细分 | 额外4型号的跨界单项；与32交集0 | 联合失败已确定，仅单项研究需补 |
| 跨目录资格 | 285版本/278配置ID/170型号的正式身份桥、M1及同配置四条件证据 | 要认定真实配置技术/法律资格时；声明参数不是检测材料 |
| 低温例外 | 19版本/12型号/8企业的匹配附录A材料与身份 | 使用120km/95Wh/kg例外时；19版本已在285内，不额外请求身份 |
| 实际车辆资格 | 92再申报型号下逐车制造/购车日期、配置、稳定脱敏键和税结果 | 做具体车辆资格/政策结果时；实际车辆数未知 |
| 同工况比较 | 2208数值可用型号的历史标签/原试验版本与口径 | 做跨车同工况技术比较时；不凭批次年份推定工况 |

2641是以上不同粒度的用途记录，按来源路由名合并为154组和2289个“企业×型号”用途附件行；不是2641份缺失数据、154个已认证现存法人或2289个独立型号。企业名仅NFKC和外部空白标准化，原文字和来源SHA保留，不自动合并改名主体。36型号按19原文/上下文企业路由；285按43原文企业。BAW官网当前联系主体为“北京汽车制造厂（青岛）有限公司”，与历史名称不同，仅作转接，请其确认档案承接关系。

有效交回应有原PDF/扫描件及单位可查来源，型号/配置、报告机构和编号、日期、表头/单位、相关整页与覆盖清单可读；可附Excel方便连接。多选项必须分别配对并解释公差；个人信息和VIN可脱敏，但匿名车辆键需稳定。详见[按用途验收字段](有效交回材料_按用途验收字段.csv)和两份空白交回CSV模板。没有配对配置的声明值、不完整营销图片、其他型号报告不关闭目标材料缺口。

历史试验/申报形成与适用日期，和当时公开/可取得日期分别证明。今天拿到的私人历史报告可证明历史技术事实，进入2023-12-10公告前公开冻结输入仍需独立信息可得证明。JX能量证据闭合与是否成为单值可计算是两件事，不保证numeric-ready自动加1。等待企业/机构材料无法给确定完工日；公开核查本轮已收尾，扩展用途材料不作为当前目录分析结项的前置。

5家品牌官网已核，4家有一般客服电话；4家未取得可核官网入口，未知字段留空。广汽丰田本轮仅核首页；东风小康/野马候选访问失败不能证明官网或材料不存在，湖南江南/江苏吉麦不猜入口。本目录及全部询证草稿均未发送，未提交申请、未改科学主数据。计数和本轮关闭数见[JSON](handoff_summary.json)，来源/回执与本目录指纹分别见两份SHA表。
'''
    README = README.replace('../../round8/jx_public_final_pass/README.md', 'https://github.com/lima0531/-/blob/purchase-tax-v1-4-files/v1_5/progress_20261009/jx_public_final_pass/README.md')
    (OUT / 'README.md').write_text(README, encoding='utf-8')
    checked_links = 0
    broken_links = []
    for markdown in OUT.rglob('*.md'):
        for target in re.findall(r'\]\(([^)]+)\)', markdown.read_text()):
            if target.startswith(('https://', 'http://', '#')):
                continue
            checked_links += 1
            if not (markdown.parent / target.split('#')[0]).exists():
                broken_links.append([str(markdown.relative_to(OUT)), target])
    assert not broken_links, broken_links
    checks = {
        'scope_rows': dict(Counter(t['purpose_scope'] for t in tasks)),
        'nonempty_original_route_text_rows': sum(bool(t['firm_original_text']) for t in tasks),
        'source_date_sha_and_original_route_text_complete': all(t['firm_original_text'] and t['source_observation_date_upper'] and t['source_sha256'] for t in tasks),
        'packets_created': len(packet_index),
        'packet_version_rows_sum': sum(p['identity_version_rows'] for p in packet_index),
        'packet_lowtemp_flags_sum': sum(p['lowtemp_priority_flags_inside_identity_rows'] for p in packet_index),
        'packet_model_rows_sum': sum(p['model_purpose_packet_rows'] for p in packet_index),
        'source_sha_all_match': all(sha(AUDIT / r['file_relative_to_audit']) == r['sha256'] for r in source_rows),
        'science_sha_all_match': summary['all_scientific_input_hashes_unchanged'],
        'siblings_new_material_closures_all_zero': all(v == 0 for v in summary['new_closures'].values()),
        'markdown_local_links_checked': checked_links, 'broken_local_links': broken_links,
        'direct_technical_contact_claims': 0, 'external_sends': 0,
    }
    assert checks['nonempty_original_route_text_rows'] == 2641
    assert checks['packets_created'] == 154
    assert checks['packet_version_rows_sum'] == 285
    assert checks['packet_lowtemp_flags_sum'] == 19
    assert checks['packet_model_rows_sum'] == 2289
    assert checks['science_sha_all_match'] and checks['source_sha_all_match']
    (OUT / 'validation.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write('文件_SHA256.csv', [{'file': str(p.relative_to(OUT)), 'sha256': sha(p), 'bytes': p.stat().st_size}
                            for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != '文件_SHA256.csv' and '__pycache__' not in p.parts])
    print(json.dumps({'status': summary['status'], 'validation': checks}, ensure_ascii=False))


if __name__ == '__main__':
    main()
