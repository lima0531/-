#!/usr/bin/env python3
"""Refresh only delivery requirements from preserved round-8 official evidence."""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
STANDARD_TABLES = ('公开标准登记_可选待补字段.csv', '公开标准登记_本轮已核字段.csv')
PROGRESS_LINK = '../progress_20261009/README.md'
JX_TEMPLATE_LINK = '../progress_20261009/jx_public_final_pass/向企业索取材料_文本模板.md'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields=None):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def source_dir(explicit=None):
    candidates = [Path(explicit)] if explicit else [
        OUT.parent / 'progress_20261009/public_archive_final_pass',
        Path('/workspace/purchase_tax_audit/round8/public_archive_final_pass'),
    ]
    for path in candidates:
        if (path / 'standard_registered_metadata.json').is_file():
            return path.resolve()
    raise FileNotFoundError('Use --evidence-dir to locate the preserved official round-8 evidence.')


def refresh(evidence_dir=None):
    evidence = source_dir(evidence_dir)
    standard = json.loads((evidence / 'standard_registered_metadata.json').read_text())
    first = json.loads((evidence / 'first_batch_registered_metadata.json').read_text())
    assert standard['standard_number'] == 'GB/T 18386.1-2021'
    assert standard['official_registered_publication_date'] == '2021-03-09'
    assert standard['official_registered_implementation_date'] == '2021-10-01'
    assert standard['registered_replaces_relation'] == '部分代替'
    assert not first['full_historical_first_online_time_verified']
    assert first['registered_public_date_in_official_index'] == '2014-08-27'
    for item in [standard['query_evidence'], standard['detail_evidence'], standard['predecessor_evidence'],
                 first['official_query_evidence'], first['official_primary_page_evidence']]:
        assert sha(evidence / Path(item['file']).name) == item['sha256']

    detail = standard['detail_evidence']
    predecessor = standard['predecessor_evidence']
    observation = detail['retrieved_at_shanghai']
    fields = [
        ('standard_release_date', '2021-03-09', '已取得官方登记发布日期',
         '登记发布日期；不作为车型试验报告、配置认证或历史上线时刻。', 'HTML lines 1111,1191; query ISSUE_DATE'),
        ('standard_current_status', '现行', '已取得查询时登记状态',
         '仅截至2026-10-09本次官方查询观察；不保证此后状态不变。', 'HTML lines 956,1168; query STATE'),
        ('replaces_standard', 'GB/T 18386-2017', '已取得直接部分替代关系，双方登记详情交叉核对',
         '关系为部分代替；2017页另列的GB/T 18386.2-2022不视为2021轻型标准的后继。', 'HTML lines 1127,1136,1141,1206,1208'),
        ('replaced_by_standard', '本次登记未列出后继标准', '已核本次完整登记详情关系图',
         '只描述本次详情页未列出；不声称未来永不替代或所有外部记录均不存在。', 'HTML standard-state relation section'),
    ]
    rows = []
    for field, value, status, boundary, locator in fields:
        rows.append({
            'standard_number': standard['standard_number'], 'field': field, 'value': value,
            'status': status, 'source_required': '已取得全国标准信息公共服务平台具体登记页；本字段无需用户补交',
            'implementation_date': '2021-10-01',
            'replacement_relation': '部分代替' if field == 'replaces_standard' else '',
            'observation_date': '2026-10-09', 'observed_at_shanghai': observation,
            'source_url': detail['source_url'], 'source_sha256': detail['sha256'],
            'evidence_file': str(evidence / Path(detail['file']).name), 'source_locator': locator,
            'corroborating_source_url': predecessor['source_url'] if field == 'replaces_standard' else standard['query_evidence']['source_url'] if field in ('standard_release_date', 'standard_current_status') else '',
            'corroborating_source_sha256': predecessor['sha256'] if field == 'replaces_standard' else standard['query_evidence']['sha256'] if field in ('standard_release_date', 'standard_current_status') else '',
            'boundary': boundary,
        })
    for name in STANDARD_TABLES:
        write_csv(OUT / name, rows)
    assert (OUT / STANDARD_TABLES[0]).read_bytes() == (OUT / STANDARD_TABLES[1]).read_bytes()

    document = OUT / '需要用户亲自提供的数据.md'
    text = document.read_text(encoding='utf-8-sig')
    if PROGRESS_LINK not in text:
        title, rest = text.split('\n', 1)
        text = title + '\n\n最新完成数量、剩余条件需求及工期边界见 [2026-10-09最新总账](' + PROGRESS_LINK + ')。\n' + rest
    jx_note = ('\n官方推荐目录2021年第10批已找到同型号配置ID **NC010086**，以及电池版本 '
               '**L173C01 / L173G01**，可据此向企业询证。公开记录仍未给出两个版本的总能量，'
               '也未取得各版本能量与质量配对，或它们与免征第48批配置的对应关系。'
               '这些编号不能关闭总能量缺口。可直接使用 [向企业索取材料的文本模板](' + JX_TEMPLATE_LINK + ')。\n')
    if JX_TEMPLATE_LINK not in text:
        anchor = '这里所说的“原空字段”范围是公告前风险集的单值输入，不是声称所有目录都没有其他空格。\n'
        assert anchor in text
        text = text.replace(anchor, anchor + jx_note)
    old_heading = '## 当前公开访问未取得的可选补证'
    new_heading = '## 公开登记已补证，历史首次上线仍有边界'
    start = text.find(old_heading)
    if start == -1:
        start = text.index(new_heading)
    end = text.index('## 只在研究市场政策效应时', start)
    current_section = '''## 公开登记已补证，历史首次上线仍有边界

第1批2014年第54号公告已取得国家税务总局政策法规库的唯一匹配登记记录：`pubDate` 字段为 **2014-08-27**。该登记日期字段的缺口已关闭；它不能单独证明历史实际首次上线。当前官方原页可见“成文日期”2014-08-27、正文实施日期2014-09-01，而 HTML 的 `meta PubDate` 为 **2026-06-02 15:18:48**。保留页面与检索字段的差异，不推断差异产生原因。PDF 创建时间2014-08-29也不作为首发日。本轮未修改科学日期或研究主数据，历史实际首次上线未证仅作为档案边界，不阻塞2023–2024目录状态分析。

GB/T 18386.1—2021 已取得官方具体登记详情：**发布日期2021-03-09、实施日期2021-10-01、截至2026-10-09本次查询为现行、部分代替GB/T 18386-2017**。直接部分替代关系由两份标准详情页交叉核对。2021标准的本次完整详情关系图未列后继标准，仅说明本次登记观察，不声称以后永不替代。四行已核字段见 [公开标准登记本轮已核字段](公开标准登记_本轮已核字段.csv)；旧名 [可选待补字段表](公开标准登记_可选待补字段.csv) 保留兼容，内容已同步为本轮结果。无需用户再补这些公开登记字段或为此寻找非公开技术材料；配置身份、低温报告及逐车材料仍按各自用途收集。官方URL、SHA256、观察时点和结论边界已列入字段表及 [输入来源表](输入来源与SHA256.csv)。

'''
    text = text[:start] + current_section + text[end:]
    document.write_text(text, encoding='utf-8')

    purpose_path = OUT / '需要用户亲自提供_按用途与优先级.csv'
    purposes = read_csv(purpose_path)
    matched = 0
    for row in purposes:
        if row['material'] in ('首批精确公开日及标准登记余项', '历史实际首次上线档案边界'):
            row.update({
                'priority': '可选历史档案边界', 'material': '历史实际首次上线档案边界',
                'scope': '首批历史实际首次上线1项；本轮所需公开登记待补0项',
                'needed_fields': '仅若另做历史首发溯源：首批实际首次上线的历史归档证据；现存税库pubDate=2014-08-27和标准四项已取得',
                'needed_when': '仅额外历史首发溯源研究；当前分析无需用户补公开登记或非公开技术材料',
                'row_checklist': '公开标准登记_本轮已核字段.csv；需要用户亲自提供的数据.md',
                'boundary': '标准发布2021-03-09/实施2021-10-01/现行仅截至2026-10-09/部分代替2017/本次未列后继；首批meta仅2026-06-02，不推断原因；不阻塞2023–24分析',
            })
            matched += 1
        if row['material'] == '公告前真实原空字段':
            row['boundary'] = 'SGM请求已闭合；NC010086/L173C01/L173G01仅为询证线索，仍无能量、版本能量质量配对及免征配置桥'
    assert matched == 1
    write_csv(purpose_path, purposes)

    summary_path = OUT / 'requirements_summary.json'
    summary = json.loads(summary_path.read_text())
    summary['public_registry_updated_utc'] = datetime.now(timezone.utc).isoformat()
    summary['public_registry_completion'] = {
        'observation_date_shanghai': '2026-10-09',
        'standard_compatible_rows': 4, 'standard_public_registry_pending_fields': 0,
        'standard_publication_date': '2021-03-09', 'standard_implementation_date': '2021-10-01',
        'standard_status_as_of_observation': '现行', 'standard_status_observed_at_shanghai': observation,
        'standard_replaces': 'GB/T 18386-2017', 'standard_replaces_relation': '部分代替',
        'standard_successor_display_observation': '本次完整登记详情未列后继标准，不作未来绝对判断',
        'first_batch_official_index_pubDate': '2014-08-27',
        'first_batch_page_meta_PubDate': '2026-06-02 15:18:48',
        'first_batch_actual_first_online_verified': False,
        'first_batch_registered_date_pending': False,
        'historical_first_online_unknown_is_optional_boundary': True,
        'current_analysis_required_public_registry_pending_fields': 0,
        'user_nonpublic_materials_requested_for_registry_completion': False,
        'scientific_dates_or_main_data_modified_in_this_update': False,
        'source': str(evidence), 'latest_ledger': PROGRESS_LINK,
    }
    summary['jx_public_inquiry_leads'] = {
        'model': 'JX6550T-M5BEV', 'recommendation_configuration_id': 'NC010086',
        'battery_versions': ['L173C01', 'L173G01'],
        'energy_obtained': False, 'energy_mass_pairing_obtained': False,
        'tax_exempt_configuration_bridge_verified': False, 'inquiry_template': JX_TEMPLATE_LINK,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    provenance_path = OUT / '输入来源与SHA256.csv'
    provenance = read_csv(provenance_path)
    extra_fields = ['source_url', 'observed_at_utc', 'boundary']
    field_names = list(provenance[0])
    for name in extra_fields:
        if name not in field_names:
            field_names.append(name)
    for row in provenance:
        for name in extra_fields:
            row.setdefault(name, '')
        if row['input'].endswith('round4/public_gaps/standard/标准登记_待人工补字段.csv'):
            row['method'] = 'historical_source_retained; superseded_by_round8_registered_fields'
            row['boundary'] = '旧时点公开缺口记录保留为历史来源；本轮四行不再沿用其空值或待补状态'
    new_names = [
        'standard_registered_metadata.json', 'standard_registry_query.html', 'standard_registry_query.receipt.json',
        'standard_registry_detail.html', 'standard_registry_detail.receipt.json',
        'standard_replaced_2017_detail.html', 'standard_replaced_2017_detail.receipt.json',
        'first_batch_registered_metadata.json', 'tax_first_final_query.html', 'tax_first_final_query.receipt.json',
        'first_batch_primary_registered_page.html', 'first_batch_primary_registered_page.receipt.json',
        'final_public_archive_summary.json',
    ]
    for name in new_names:
        path = evidence / name
        receipt_path = path if name.endswith('.receipt.json') else path.with_name(path.stem + '.receipt.json')
        receipt = json.loads(receipt_path.read_text()) if receipt_path.is_file() else {}
        row = {
            'output': '公开标准登记四行兼容表/本轮已核表及requirements说明' if name.startswith('standard_') else '首批官方登记与历史首发边界说明',
            'input': str(path), 'input_sha256': sha(path), 'method': 'offline_accept_preserved_round8_official_evidence',
            'source_url': receipt.get('request_url', ''), 'observed_at_utc': receipt.get('retrieved_at_utc', ''),
            'boundary': '现行与未列后继仅截至本次登记观察；pubDate不是历史实际首发认证；不修改科学数据',
        }
        provenance = [old for old in provenance if old['input'] != row['input']]
        provenance.append(row)
    jx_path = evidence.parent / 'jx_public_final_pass/向企业索取材料_文本模板.md'
    if jx_path.is_file():
        provenance = [old for old in provenance if old['input'] != str(jx_path)]
        provenance.append({
            'output': 'JX询证线索与企业材料模板链接', 'input': str(jx_path), 'input_sha256': sha(jx_path),
            'method': 'link_preserved_round8_inquiry_template', 'source_url': '', 'observed_at_utc': '',
            'boundary': 'NC010086及两个电池版本仅为询证线索；能量、质量配对、免征配置桥均未取得',
        })
    write_csv(provenance_path, provenance, field_names)
    write_csv(OUT / '文件_SHA256.csv', [
        {'file': path.name, 'bytes': str(path.stat().st_size), 'sha256': sha(path)}
        for path in sorted(OUT.iterdir()) if path.is_file() and path.name != '文件_SHA256.csv'
    ])
    print(json.dumps({'directory': str(OUT), 'standard_rows': 4, 'public_registry_pending_fields': 0,
                      'historical_first_online_verified': False, 'science_data_modified': False}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir')
    refresh(parser.parse_args().evidence_dir)
