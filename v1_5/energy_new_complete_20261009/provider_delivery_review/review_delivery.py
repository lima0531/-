#!/usr/bin/env python3
"""Verify provider compressed delivery against all 58 original payload hashes."""
import argparse, csv, gzip, hashlib, json, re, tarfile
from datetime import datetime, timezone
from pathlib import Path

def digest(raw): return hashlib.sha256(raw).hexdigest()
def sha(path): return digest(path.read_bytes())
def js(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

parser = argparse.ArgumentParser()
parser.add_argument('--delivery-root', type=Path,
                    default=Path(__file__).resolve().parent / 'received')
parser.add_argument('--page-root', type=Path, default=Path(__file__).resolve().parent.parent / 'public_new_snapshot')
parser.add_argument('--user-manifest', type=Path, default=Path(__file__).resolve().parent.parent / 'user_submitted/delivery_manifest_用户原文.json')
parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
args = parser.parse_args()
out, delivery = args.output, args.delivery_root
out.mkdir(parents=True, exist_ok=True)
assert (delivery / 'delivery_manifest.json').read_bytes() == args.user_manifest.read_bytes()
manifest = json.loads((delivery / 'delivery_manifest.json').read_bytes())
declared = {row['path']: row for row in manifest['files']}
assert len(declared) == 58
payload = {}
for name in ['summary.md', 'old_library_verification.json', 'requests.jsonl', 'query_runs.jsonl']:
    payload[name] = (delivery / name).read_bytes()
with gzip.open(delivery / 'records.jsonl.gz', 'rb') as handle:
    payload['records.jsonl'] = handle.read()
with tarfile.open(delivery / 'new_registry_raw_pages.tar.gz', 'r:gz') as archive:
    regulars = [m for m in archive.getmembers() if m.isfile()]
    assert len(regulars) == 53
    for member in archive.getmembers():
        assert not member.issym() and not member.islnk()
        if not member.isfile(): continue
        match = re.fullmatch(r'new_registry_raw_pages/(new_page\d{4}\.json)', member.name)
        assert match and '..' not in member.name
        key = 'raw/responses/' + match.group(1)
        assert key not in payload
        payload[key] = archive.extractfile(member).read()
assert set(payload) == set(declared)
checked = []
for key in sorted(declared):
    raw, row = payload[key], declared[key]
    assert len(raw) == row['bytes'] and digest(raw) == row['sha256'], key
    checked.append({'file': key, 'bytes': len(raw), 'sha256': digest(raw), 'manifest_identity_pass': True})
pages, references = {}, {}
for page in range(1, 54):
    key = f'raw/responses/new_page{page:04d}.json'
    raw = payload[key]
    assert raw == (args.page_root / f'new_currentPage/page{page:04d}_response.json').read_bytes()
    body = json.loads(raw); info = body['info']
    assert body['result'] == 200 and info['currentPage'] == page
    assert info['totalSize'] == 10479 and info['pages'] == 53 and info['pageSize'] == 200
    assert len(info['list']) == (200 if page < 53 else 79)
    pages[page] = info
    for index, row in enumerate(info['list']): references[(page, index)] = row
records = [json.loads(line) for line in payload['records.jsonl'].splitlines() if line.strip()]
assert len(records) == len(references) == 10479
keys, full_rows, ids = set(), set(), set()
for row in records:
    key = (row['page'], row['row_0based']); assert key not in keys
    keys.add(key); raw = references[key]; assert row['raw'] == raw
    assert row['full_row_sha256'] == digest(js(raw).encode())
    assert row['uuid'] == raw['uuid'] and row['vehicleModel'] == raw['vehicleModel']
    assert row['recordNumber'] == raw['recordNumber'] and row['library'] == 'new'
    ids.add(row['uuid']); full_rows.add(row['full_row_sha256'])
assert keys == set(references) and len(full_rows) == 10479 and len(ids) == 10476
requests = [json.loads(line) for line in payload['requests.jsonl'].splitlines() if line.strip()]
runs = [json.loads(line) for line in payload['query_runs.jsonl'].splitlines() if line.strip()]
assert len(requests) == len(runs) == 53
assert {row['request_json']['currentPage'] for row in requests} == set(pages)
assert {row['page'] for row in runs} == set(pages)
for request in requests:
    assert request['method'] == 'POST' and request['request_json']['pageSize'] == 200
    assert request['request_json']['energyType'] == '8'
for row in runs:
    info = pages[row['page']]; raw = payload[row['file']]
    assert row['http_status'] == 200 and row['result'] == 200
    assert row['response_bytes'] == len(raw) and row['response_sha256'] == digest(raw)
    assert row['rows'] == len(info['list'])
    for field in ['currentPage', 'pageSize', 'pages', 'size', 'totalSize']:
        assert row['echo_' + field] == info[field]
time_fields = sorted({key for row in requests + runs for key in row if any(term in key.lower() for term in ['time', 'utc', 'date'])})
reuse_marker_fields = sorted({key for row in requests + runs for key in row if any(term in key.lower() for term in ['cache', 'reuse', 'attempt'])})
proof = {
    'status': 'PASS', 'generated_utc': datetime.now(timezone.utc).isoformat(),
    'network_requests_by_review': 0, 'delivered_repository_commit': '3cb9150',
    'compressed_source_files': [dict(file=p.name, bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(delivery.iterdir()) if p.is_file() and p.name != 'README.md'],
    'payload_manifest_items_verified': 58, 'payload_bytes_verified': sum(len(raw) for raw in payload.values()),
    'new_raw_pages_same_as_our_observed_raw': 53, 'records_full_field_source_positions_verified': 10479,
    'unique_uuid': 10476, 'unique_full_rows': 10479,
    'request_log_entries': 53, 'query_run_log_entries': 53,
    'query_log_page_echo_and_hash_checks_pass': True,
    'record_full_row_sha_recipe': 'UTF-8 compact JSON sort_keys=True, ensure_ascii=False, separators=(comma, colon)',
    'request_log_timestamp_fields': time_fields, 'request_log_reuse_or_attempt_fields': reuse_marker_fields,
    'producer_53_fresh_network_requests_certified': False,
    'producer_observation_time_or_zero_failed_attempts_certified': False,
    'source_boundary': 'Delivered logs cover 53 accepted page entries but contain no per-request observation time, reuse marker or attempt history. Summary still says 52 fresh plus 1 reused; manifest says 53. No assertion of fresh-request count or original clock authentication.',
    'source_scientific_input_modified': False,
}
(out / 'review.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
with (out / '58逻辑原件_逐SHA验收.csv').open('w', encoding='utf-8-sig', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=list(checked[0])); writer.writeheader(); writer.writerows(checked)
(out / 'README.md').write_text('''# 后续仓库完整交付：58件逻辑原件全部验收

上传阶段发现仓库提交`3cb9150`新增DeepSeek完整交付7个物理文件。已保留合入，不覆盖对方内容。压缩包中的53页原响应和records.jsonl解压后，与其原delivery_manifest的全部58条逻辑payload逐SHA/大小核验通过，实测57,291,686 B。records的10,479行逐page/row位置、完整原字段、uuid及紧凑全行hash都与本环境原页一致；53页原字节也与本环境实取相同。

因此此前“附件只有3件”仍描述当时附件，但**现在records和两份日志均已在仓库取得并验收**。无需再请用户索取完整payload。两份日志各53行，其页码、回显、SHA和大小与53成功页面自洽。

日志没有逐请求时间、复用标记或失败尝试历史。它们支持53成功页条目，不能单据日志证明53次本轮新网络请求、零失败尝试或13:0x实际观测时间；summary的“52新＋1复用”与manifest的53仍须口径说明。此前13:0x与第4页原收据时序冲突不能由无时间戳的日志消除。不自行补时间或把复用当新采。

936原样精确、trim938、545/961规范化候选、加upper才得566/1087，以及458/460有效日期而非519的纠错均由这些**同字节原件**支持，完整交付不会消除计数口径问题。

- [验收与时间边界](review.json)
- [58逻辑原件逐SHA](58逻辑原件_逐SHA验收.csv)
- [可重跑脚本](review_delivery.py)
- [原完整交付7文件同字节归档](received/README.md)

复跑时`--delivery-root`指向原7文件目录、`--page-root`指向本轮public_new_snapshot、`--output`指定结果目录。不进行网络请求，不将tar成员提取到文件系统，不修改原始交付或科学数据。
''', encoding='utf-8')
paths = sorted(p for p in out.rglob('*') if p.is_file() and p.name != '文件_SHA256.csv')
with (out / '文件_SHA256.csv').open('w', encoding='utf-8-sig', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=['file', 'bytes', 'sha256']); writer.writeheader()
    writer.writerows(dict(file=p.relative_to(out).as_posix(), bytes=p.stat().st_size, sha256=sha(p)) for p in paths)
print(json.dumps({key: proof[key] for key in ['status', 'payload_manifest_items_verified', 'payload_bytes_verified', 'records_full_field_source_positions_verified', 'request_log_entries', 'request_log_timestamp_fields']}, ensure_ascii=False))
