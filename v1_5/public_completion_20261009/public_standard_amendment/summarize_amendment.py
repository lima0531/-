#!/usr/bin/env python3
"""Summarize saved amendment evidence; no network requests or science edits."""
import csv
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(text):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', '', text))).strip()


def main():
    seeds = {
        'smvic_search_cached.html': ROOT / 'round9/public_lowtemp/institution_queries/smvic_18386.1.html',
        'official_base_detail_cached.html': ROOT / 'round8/public_archive_final_pass/standard_registry_detail.html',
        'official_base_query_cached.json': ROOT / 'round8/public_archive_final_pass/standard_registry_query.html',
        'official_base_metadata_cached.json': ROOT / 'round8/public_archive_final_pass/standard_registered_metadata.json',
    }
    inputs = []
    for filename, source in seeds.items():
        before = sha(source)
        (OUT / filename).write_bytes(source.read_bytes())
        inputs.append({'source_relative_path': str(source.relative_to(ROOT)), 'saved_copy': filename,
                       'bytes': source.stat().st_size, 'sha256_before': before, 'sha256_after': sha(source)})
        assert inputs[-1]['sha256_before'] == inputs[-1]['sha256_after'] == sha(OUT / filename)
    smvic = (OUT / 'smvic_search_cached.html').read_text(encoding='utf-8')
    anchor = re.search(r'<a\s+href="/indexnews/1384"[^>]*>(.*?)</a>', smvic, re.S)
    assert anchor
    anchor_text = clean(anchor.group(1))
    assert '18386.1-2021' in anchor_text and '第1号修改单' in anchor_text
    list_date = re.search(r'\b\d{4}-\d{2}-\d{2}\b', anchor_text).group()
    assert list_date == '2026-07-09'
    base = json.loads((OUT / 'official_base_metadata_cached.json').read_text())
    assert base['standard_number'] == 'GB/T 18386.1-2021'
    detail = (OUT / 'official_base_detail_cached.html').read_text(encoding='utf-8')
    other = re.search(r'<a[^>]+href="(https://std\.samr\.gov\.cn/gb/search/gbDetailed\?id=53B90BF525773166E06397BE0A0A5D69)"[^>]*>(.*?)</a>', detail, re.S)
    assert other and '轻型汽车能源消耗量标识 第2部分' in clean(other.group(2))
    records = json.loads((OUT / 'requests.json').read_text())
    assert len(records) == 9 and len({x['request_url'] for x in records}) == len(records)
    actual_requests = len(records)
    query_results = []
    strict_matches = []
    for receipt in records:
        path = OUT / receipt['evidence_file']
        assert sha(path) == receipt['sha256'] and path.stat().st_size == receipt['bytes']
        if path.name.startswith('official_query_') and receipt['http_status'] == 200:
            result = json.loads(path.read_text())
            rows = [{**row, 'C_STD_CODE': clean(row['C_STD_CODE']), 'C_C_NAME': clean(row['C_C_NAME'])} for row in result['rows']]
            query_results.append({'file': path.name, 'request_url': receipt['request_url'], 'total': result['total'], 'page_number': result['pageNumber'], 'displayed_rows': rows})
            for row in rows:
                if re.sub(r'\s+', '', row['C_STD_CODE']) == 'GB/T18386.1-2021' and '第1号修改单' in row['C_C_NAME']:
                    strict_matches.append(row)
    assert not strict_matches
    smvic_request = next(x for x in records if x['evidence_file'] == 'smvic_amendment.html')
    assert smvic_request['http_status'] == 503
    search_receipt = next(x for x in records if x['evidence_file'] == 'public_search_amendment.html')
    search_results = json.loads((OUT / 'public_search_results.json').read_text())
    openstd_request = next(x for x in records if x['evidence_file'] == 'official_openstd_base_amendment.html')
    assert search_receipt['http_status'] == 200 and openstd_request['http_status'] == 403
    final_search = next(x for x in records if x['evidence_file'] == 'public_search_official_2025.html')
    final_results = json.loads((OUT / 'public_search_official_2025_results.json').read_text())
    notice_result = next(x for x in final_results if x['url'] == 'https://openstd.samr.gov.cn/bzgk/std/nd?no=2462')
    notice_request = next(x for x in records if x['evidence_file'] == 'official_2025_19_fulltext_notice.html')
    assert final_search['http_status'] == 200 and notice_request['http_status'] == 403
    evidence = {
        'audit_generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_standard': 'GB/T 18386.1-2021', 'target_amendment': '第1号修改单',
        'target_standard_name': base['standard_name'],
        'status': 'institutional_lead_only; official_amendment_publication_and_implementation_not_verified',
        'official_amendment_registry_id': None, 'official_amendment_announcement_number': None,
        'official_amendment_publication_date': None, 'official_amendment_implementation_date': None,
        'institution_lead': {'url': 'https://hss.smvic.com.cn/indexnews/1384', 'anchor_text': anchor_text,
                             'list_date': list_date, 'list_date_is_official_amendment_publication_date': False,
                             'list_date_is_official_amendment_implementation_date': False,
                             'saved_source': 'smvic_search_cached.html', 'body_http_status': 503,
                             'body_result': 'upstream connect timeout; not retried'},
        'official_query_results': query_results, 'strict_amendment_matches_observed': strict_matches,
        'base_standard_reference_only': {
            'standard_number': base['standard_number'], 'official_id': base['official_registry_id'],
            'publication_date': base['official_registered_publication_date'],
            'implementation_date': base['official_registered_implementation_date'],
            'observed_status': base['official_registered_current_status'],
            'dates_used_as_amendment_dates': False,
            'current_status_or_absent_successor_proves_no_amendment': False,
        },
        'excluded_similar_amendment': {
            'url': other.group(1), 'anchor_text': clean(other.group(2)),
            'reason': '轻型汽车能源消耗量标识第2部分属于另标准；不得移用为18386.1修改单',
            'dates_borrowed': False,
        },
        'public_search_extension': {
            'actual_public_queries': 2, 'actual_official_link_follow_ups': 2,
            'search_response_file': 'public_search_amendment.html',
            'search_results_file': 'public_search_results.json',
            'returned_results': search_results,
            'third_party_2025XG1_or_2025_amendment_phrases_are_official_date_evidence': False,
            'official_openstd_response': openstd_request,
            'final_official_site_2025_query_file': 'public_search_official_2025.html',
            'final_official_site_2025_results': final_results,
            '2025_19_fulltext_notice_result': notice_result,
            '2025_19_fulltext_notice_response': notice_request,
            '2025_19_reference_only_from_search_index_not_verified_source_body': True,
            'blocked_source_not_retried_or_access_bypassed': True,
        },
        'actual_network_requests': actual_requests, 'original_request_budget_maximum': 10,
        'final_request_budget_maximum': 9,
        'same_failed_url_retried': False, 'source_or_access_restrictions_bypassed': False,
        'stop_reason': '机构正文一次503；四条官方查询未取得严格匹配修改单id/公告原文；两次公开搜索发现真实SAMR标准全文页及2025年第19号全文公开通知，两独立URL各一次403。累计9请求后最终停止，不重试或绕限制；正式字段未知',
        'frozen_2023_values_changed': False, 'science_export_or_git_modified': False,
        'queried_absence_proves_amendment_nonexistence': False,
        'historical_cached_inputs': inputs, 'cached_source_bytes_unchanged': True,
    }
    (OUT / 'standard_amendment_evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    fields = [
        ('修改单', '正式公告号', '', '未取得', '', '', 0),
        ('修改单', '官方登记id', '', '未取得严格匹配', 'official_query_exact_amendment.json;official_query_number.json;official_query_name.json;official_query_amendment_type.json', '编号+修改单名称同时匹配才可纳入', 0),
        ('修改单', '正式发布日期', '', '未认证', 'smvic_amendment.html.receipt.json;requests.json', '机构正文503且无匹配正式记录', 0),
        ('修改单', '正式实施日期', '', '未认证', 'smvic_amendment.html.receipt.json;requests.json', '机构正文503且无匹配正式记录', 0),
        ('机构列表', '列表网页日期', list_date, '已观察；不能移作正式发布/实施日', 'smvic_search_cached.html', '/indexnews/1384锚文本相邻spantime', 0),
        ('基础标准', '官方登记发布日期', base['official_registered_publication_date'], '已取得基础标准字段；不是修改单', 'official_base_metadata_cached.json;official_base_detail_cached.html', 'GB/T18386.1-2021基础标准id BD89DE8E07723D08E05397BE0A0A4FAD', 0),
        ('基础标准', '官方登记实施日期', base['official_registered_implementation_date'], '已取得基础标准字段；不是修改单', 'official_base_metadata_cached.json;official_base_detail_cached.html', 'GB/T18386.1-2021基础标准id BD89DE8E07723D08E05397BE0A0A4FAD', 0),
        ('公共搜索', '第三方修改单年份措辞', '2025XG1/2025年第1号修改单', '二级线索；不是正式发布日期或实施日期', 'public_search_results.json;public_search_amendment.html', '商业/转载搜索结果片段；未用于官方字段', 0),
        ('官方全文平台', '当前访问状态', 'HTTP403', '真实SAMR标准入口未取得；停止不重试', 'official_openstd_base_amendment.html.receipt.json', '公开搜索实际给出hcno=018D351EFF1AACD87C5919D0F21BEEBE', 0),
        ('公共搜索', '官方公告编号线索', '2025年第19号（全文公开通知题名）', '仅搜索索引线索；原文403，正式修改单公告号未认证', 'public_search_official_2025_results.json;official_2025_19_fulltext_notice.html.receipt.json', '实际官方链接https://openstd.samr.gov.cn/bzgk/std/nd?no=2462，未取得正文', 0),
    ]
    with (OUT / '正式修改单字段_逐来源核查.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['target_standard','object','field','value','verification_status','evidence_file','source_locator','used_as_amendment_official_date'])
        w.writeheader()
        for obj, field, value, status, file, locator, used in fields:
            w.writerow({'target_standard': 'GB/T 18386.1-2021', 'object': obj, 'field': field, 'value': value,
                        'verification_status': status, 'evidence_file': file, 'source_locator': locator,
                        'used_as_amendment_official_date': used})
    readme = f'''# GB/T 18386.1—2021《第1号修改单》正式日期核查

本轮取得机构与公共搜索线索，**尚未取得该修改单的正式发布日期、实施日期、公告号或官方登记id**。四条全国标准平台定向查询没有给出编号与“第1号修改单”同时匹配的记录；机构正文一次HTTP503。另补两次公开入口发现搜索，真实SAMR标准全文页与2025年第19号全文公开通知两个独立资源各一次HTTP403；累计9次请求后最终停止，没有重复失败URL或绕访问限制。

已保存SMVIC搜索列表明确列出 `E7-GB/T18386.1-2021 电动汽车能量消耗量和续驶里程试验方法第1部分:轻型汽车《第1号修改单》`，真实链接为 `https://hss.smvic.com.cn/indexnews/1384`，相邻列表日期为 **{list_date}**。该日期属于机构列表网页，未认证为修改单正式发布或实施日。正文返回上游连接超时，因此未取得可跟进的正式公告号或附件原文。

| 本轮公共请求 | 实际结果 | 能支持的结论 |
|---|---|---|
| SMVIC明示修改单正文 | HTTP503，上游连接超时 | 仅保留列表线索，正文未取得 |
| 18386.1-2021＋第1号修改单 | HTTP200，total=0 | 本次指定查询未匹配 |
| 编号18386.1 | HTTP200，total=1 | 基础标准GB/T18386.1-2021 |
| 标准题名前缀 | HTTP200，total=2 | 基础标准18386.1及18386.2 |
| 第1号修改单类型词 | HTTP200，total=0 | 此公共查询未列该类型，不能推断修改单不存在 |
| 公开搜索入口发现 | HTTP200，10条实际结果 | 政府标准入口及第三方2025修改单/征求意见线索；不是正式日期证据 |
| 实际SAMR全文平台标准入口 | HTTP403 | 官方内容未取得；失败后停止，不重试或换路由 |
| 2025修改单政府域最后定向搜索 | HTTP200，10条实际结果 | 实际2025年第19号全文公开通知链接；仍须原文核定 |
| 2025年第19号全文公开通知独立URL | HTTP403 | 通知正文未取得；累计9请求后最终停止 |

基础标准的官方登记发布日2021-03-09、实施日2021-10-01和“现行”状态是另一组字段，不移用为修改单日期；本次详情未列后继，也不表示没有修改单。缓存详情中的相关“修改单”链接 `53B90BF525773166E06397BE0A0A5D69` 明示为“轻型汽车能源消耗量标识 第2部分：可外接充电式混合动力电动汽车和纯电动汽车”，属于另标准，已排除。

新增公开搜索实际返回 `https://openstd.samr.gov.cn/bzgk/std/newGbInfo?hcno=018D351EFF1AACD87C5919D0F21BEEBE`，已跟进并保存403响应。第三方结果有“[Including 2025XG1]”“2025年第1号修改单”措辞，CATARC结果片段提及修改单征求意见稿；这些属于入口发现线索，未用于填写正式日期或认证实施状态，未另行跟进非政府网页或下载商业全文。

基于新出现的2025线索，最后一条政府域定向搜索实际返回“关于公开2025年第19号中国国家标准公告中国家标准全文的通知”，真实URL `https://openstd.samr.gov.cn/bzgk/std/nd?no=2462`。搜索片段提到“电动汽车能量消耗量和续驶里程试验方法 第1部分：轻型汽车”等3项修改单；独立通知URL一次请求也为403。因此2025年第19号仅列公告入口线索，尚未以通知原文认证具体修改单批准发布日、实施日或正式公告号。

[字段CSV](正式修改单字段_逐来源核查.csv)保留正式字段为空及原因；[证据JSON](standard_amendment_evidence.json)保留严格匹配条件、各实际查询行、来源界限及未闭合结论。每份新响应均有receipt、确切请求URL、状态/响应头/时间及SHA。四份此前已取得的页面/登记JSON逐字节复制到本目录，前后SHA均一致。旧来源与科学数据均未改写。

实际网络请求{actual_requests}次，原预算上限10次，最后指令收紧为累计至多9次；新增入口发现共2次公开搜索及2个真实官方资源请求。`fetch_public.py`读取已保存回执避免重复请求并以9次为硬上限；`summarize_amendment.py`仅重建证据摘要，不发网络请求。到此以线索及访问边界收尾；未以负面查询认证“无修改单”，未影响2023冻结值、export或Git。文件清单排除自身。
'''
    (OUT / 'README.md').write_text(readme, encoding='utf-8')
    print(json.dumps({'status':evidence['status'], 'actual_network_requests':actual_requests, 'official_dates_verified':False, 'cached_inputs_unchanged':True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
