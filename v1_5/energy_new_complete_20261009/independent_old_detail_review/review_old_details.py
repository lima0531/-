#!/usr/bin/env python3
"""Independent offline review of the first-100 later old-registry details."""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def js(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def load(path):
    return json.loads(path.read_bytes())


def jsonl(path):
    with path.open(encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def leaves(obj, pointer=''):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield from leaves(value, pointer + '/' + str(key).replace('~', '~0').replace('/', '~1'))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from leaves(value, pointer + '/' + str(index))
    else:
        yield pointer, obj


def csv_write(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--detail-root', type=Path)
    parser.add_argument('--source-records', type=Path)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    detail_root = args.detail_root or args.batch_root / 'old_details'
    source_records_path = args.source_records or args.batch_root / 'independent_old_review/4497记录_旧库精确命中固定来源键.jsonl'
    cp_path = detail_root / 'checkpoint.json'
    checkpoint = load(cp_path)
    if checkpoint.get('selected_record_budget') != 100 or not checkpoint.get('completed_selected_budget') or not checkpoint.get('finished_utc'):
        raise SystemExit('First-100 planned budget has not completed; no complete review emitted.')
    source_records = jsonl(source_records_path)
    assert len(source_records) == 4497
    source_by_key = {row['record_key']: row for row in source_records}
    assert len(source_by_key) == 4497
    meta = load(detail_root / 'queue_manifest.json')
    assert meta['input_sha256'] == sha(source_records_path)
    assert meta['input_bytes'] == source_records_path.stat().st_size
    assert meta['records'] == 4497
    saved_evidence = jsonl(detail_root / 'details_readonly.jsonl')
    assert len(saved_evidence) == 100
    assert [row['record_key'] for row in saved_evidence] == [row['record_key'] for row in source_records[:100]]
    remaining = jsonl(detail_root / 'remaining_details_queue.jsonl')
    assert len(remaining) == 4397
    assert {row['record_key'] for row in remaining} == {row['record_key'] for row in source_records[100:]}
    assert checkpoint['accepted_records'] == 100 and checkpoint['remaining_fixed_queue_records'] == 4397
    assert checkpoint['entire_fixed_queue_complete'] is False

    standard_re = re.compile(r'GB\s*[/／]\s*T\s*\d+(?:\.\d+)?\s*[-—–－]\s*\d{4}')
    summaries = []
    all_literals = []
    all_differences = []
    comparison_contexts = []
    standard_fields = Counter()
    info_counts = Counter()
    full_response_groups = defaultdict(list)
    info_groups = defaultdict(list)
    cached_keys = []
    nonempty_apply_echo = []
    nonempty_number_echo = []
    bj_code_quotes = []
    dates = []
    collector_difference_records = []
    for evidence in saved_evidence:
        source = source_by_key[evidence['record_key']]
        assert evidence['source_fixed_list_record'] == source
        raw_path = detail_root / evidence['detail_file']
        receipt_path = detail_root / evidence['receipt_file']
        receipt = load(receipt_path)
        body = load(raw_path)
        assert receipt['http_status'] == 200 and receipt['tls_verified'] is True
        assert receipt['method'] == 'POST'
        assert receipt['requested_url'].endswith('/fcSearchCtr/queryDetail')
        assert receipt['request_json'] == {'applyId': source['stable_id_raw']}
        assert receipt['input_record_key'] == source['record_key']
        assert receipt['expected_model_raw'] == source['model_key']
        assert receipt['source_fixed_list_file'] == source['source_file']
        assert receipt['source_fixed_list_sha256'] == source['source_sha256']
        assert receipt['source_fixed_json_pointer'] == source['json_pointer']
        assert receipt['file'] == evidence['detail_file']
        assert receipt['bytes'] == raw_path.stat().st_size
        assert receipt['sha256'] == sha(raw_path) == evidence['detail_sha256']
        assert type(body['result']) is int and body['result'] == 1
        assert isinstance(body['info'], dict) and body['info']['vehicleNumber'] == source['model_key']
        assert evidence['detail_raw'] == body
        assert evidence['observed_utc'] == receipt['observed_utc']
        info = body['info']
        echoed_id = info.get('applyId')
        echoed_number = info.get('uniqId')
        if echoed_id not in (None, ''):
            assert echoed_id == source['stable_id_raw']
            nonempty_apply_echo.append(source['record_key'])
        if echoed_number not in (None, ''):
            assert echoed_number == source['record_number_raw']
            nonempty_number_echo.append(source['record_key'])
        if datetime.fromisoformat(receipt['observed_utc']) < datetime.fromisoformat(checkpoint['started_utc']):
            cached_keys.append(source['record_key'])
        date_items = [{'pointer': pointer, 'value_raw': value}
                      for pointer, value in leaves(info, '/info')
                      if 'date' in pointer.rsplit('/', 1)[-1].lower() or 'time' in pointer.rsplit('/', 1)[-1].lower()]
        dates.extend({'record_key': source['record_key'], **item} for item in date_items)
        literal_items = []
        for pointer, value in leaves(info, '/info'):
            if not isinstance(value, str):
                continue
            for match in standard_re.finditer(value):
                item = {'record_key': source['record_key'], 'model_key': source['model_key'],
                        'json_pointer': pointer, 'literal': match.group(), 'source_value_raw': value,
                        'detail_sha256': sha(raw_path)}
                literal_items.append(item)
                all_literals.append(item)
            if 'NEDC' in value:
                comparison_contexts.append({
                    'record_key': source['record_key'], 'model_key': source['model_key'],
                    'json_pointer': pointer, 'value_raw': value,
                    'nedc_word_occurrence_is_not_cycle_certification': True,
                    'contains_comparison_phrase': bool(re.search(r'与\s*NEDC\s*(?:工况\s*)?略有差异', value)),
                })
        independent_literal_set = {(item['json_pointer'], item['literal']) for item in literal_items}
        collector_literal_set = {(item['json_pointer'], item['literal']) for item in evidence['standard_literals_with_paths']}
        assert independent_literal_set == collector_literal_set
        if info.get('testBasisStandard') == 'BJ_18386_2017':
            bj_code_quotes.append({'record_key': source['record_key'], 'model_key': source['model_key'],
                                  'testBasisStandard_raw': info['testBasisStandard'],
                                  'otherInfo_raw': info.get('otherInfo'),
                                  'literal_standard_quotes': [item for item in literal_items if item['json_pointer'].startswith('/info/otherInfo')],
                                  'BJ_token_itself_is_not_a_formal_standard_literal': True})
        differences = []
        collector_subset = []
        for field in sorted(set(source['raw_record']) & set(info)):
            left, right = source['raw_record'][field], info[field]
            if left is not None and right is not None and left != right:
                item = {'record_key': source['record_key'], 'model_key': source['model_key'],
                        'field': field, 'list_value_raw': left, 'detail_value_raw': right,
                        'later_detail_is_not_same_historical_snapshot': True,
                        'same_configuration_conflict_certified': False}
                differences.append(item)
                all_differences.append(item)
                if field in ('vehicleNumber', 'peakPower', 'runingRange', 'powerConsumption', 'reportType'):
                    collector_subset.append(item)
        declared_differences = evidence['fixed_list_vs_later_detail_literal_differences']
        assert {(item['field'], js(item['list_value_raw']), js(item['detail_value_raw'])) for item in collector_subset} == {
            (item['field'], js(item['fixed_list_value_raw']), js(item['later_detail_value_raw'])) for item in declared_differences}
        if collector_subset:
            collector_difference_records.append(source['record_key'])
        info_counts[len(info)] += 1
        standard_fields[js(info.get('testBasisStandard'))] += 1
        full_hash = hashlib.sha256(js(body).encode()).hexdigest()
        info_hash = hashlib.sha256(js(info).encode()).hexdigest()
        full_response_groups[full_hash].append(source['record_key'])
        info_groups[info_hash].append(source['record_key'])
        summaries.append({
            'record_key': source['record_key'], 'model_key': source['model_key'],
            'request_applyId_raw': source['stable_id_raw'],
            'source_list_file': source['source_file'], 'source_list_json_pointer': source['json_pointer'],
            'source_list_sha256': source['source_sha256'], 'source_list_observed_utc': source['source_observed_utc'],
            'source_publicTime_raw': source['raw_record'].get('publicTime'),
            'detail_file': evidence['detail_file'], 'receipt_file': evidence['receipt_file'],
            'detail_bytes': raw_path.stat().st_size, 'detail_sha256': sha(raw_path),
            'detail_observed_utc': receipt['observed_utc'],
            'http_and_business_model_and_integrity_pass': True,
            'applyId_echo_raw': echoed_id, 'uniqId_echo_raw': echoed_number,
            'unique_id_echo_certified': bool(echoed_id or echoed_number),
            'info_field_count': len(info), 'testBasisStandard_raw': info.get('testBasisStandard'),
            'formal_standard_literal_occurrences': len(literal_items),
            'formal_standard_literals_json': js(sorted({item['literal'] for item in literal_items})),
            'list_vs_detail_shared_nonnull_differences': len(differences),
            'date_or_time_named_info_fields': len(date_items),
            'frozen_cycle_or_tax_configuration_closed': False,
        })
    assert len(cached_keys) == 10
    assert len(nonempty_apply_echo) == checkpoint['applyId_nonempty_echo_records']
    assert len(collector_difference_records) == checkpoint['list_detail_literal_difference_records']
    assert sum(bool(row['formal_standard_literal_occurrences']) for row in summaries) == checkpoint['standard_literal_records']
    duplicate_full = {key: values for key, values in full_response_groups.items() if len(values) > 1}
    duplicate_info = {key: values for key, values in info_groups.items() if len(values) > 1}
    requests = jsonl(detail_root / 'requests.jsonl')
    current_requests = [row for row in requests if row.get('invocation_id') == checkpoint['started_utc']]
    assert len(current_requests) == checkpoint['requests_this_invocation']
    summary = {
        'status': 'PASS', 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'network_requests_by_review': 0,
        'input_sha256': {'checkpoint': sha(cp_path), 'source_records': sha(source_records_path),
                         'details_readonly': sha(detail_root / 'details_readonly.jsonl')},
        'completed_first_queue_budget': 100, 'entire_4497_queue_complete': False,
        'accepted_details': len(summaries), 'models': len({row['model_key'] for row in summaries}),
        'remaining_details': len(remaining), 'full_byte_and_model_request_checks_passed': 100,
        'cached_records_observed_before_current_invocation': len(cached_keys),
        'requests_this_invocation': checkpoint['requests_this_invocation'],
        'total_saved_request_log_entries': len(requests),
        'applyId_nonempty_echo_records': len(nonempty_apply_echo),
        'uniqId_nonempty_echo_records': len(nonempty_number_echo),
        'info_field_count_distribution': dict(info_counts),
        'testBasisStandard_raw_distribution': dict(standard_fields),
        'records_with_formal_GB_T_literal_somewhere_in_info': sum(bool(row['formal_standard_literal_occurrences']) for row in summaries),
        'formal_literal_occurrences': len(all_literals),
        'BJ_18386_2017_raw_token_records': len(bj_code_quotes),
        'comparison_NEDC_phrase_records': len({row['record_key'] for row in comparison_contexts if row['contains_comparison_phrase']}),
        'all_NEDC_word_context_records': len({row['record_key'] for row in comparison_contexts}),
        'collector_five_field_literal_difference_records': len(collector_difference_records),
        'all_shared_nonnull_field_literal_difference_records': len({row['record_key'] for row in all_differences}),
        'all_shared_nonnull_field_literal_differences': len(all_differences),
        'detail_date_or_time_named_fields': dates,
        'distinct_full_response_objects': len(full_response_groups),
        'distinct_info_objects': len(info_groups),
        'duplicate_full_response_groups': duplicate_full,
        'duplicate_info_groups': duplicate_info,
        'earliest_accepted_detail_observed_utc': min(row['detail_observed_utc'] for row in summaries),
        'latest_accepted_detail_observed_utc': max(row['detail_observed_utc'] for row in summaries),
        'cached_record_keys': cached_keys,
        'frozen_cycle_gap_closed': 0, 'battery_energy_gap_closed': 0,
        'same_tax_configuration_identity_certified': False,
        'historical_first_public_availability_certified': False,
        'scope': 'First 100 entries of an explicitly fixed queue, observed later through normal queryDetail. Request mapping plus exact model does not replace missing applyId/uniqId echo or certify historical tax configuration. PASS refers to saved bytes, provenance and extraction, not full completion or historical eligibility.',
    }
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    (out / 'review.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    csv_write(out / '100条_原件来源与独立校验.csv', summaries, list(summaries[0]))
    for name, rows in [('标准字面及JSON路径.json', all_literals),
                       ('BJ代码及otherInfo标准原句.json', bj_code_quotes),
                       ('NEDC上下文_不作工况认证.json', comparison_contexts),
                       ('列表详情共有字段原值差异.json', all_differences)]:
        (out / name).write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'README.md').write_text(f'''# 旧库详情首100条独立只读复核

PASS范围：固定4,497条队列中的首100条原详情、请求映射、实际字节、收据SHA、HTTP200、业务result=1、响应型号及标准字面提取。首100条已完成，涉及{summary['models']}型号；全队列仍剩4,397条，本结论不声称4,497条详情已采完。

首10条是本次100条续采前取得的缓存，其原始observed_utc已保留；本次新增请求{checkpoint['requests_this_invocation']}次，不能将100条都写成本次新下载。详情取得日期与固定列表观测日期分开，不将两者合成同一事务快照或历史冻结记录。

非空applyId回显{len(nonempty_apply_echo)}条、非空uniqId回显{len(nonempty_number_echo)}条；缺失时只证明“请求所用列表applyId→本次详情同型号”，不虚构唯一编号回显或同免税配置认证。详情info字段数分布：{js(dict(info_counts))}。完整响应对象{len(full_response_groups)}种、info对象{len(info_groups)}种；重复返回对象均保留原请求来源，不能据重复字节认定不同applyId代表同配置。

{summary['records_with_formal_GB_T_literal_somewhere_in_info']}条在info实际文字中含GB/T标准字面，逐条附JSON路径及原句。BJ_18386_2017仅作原代码；其{len(bj_code_quotes)}条记录的otherInfo正式GB/T字面另列，未把BJ代码自行转换为国家标准版本。“与NEDC略有差异”等文字是比较语境，不认证采用NEDC工况。

采集器五字段差异台账有{len(collector_difference_records)}条；本复核同时比较所有共有且非空原字段，发现{summary['all_shared_nonnull_field_literal_difference_records']}条有字面差异，详细保存原值。差异只表示两次观测不同，不认证同配置冲突，不缩放单位。日期字段和公示年月均不自动认证冻结点前公开可得。

**冻结工况关闭0、电池总能量缺口关闭0；科学数据未改。** 标准声明、质量及范围参数属于新取得的可核查线索，仍需匹配历史免税配置与版本。

- [复核摘要](review.json)
- [100条来源及验证](100条_原件来源与独立校验.csv)
- [标准原句和路径](标准字面及JSON路径.json)
- [BJ代码与另见正式原句](BJ代码及otherInfo标准原句.json)
- [NEDC上下文](NEDC上下文_不作工况认证.json)
- [共有字段差异](列表详情共有字段原值差异.json)
- [复跑脚本](review_old_details.py)
- [输出SHA清单](文件_SHA256.csv)

下载仓库后可使用--batch-root指向本轮目录；或分别通过--detail-root、--source-records、--output重映射。脚本只读源目录、不请求网络；首100阶段checkpoint未完成时停止，避免伪完整复核。原JSONL及raw/receipt来自相邻old_details与independent_old_review目录。
''', encoding='utf-8')
    manifest = [{'file': path.relative_to(out).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                for path in sorted(out.rglob('*'))
                if path.is_file() and path.name != '文件_SHA256.csv' and '__pycache__' not in path.parts]
    csv_write(out / '文件_SHA256.csv', manifest, ['file', 'bytes', 'sha256'])
    print(js({key: summary[key] for key in ['status', 'accepted_details', 'models', 'remaining_details', 'records_with_formal_GB_T_literal_somewhere_in_info', 'testBasisStandard_raw_distribution', 'BJ_18386_2017_raw_token_records', 'all_shared_nonnull_field_literal_difference_records']}))


if __name__ == '__main__':
    main()
