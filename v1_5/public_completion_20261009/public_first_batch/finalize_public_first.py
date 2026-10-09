#!/usr/bin/env python3
"""Offline audit of round-9 first-batch source dates; no science/export writes."""
import csv
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT.parents[1] / 'round8/public_archive_final_pass'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(name, rows):
    with (ROOT / name).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def decoded(path):
    raw = path.read_bytes()
    try:
        return raw.decode('utf-8')
    except UnicodeError:
        return raw.decode('gb18030', errors='replace')


def observation(name, field, value, kind, locator, conclusion, boundary):
    receipt_path = ROOT / (name + '.receipt.json')
    receipt = json.loads(receipt_path.read_text())
    source_path = ROOT / (name + '.html')
    assert sha(source_path) == receipt['sha256']
    return {'source_name': name, 'field': field, 'value': value, 'date_semantics': kind,
            'source_url': receipt['request_url'], 'evidence_file': str(source_path),
            'source_sha256': receipt['sha256'], 'observed_at_utc': receipt['retrieved_at_utc'],
            'field_locator_or_quote': locator, 'conclusion': conclusion, 'boundary': boundary,
            'certifies_historical_actual_first_online': '0'}


def main():
    hainan = decoded(ROOT / 'hainan_first_full.html')
    mof = decoded(ROOT / 'mof_historical_news.html')
    esnai = decoded(ROOT / 'esnai_first_full.html')
    assert '发布日期： 2014-08-26' in hainan and '成文日期： 2014-08-26' in hainan
    assert '2014年8月27日' in hainan and '2014年第54号' in hainan
    assert '8月28日，工业和信息化部会同税务总局印发' in mof
    assert '2014年9月18日 来源：中国财经报' in mof
    assert '2014-8-27' in esnai and '2014年第54号' in esnai
    rows = [
        observation('hainan_first_full', 'regional_registered_publication_date', '2014-08-26',
                    '当前地方法规库明示发布日期；与自身正文落款冲突', 'HTML table 发布日期：2014-08-26; meta PubDate=2014-08-26',
                    '只保留登记观察，不认证此日真实上线', '页成文日期亦登记8/26，正文却落款8/27；当前来源标总局政策库，不能自行解释一日差异'),
        observation('hainan_first_full', 'regional_registered_signed_date', '2014-08-26',
                    '当前地方法规库成文日期字段', 'HTML table 成文日期：2014-08-26',
                    '与正文落款8/27冲突，不能替代主管原件落款', '不把表头登记误当可靠真实首次公开日'),
        observation('hainan_first_full', 'body_signed_date', '2014-08-27',
                    '完整54号正文落款', '工业和信息化部 国家税务总局<br /> 2014年8月27日',
                    '完整公告及真实车型附件href当前可读，落款仍只是落款', '未重下载已齐的目录PDF，链接路径20200403不用于历史日期'),
        observation('mof_historical_news', 'reported_catalogue_issuance_day', '2014-08-28',
                    '财政部转载中国财经报对印发事件的报道', '8月28日，工业和信息化部会同税务总局印发《免征车辆购置税的新能源汽车车型目录》（第一批）。',
                    '新增同期政策报道印发线索；不是完整原公告或车型附件上线记录', '不把印发或报道公布措辞作全网首发；该新闻未提供第一批车型PDF'),
        observation('mof_historical_news', 'historical_news_labeled_date', '2014-09-18',
                    '财政部新闻页明示日期及meta登记', '2014年9月18日 来源：中国财经报; meta PubDate=2014-09-18 10:39:00',
                    '仅证这篇历史报道的登记日期', '不转作原公告/附件在2014年的真实网页观察上界'),
        observation('esnai_first_full', 'document_issuance_date', '2014-08-27',
                    '完整正式法规转载页的发文时间字段', '发文时间：2014-8-27; 实施时间：2014-9-1',
                    '完整54号正文和真实车型附件href当前取得，网页历史发布时间未明示', '附件路径/upload_files/14/20149122313185431.pdf不得推成2014-09-12上线日期'),
    ]
    prior = json.loads((PRIOR / 'first_batch_registered_metadata.json').read_text())
    for key, value, evidence_key, boundary in [
        ('registered_public_date_in_official_index', '2014-08-27', 'official_query_evidence', '复用round8主管税库pubDate登记；本轮不重请求、不升格历史实际首次上线'),
        ('page_html_metadata_PubDate', '2026-06-02 15:18:48', 'official_primary_page_evidence', '仅HTML meta字段，保留与索引差异，不解释迁移或修改原因'),
    ]:
        evidence = prior[evidence_key]
        assert sha(Path(evidence['file'])) == evidence['sha256']
        rows.append({'source_name':'round8_tax_primary_reused','field':key,'value':value,
                     'date_semantics':'复用主管现存登记字段', 'source_url':evidence['source_url'],
                     'evidence_file':evidence['file'],'source_sha256':evidence['sha256'],
                     'observed_at_utc':evidence['retrieved_at_utc'], 'field_locator_or_quote':key,
                     'conclusion':'登记层已取得；科学日期未改','boundary':boundary,
                     'certifies_historical_actual_first_online':'0'})
    rows.append({'source_name':'round9_bounded_conclusion','field':'historical_actual_first_online_date',
                 'value':'','date_semantics':'仍未核实','source_url':'','evidence_file':str(ROOT / 'conclusion.json'),
                 'source_sha256':'','observed_at_utc':datetime.now(timezone.utc).isoformat(),
                 'field_locator_or_quote':'5次公共CDX与具体源页/新闻/登记字段分层判断',
                 'conclusion':'本轮新增闭合0项；无可给出的新历史公开观察上界',
                 'boundary':'不将检索无结果、404、空CDX视为历史未公开；不阻塞2023–2024目录状态分析',
                 'certifies_historical_actual_first_online':'0'})
    write_csv('首批日期字段_来源与可信范围.csv', rows)

    attempts = []
    for path in sorted(ROOT.rglob('*.receipt.json')):
        item = json.loads(path.read_text())
        evidence = item.get('evidence_file')
        if not evidence and item.get('response_body_file'):
            evidence = str(path.parent / item['response_body_file'])
        fingerprint = item.get('sha256', item.get('response_body_sha256', ''))
        if evidence:
            assert sha(Path(evidence)) == fingerprint
        label = path.stem.replace('.receipt', '')
        classification = '入口发现或检索辅助；未认证历史首发'
        if path.parent.name == 'cdx': classification = '实际公共CDX空数组；不证明不存在'
        if label == 'esnai_cdx_2014': classification = '新转载页公共CDX 503，未取历史快照'
        if label == 'hainan_first_full': classification = '完整官方转载与附件href；登记8/26与正文8/27冲突'
        if label == 'mof_historical_news': classification = '历史政策新闻；报道印发8/28，无车型附件'
        if label == 'esnai_first_full': classification = '完整正式法规转载与附件href；发文非网页发布日期'
        if label.startswith('miit_first_'): classification = '真实索引发现主管旧公告入口，当前404'
        if label in ('google_first','baidu_first','sogou_first','shui5_first_full'): classification = 'JS/安全验证响应，未取得目标实质内容'
        if label.startswith('search_') or label == 'bing_html_zh': classification = '检索结果无关，未取得目标实质内容'
        attempts.append({'receipt_file':str(path.relative_to(ROOT)), 'request_url':item['request_url'],
                         'method':item.get('request_method','GET'),
                         'observed_at_utc':item.get('retrieved_at_utc',item.get('started_at_utc','')),
                         'http_status':item.get('http_status',''),'status':item.get('status',item.get('outcome','')),
                         'bytes':item.get('bytes',item.get('response_body_bytes','')),'sha256':fingerprint,
                         'response_classification':classification,'purpose':item.get('purpose','')})
    write_csv('实际请求与结果.csv', attempts)
    cdx = json.loads((ROOT / 'cdx/conclusion.json').read_text())
    assert cdx['requests_made'] == 4 and cdx['all_responses_http_200_and_empty_cdx_arrays']
    summary = {
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'document_number':'工业和信息化部 国家税务总局公告2014年第54号',
        'scope':'一次有界历史公开档案补查；具体官方公告/正式转载/新闻与公共CDX分别留证',
        'actual_requests_this_round_including_cdx':len(attempts),
        'http_200_responses':sum(row['http_status']==200 for row in attempts),
        'new_complete_official_reprint_pages':1,
        'new_complete_formal_third_party_reprint_pages':1,
        'new_official_historical_news_pages':1,
        'new_original_miit_indexed_urls_current_http404':2,
        'registered_layer_already_obtained_in_round8':'2014-08-27',
        'regional_register_vs_own_body_conflict':{'regional_pub_date':'2014-08-26','regional_signed_field':'2014-08-26','body_signed_day':'2014-08-27'},
        'historical_news_reported_issuance_day':'2014-08-28',
        'historical_news_labeled_date':'2014-09-18',
        'public_cdx_attempts':5,'official_known_url_cdx_http200_empty_arrays':4,'new_esnai_cdx_http_status':503,
        'actual_historical_first_online_date_verified':False,
        'new_historical_public_observation_upper_bound':None,
        'previously_unresolved_historical_first_online_items_closed':0,
        'historical_first_online_item_still_unverified':1,
        'first_online_unknown_is_current_analysis_blocker':False,
        'no_historical_nonpublication_inferred_from_empty_search_or_cdx':True,
        'original_pdf_or_zip_re_downloaded':False,
        'science_dates_main_data_export_and_git_modified':False,
        'registry_conflict_and_news_not_adopted_as_scientific_dates':True,
    }
    (ROOT / 'conclusion.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    write_csv('复用证据_SHA256.csv',[{'input_file':str(PRIOR/'first_batch_registered_metadata.json'),'sha256':sha(PRIOR/'first_batch_registered_metadata.json'),'method':'read_only_reuse_no_new_request'}])
    write_csv('文件_SHA256.csv',[{'file':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':sha(path)}
                               for path in sorted(ROOT.rglob('*')) if path.is_file() and '__pycache__' not in path.parts and path != ROOT/'文件_SHA256.csv'])
    print(json.dumps(summary,ensure_ascii=False))


if __name__ == '__main__':
    main()
