#!/usr/bin/env python3
"""Read-only independent old-library byte, pagination and exact-model review.

No network and no writes to original inputs. Valid selection is pinned by the
existing checkpoint, never inferred from lexicographic/latest attempt names.
"""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def json_row(value):
    # Matches the documented original full-row hash recipe, including spaces.
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def csv_read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def csv_write(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry-root', type=Path, default=Path('/workspace/purchase_tax_audit/round10/public_energy_registry'))
    parser.add_argument('--targets', type=Path, default=Path('/workspace/purchase_tax_audit/round10/bulk_handoff/2208精确请求型号名单.csv'))
    parser.add_argument('--user-review', type=Path, default=Path('/workspace/attachments/3d25d40c-f714-41dd-a317-67797d52c3de/old_library_verification.json'))
    parser.add_argument('--golden', type=Path, default=Path('/workspace/purchase_tax_audit/round6/pre_review_scientific_csv_sha256.json'))
    parser.add_argument('--science-root', type=Path, default=Path('/workspace/file_export_proposal/v1_5'))
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    checkpoint_path = args.registry_root / 'old_checkpoint.json'
    checkpoint = read_json(checkpoint_path)
    user_review = read_json(args.user_review)
    targets_rows = csv_read(args.targets)
    targets = {row['model_key'] for row in targets_rows}
    assert len(targets_rows) == len(targets) == 2208
    assert 'JX6550T-M5BEV' not in targets
    assert checkpoint['completed'] is True
    assert checkpoint['pages_validated'] == checkpoint['reported_pages'] == 47
    assert checkpoint['rows'] == checkpoint['reported_total'] == 9336
    assert len(checkpoint['source_page_files']) == 47
    assert checkpoint['filters'] == {'fuelType': '8'}

    attempts = []
    valid_by_page = defaultdict(list)
    pattern = re.compile(r'page(\d{4})(?:_attempt(\d+))?_response\.json$')
    for path in sorted((args.registry_root / 'old_currentPage').glob('*_response.json')):
        match = pattern.fullmatch(path.name)
        assert match is not None, path.name
        page, attempt_number = int(match.group(1)), int(match.group(2) or 1)
        rel = path.relative_to(args.registry_root).as_posix()
        receipt_path = path.with_name(path.name.replace('_response.json', '_receipt.json'))
        receipt = read_json(receipt_path)
        actual_bytes, actual_sha = path.stat().st_size, digest(path)
        # Integrity of failed and successful attempts is checked before admission.
        assert receipt['file'] == rel
        assert receipt['bytes'] == actual_bytes
        assert receipt['sha256'] == actual_sha
        assert receipt['library'] == 'old' and receipt['page'] == page
        assert receipt['tls_verified'] is True
        assert receipt['method'] == 'POST'
        assert receipt['request_json'] == {'currentPage': page, 'pageSize': 200, 'fuelType': '8'}
        assert receipt['requested_url'].endswith('/fcSearchCtr/queryList')
        issues = []
        document = None
        try:
            document = read_json(path)
        except (json.JSONDecodeError, UnicodeDecodeError):
            issues.append('invalid_json')
        if receipt['http_status'] != 200:
            issues.append('http_status_not_200')
        info = document.get('info') if isinstance(document, dict) else None
        if document is not None:
            if not isinstance(document, dict) or type(document.get('result')) is not int or document.get('result') != 1:
                issues.append('business_result_not_1')
            if not isinstance(info, dict):
                issues.append('info_not_object')
            else:
                if info.get('currentPage') != page:
                    issues.append('echo_currentPage_mismatch')
                if info.get('pageSize') != 200:
                    issues.append('echo_pageSize_mismatch')
                if info.get('totalSize') != 9336 or info.get('pages') != 47:
                    issues.append('echo_total_or_pages_mismatch')
                expected_size = 200 if page < 47 else 136
                if not isinstance(info.get('list'), list) or len(info['list']) != expected_size or info.get('size') != expected_size:
                    issues.append('page_row_count_mismatch')
        valid = not issues
        item = {
            'page': page, 'attempt': attempt_number, 'file': rel,
            'receipt_file': receipt_path.relative_to(args.registry_root).as_posix(),
            'http_status': receipt['http_status'], 'actual_bytes': actual_bytes,
            'actual_sha256': actual_sha, 'receipt_hash_and_bytes_match': True,
            'observed_utc': receipt['observed_utc'],
            'json_parseable': document is not None,
            'business_result': document.get('result') if isinstance(document, dict) else None,
            'echo_currentPage': info.get('currentPage') if isinstance(info, dict) else None,
            'rows': len(info['list']) if isinstance(info, dict) and isinstance(info.get('list'), list) else None,
            'valid_for_checkpoint': valid,
            'exclusion_reasons': issues,
            'selected_by_explicit_checkpoint': rel in checkpoint['source_page_files'],
        }
        attempts.append(item)
        if valid:
            valid_by_page[page].append(item)
    # A timeout before response bytes arrived has a receipt but no body file.
    # It must remain a separate failed attempt, never invented as HTTP503.
    existing_receipts = {item['receipt_file'] for item in attempts}
    for receipt_path in sorted((args.registry_root / 'old_currentPage').glob('*_receipt.json')):
        receipt_rel = receipt_path.relative_to(args.registry_root).as_posix()
        if receipt_rel in existing_receipts:
            continue
        receipt = read_json(receipt_path)
        assert receipt_path.name == 'page0017_receipt.json'
        assert receipt['page'] == 17 and receipt['attempt'] == 1
        assert receipt['error'] == 'TimeoutError'
        assert 'http_status' not in receipt and 'bytes' not in receipt and 'sha256' not in receipt
        assert receipt['request_json'] == {'currentPage': 17, 'pageSize': 200, 'fuelType': '8'}
        assert receipt['tls_verified'] is True and receipt['method'] == 'POST'
        expected_body = receipt_path.name.replace('_receipt.json', '_response.json')
        assert not receipt_path.with_name(expected_body).exists()
        attempts.append({
            'page': 17, 'attempt': 1,
            'file': f'old_currentPage/{expected_body}',
            'receipt_file': receipt_rel,
            'http_status': None, 'actual_bytes': None, 'actual_sha256': None,
            'receipt_hash_and_bytes_match': None,
            'observed_utc': receipt['observed_utc'], 'json_parseable': False,
            'business_result': None, 'echo_currentPage': None, 'rows': None,
            'valid_for_checkpoint': False, 'exclusion_reasons': ['TimeoutError_no_response_body'],
            'selected_by_explicit_checkpoint': False, 'receipt_error': receipt['error'],
            'response_body_saved': False,
        })
    assert len(attempts) == 49
    assert set(valid_by_page) == set(range(1, 48))
    # A second successful attempt with different bytes would be a separate
    # observation, not an automatic replacement or a fabricated atomic snapshot.
    multi_valid_different = [page for page, values in valid_by_page.items()
                             if len({value['actual_sha256'] for value in values}) > 1]
    assert not multi_valid_different, multi_valid_different
    assert all(len(values) == 1 for values in valid_by_page.values())
    attempt_by_file = {item['file']: item for item in attempts}
    user_pages = {item['page']: item for item in user_review['pages']}
    assert len(user_pages) == len(user_review['pages']) == 47
    all_rows = []
    exact_records = []
    by_model = defaultdict(list)
    page_reviews = []
    for page, rel in enumerate(checkpoint['source_page_files'], 1):
        attempt = attempt_by_file[rel]
        assert attempt['valid_for_checkpoint'] and attempt['page'] == page
        document = read_json(args.registry_root / rel)
        info = document['info']
        rows = info['list']
        ids = [row['applyId'] for row in rows]
        assert all(isinstance(value, str) and value for value in ids)
        expected = {
            'page': page, 'file': rel, 'result': document['result'],
            'echo_currentPage': info['currentPage'], 'rows': len(rows),
            'unique_applyId': len(set(ids)), 'echo_totalSize': info['totalSize'],
            'echo_pages': info['pages'], 'response_sha256': attempt['actual_sha256'],
        }
        user_page = user_pages[page]
        mismatch = {key: {'actual': value, 'user': user_page.get(key)}
                    for key, value in expected.items() if value != user_page.get(key)}
        assert not mismatch, (page, mismatch)
        page_reviews.append({**expected, 'actual_bytes': attempt['actual_bytes'],
                             'receipt_file': attempt['receipt_file'],
                             'receipt_hash_and_bytes_match': True,
                             'request_and_echo_currentPage_match': True,
                             'user_page_matches': True,
                             'observed_utc': attempt['observed_utc']})
        for row_index, raw_row in enumerate(rows):
            row_sha = hashlib.sha256(json_row(raw_row).encode('utf-8')).hexdigest()
            all_rows.append(raw_row)
            model = raw_row.get('vehicleNumber')
            if model not in targets:
                continue
            record = {
                'library': 'old',
                'record_key': f"old:{raw_row['applyId']}:{row_sha}",
                'source_occurrence': f'old:{page}:{row_index}',
                'model_key': model,
                'stable_id_raw': raw_row['applyId'],
                'record_number_raw': raw_row.get('uniqId'),
                'raw_full_row_sha256': row_sha,
                'source_file': rel,
                'json_pointer': f'/info/list/{row_index}',
                'source_sha256': attempt['actual_sha256'],
                'source_observed_utc': attempt['observed_utc'],
                'raw_record': raw_row,
            }
            exact_records.append(record)
            by_model[model].append(record)

    ids = [row['applyId'] for row in all_rows]
    full_hashes = [hashlib.sha256(json_row(row).encode()).hexdigest() for row in all_rows]
    assert len(all_rows) == len(set(ids)) == len(set(full_hashes)) == 9336
    assert len(by_model) == 1233
    assert len(exact_records) == 4497
    assert len({row['record_key'] for row in exact_records}) == 4497
    assert len({row['source_occurrence'] for row in exact_records}) == 4497
    supplied_summary = user_review['summary']
    expected_summary = {
        'pages': 47, 'pages_listed': 47, 'parse_errors': [], 'rows': 9336,
        'unique_applyId': 9336, 'echo_mismatch': [], 'page_size_anomalies': [],
        'totalSize_values': [9336], 'result_values': [1],
    }
    assert all(supplied_summary.get(key) == value for key, value in expected_summary.items())

    retry_reviews = []
    for page in (10, 17):
        original = attempt_by_file[f'old_currentPage/page{page:04d}_response.json']
        selected = attempt_by_file[f'old_currentPage/page{page:04d}_attempt02_response.json']
        if page == 10:
            assert original['http_status'] == 503 and original['actual_bytes'] == 95
        else:
            assert original['http_status'] is None and original['actual_bytes'] is None
            assert original['receipt_error'] == 'TimeoutError'
            assert original['response_body_saved'] is False
        assert not original['json_parseable'] and not original['selected_by_explicit_checkpoint']
        assert selected['http_status'] == 200 and selected['business_result'] == 1
        assert selected['echo_currentPage'] == page and selected['rows'] == 200
        assert selected['selected_by_explicit_checkpoint'] and selected['valid_for_checkpoint']
        retry_reviews.append({'page': page, 'failed_first_attempt': original,
                              'valid_checkpoint_attempt': selected})

    model_rows = []
    for model in sorted(by_model):
        records = by_model[model]
        codes = sorted({str(condition.get('workConditionType'))
                        for record in records
                        for condition in (record['raw_record'].get('workConditionVos') or [])
                        if condition.get('workConditionType') is not None})
        model_rows.append({
            'model_key': model, 'old_raw_rows': len(records),
            'old_unique_applyId': len({record['stable_id_raw'] for record in records}),
            'old_cycle_codes_raw_json': json_row(codes),
            'source_record_keys_json': json_row([record['record_key'] for record in records]),
            'source_occurrences_json': json_row([record['source_occurrence'] for record in records]),
            'same_tax_configuration_identity_certified': False,
            'historical_public_availability_certified': False,
            'can_replace_frozen_scientific_input': False,
        })
    csv_write(output / '1233型号_旧库精确命中集合.csv', model_rows, list(model_rows[0]))
    with (output / '4497记录_旧库精确命中固定来源键.jsonl').open('w', encoding='utf-8') as handle:
        for record in exact_records:
            handle.write(json_row(record) + '\n')
    # Fixed gold fingerprint compares all 52 scientific CSVs, not documentation.
    golden = read_json(args.golden)
    assert len(golden) == 52
    scientific_results = []
    for rel, expected in sorted(golden.items()):
        path = args.science_root / rel
        actual = {'bytes': path.stat().st_size, 'sha256': digest(path)}
        assert actual == expected, rel
        scientific_results.append({'file': rel, **actual, 'matches_frozen_gold': True})

    review = {
        'status': 'PASS', 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'network_requests': 0, 'original_input_or_scientific_files_modified': False,
        'inputs': {
            'old_checkpoint': {'file': str(checkpoint_path), 'sha256': digest(checkpoint_path)},
            'user_old_library_verification': {'file': str(args.user_review), 'sha256': digest(args.user_review)},
            '2208_target_list': {'file': str(args.targets), 'sha256': digest(args.targets)},
            'scientific_gold': {'file': str(args.golden), 'sha256': digest(args.golden)},
        },
        'summary': {
            'saved_attempts_checked': 49, 'selected_valid_pages': 47,
            'raw_rows': 9336, 'unique_applyId': 9336, 'unique_full_rows': 9336,
            'successful_attempts': 47, 'excluded_http_503_attempts': 1,
            'excluded_timeout_attempts_without_body': 1,
            'saved_response_bodies_checked': 48,
            'all_saved_body_receipt_hashes_and_bytes_verified': True,
            'all_selected_pages_business_and_request_echo_verified': True,
            'user_verification_page_mismatches': 0,
            'user_verification_summary_matches': True,
            'target_models': 2208, 'exact_old_models': 1233,
            'exact_old_records': 4497, 'exact_model_match_is_raw_string_equality': True,
            'multiple_valid_attempts_with_different_bytes': multi_valid_different,
            'scientific_gold_files_verified': 52,
            'source_view_filter': {'fuelType': '8'},
            'atomic_transaction_snapshot_claimed': False,
            'public_current_view_is_not_historical_exhaustiveness': True,
            'unmarked_frozen_cycle_list_closed': 0,
            'battery_energy_gap_closed': 0,
        },
        'selection_rule': 'Explicit checkpoint source_page_files plus HTTP200, verified receipt size/SHA, business result1, currentPage/pageSize/totalSize/pages/row-length checks. Merely parseable JSON is insufficient. No latest-attempt fallback and no mixing separate valid observations.',
        'observation_window': {
            'earliest_page_observed_utc': min(row['observed_utc'] for row in page_reviews),
            'latest_page_observed_utc': max(row['observed_utc'] for row in page_reviews),
            'checkpoint_started_utc_is_resume_not_first_page_time': checkpoint['started_utc'],
        },
        'pages': page_reviews, 'retry_reviews': retry_reviews,
        'all_attempts': attempts, 'scientific_gold_verification': scientific_results,
    }
    (output / 'review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'README.md').write_text('''# 旧库分页及重试独立复核

只读重核通过：47个有效页、9,336原始行、9,336唯一applyId，与用户交付的旧库核验文件逐页一致。47页的实际字节、SHA256、收据、请求页码、业务result=1、回显页码及页长全部通过；最后一页136行。两次失败加重试共49个已保存收据；其中48个有响应字节，其字节和SHA均核验，另一个超时无响应原件。

第10页首次为HTTP503、95字节、非JSON网关文本。第17页首次则是TimeoutError，只有收据、无HTTP状态和响应字节；不能写成“同样503/95字节”。checkpoint明确采用两页各自attempt02：HTTP200、result=1、页码正确、200行。此差别不影响用户旧库逐页JSON核验结果及9,336总行数。

不能只按默认首次文件计数，也不能用“任何可JSON解析尝试”作为成功标准。若一页出现多个有效但字节不同的尝试，应保留各次观测边界并核查，不能自动拿最新文件拼接成同一事务快照。本轮每页只有一个有效尝试，未发生此歧义。

从原始页重新进行原字符串精确匹配：2,208目标中命中1,233型号、4,497记录；JX6550T-M5BEV不在该2,208名单。输出集合可与新库集合计算交、并、差，不能将两库型号数量直接相加。原工况代码不映射为标准版本，不证明同免税配置，也不证明公告前公开可得；冻结工况清单关闭数仍为0。fuelType=8筛选视图包含原有响应分类异常，不将每一行认证为纯电车型。

本复核不请求网络、不修改原数据；52份冻结科学CSV均与gold指纹一致。请求观测窗口见review.json；checkpoint的started_utc是续采启动时间，早于此时的缓存页仍保留各自真实observed_utc。公开筛选视图分页采集不具有事务原子性，也不证明隐藏或全部历史备案已收齐。

- [复核明细](review.json)
- [1,233型号集合](1233型号_旧库精确命中集合.csv)
- [4,497记录及固定来源键](4497记录_旧库精确命中固定来源键.jsonl)
- [可复跑脚本](review_old_snapshot.py)
- [输出SHA清单](文件_SHA256.csv)

固定来源键采用old:applyId:全行SHA256；来源位置另保留old:page:零基行号、原页文件、JSON Pointer、原页SHA及请求观测时间。全行SHA使用Python json.dumps(record, ensure_ascii=False, sort_keys=True)的UTF-8字节（默认空格），与既有旁表一致。

复跑时可传--registry-root、--targets、--user-review、--golden、--science-root及--output。脚本只在--output目录写复核产物；原库及名单均只读。仓库已有[原旧库及checkpoint](https://github.com/lima0531/-/tree/purchase-tax-v1-4-files/v1_5/energy_registry_20261009/public_energy_registry)及[2,208型号名单](https://github.com/lima0531/-/blob/purchase-tax-v1-4-files/v1_5/energy_registry_20261009/bulk_handoff/2208精确请求型号名单.csv)。
''', encoding='utf-8')
    manifest_rows = []
    for path in sorted(output.rglob('*')):
        if path.is_file() and path.name != '文件_SHA256.csv' and '__pycache__' not in path.parts:
            manifest_rows.append({'file': path.relative_to(output).as_posix(),
                                  'bytes': path.stat().st_size, 'sha256': digest(path)})
    csv_write(output / '文件_SHA256.csv', manifest_rows, ['file', 'bytes', 'sha256'])
    print(json.dumps(review['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
