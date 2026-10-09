#!/usr/bin/env python3
"""At most four TLS-verified public CDX requests; reuse saved receipts."""
import hashlib
import gzip
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
CANDIDATES = [
    ('tax_primary', 'https://fgk.chinatax.gov.cn/zcfgk/c100013/c5207263/content.html', '2014'),
    ('inner_mongolia_reprint', 'https://neimenggu.chinatax.gov.cn/zcwj/zxwj/201809/t20180929_419165.html', '2014'),
    ('tax_primary_earliest', 'https://fgk.chinatax.gov.cn/zcfgk/c100013/c5207263/content.html', 'earliest'),
    ('inner_mongolia_reprint_earliest', 'https://neimenggu.chinatax.gov.cn/zcwj/zxwj/201809/t20180929_419165.html', 'earliest'),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    requests_this_run = 0
    stopped_for_access_restriction = False
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    for label, original, period in CANDIDATES:
        saved_receipt = OUT / (label + '.receipt.json')
        if saved_receipt.exists():
            saved = json.loads(saved_receipt.read_text(encoding='utf-8'))
            saved['query_period'] = period
            results.append(saved)
            if saved['outcome'] == 'access_restricted_http_response':
                stopped_for_access_restriction = True
                break
            continue
        params = {
            'url': original, 'matchType': 'exact', 'output': 'json',
            'filter': 'statuscode:200',
            'fl': 'timestamp,original,statuscode,mimetype,digest', 'collapse': 'digest',
        }
        if period == '2014':
            params.update({'from': '2014', 'to': '2014'})
        else:
            params['limit'] = '1'
        request_url = 'https://web.archive.org/cdx/search/cdx?' + urllib.parse.urlencode(params)
        receipt = {
            'original_url': original, 'request_url': request_url,
            'query_period': period,
            'started_at_utc': datetime.now(timezone.utc).isoformat(),
            'purpose': '仅查已知公告URL的公共CDX元数据；2014限定或最早记录查询，不推定全球首发',
            'tls_verification_enabled': True, 'proxy_environment_preserved': True,
            'redirects_followed': False, 'same_url_retries': 0,
        }
        try:
            request = urllib.request.Request(request_url, headers={'Accept': 'application/json', 'User-Agent': 'purchase-tax-public-source-audit/1.0'})
            requests_this_run += 1
            try:
                response = opener.open(request, timeout=30)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                body = response.read()
                status_code, response_url, headers = response.code, response.geturl(), dict(response.headers)
            body_file = OUT / (label + '.response.bin')
            body_file.write_bytes(body)
            receipt.update(http_status=status_code, response_url=response_url,
                           headers=headers, response_body_file=body_file.name,
                           response_body_bytes=len(body), response_body_sha256=hashlib.sha256(body).hexdigest(),
                           stored_body_representation='urllib.read after transfer decoding; Content-Encoding preserved; not inferred wire length')
            if status_code == 200:
                try:
                    decoded = gzip.decompress(body) if headers.get('Content-Encoding', '').lower() == 'gzip' else body
                    data = json.loads(decoded.decode('utf-8'))
                    if isinstance(data, list) and data:
                        columns = data[0]
                        records = [dict(zip(columns, row)) for row in data[1:]]
                    elif data == []:
                        records = []
                    else:
                        raise ValueError('CDX JSON was not a row array')
                    receipt.update(outcome='parsed_cdx', records=records,
                                   listed_2014_snapshot_count=sum(str(x.get('timestamp', '')).startswith('2014') for x in records))
                except (ValueError, TypeError) as error:
                    receipt.update(outcome='unparsed_200_response', parse_error=str(error))
            elif status_code in (401, 403, 429):
                receipt['outcome'] = 'access_restricted_http_response'
                stopped_for_access_restriction = True
            else:
                receipt['outcome'] = 'non_200_http_response'
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            receipt.update(outcome='request_failed', error_type=type(error).__name__, error=str(error))
        receipt['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        saved_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        results.append(receipt)
        if stopped_for_access_restriction:
            break
    snapshots = [record for result in results for record in result.get('records', []) if str(record.get('timestamp', '')).startswith('2014')]
    all_success_empty = all(result.get('http_status') == 200 and result.get('outcome') == 'parsed_cdx' and result.get('records') == [] for result in results)
    conclusion = {
        'audit_generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': '已知第一批公告2个URL，2014限定及各最早记录共最多4次公共CDX请求；复用保存回执不重复；拒绝即停止；未下载原件或重放快照',
        'known_url_candidates': [{'label': label, 'url': url, 'query_period': period} for label, url, period in CANDIDATES],
        'requests_made': len(results), 'requests_this_run': requests_this_run, 'request_budget_maximum': 4,
        'stopped_after_access_restriction': stopped_for_access_restriction,
        'all_responses_http_200_and_empty_cdx_arrays': all_success_empty,
        'attempt_results': [{k: v for k, v in result.items() if k not in ('headers', 'records')} for result in results],
        'listed_2014_snapshots': snapshots,
        'earliest_exact_url_cdx_records': [{'original_url_queried': result['original_url'], 'records': result.get('records', [])} for result in results if result.get('query_period') == 'earliest'],
        'snapshot_content_verified': False,
        '2014_historical_online_presence_established_by_this_probe': False,
        'global_first_publication_time_certified': False,
        'historical_public_observation_upper_bound_from_this_probe': None,
        'conclusion': ('公共CDX访问受限，本轮无法观察2014快照；不把不可访问解释为历史没有快照。' if stopped_for_access_restriction else
                       '4次实际公共CDX请求均HTTP200且返回空数组；两个已知URL在2014限定查询及不限年份首条查询均未观察到快照记录。不能据此断言未收录的旧URL没有快照或公告当时没有公开，本轮不给历史公开观察上界。' if all_success_empty and len(results) == 4 else
                       '仅报告可观察CDX元数据；未重放并核实完整公告内容，不能据此认证历史首次公开。'),
        'earlier_original_miit_url_found_in_reviewed_cache': False,
        'miit_cache_search_limit': '已读round3/archive/page_manifest.json及免征首批记录；不采用减免第一批2023原页混作2014证据。',
        'old_data_reports_export_science_and_git_modified': False,
    }
    (OUT / 'conclusion.json').write_text(json.dumps(conclusion, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in conclusion.items() if k not in ('attempt_results', 'known_url_candidates', 'listed_2014_snapshots')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
