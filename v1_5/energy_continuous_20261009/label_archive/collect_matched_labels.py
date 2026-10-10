#!/usr/bin/env python3
"""Archive exactly matched new-library labels, preserving record state variants.

Only public anonymous requests are made. A denied or unparseable successful
response is a stop condition, never a reason to change network paths.
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import fitz

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT.parent / 'public_new_snapshot'
TARGETS = ROOT / 'inputs/2208型号_固定工况待核清单.csv'
OLD_MODELS = ROOT / 'inputs/1233型号_旧库原文精确命中集合.csv'
BASE = 'https://yhgscx.miit.gov.cn/fuel-consumption-center/fuel-consumption-center/file/file/file/download'
CUTOFF = '2023-12-10'
MATCH_MODE = 'raw'
CANONICAL_ARGS = dict(sort_keys=True, ensure_ascii=False)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    return digest(path.read_bytes())


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def read_models(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        return set()
    key = 'model_key' if 'model_key' in rows[0] else 'vehicleModel'
    if key not in rows[0]:
        key = next(k for k in rows[0] if 'model' in k.lower())
    return {r[key] for r in rows}


def build_queue():
    state = json.loads((SNAPSHOT / 'new_checkpoint.json').read_text(encoding='utf-8'))
    assert state['completed'] and state['pages_validated'] == state['reported_pages'], 'new snapshot incomplete'
    targets = read_models(TARGETS)
    assert len(targets) == 2208
    old_models = read_models(OLD_MODELS)
    rows, jobs = [], {}
    for source_file in state['source_page_files']:
        path = SNAPSHOT / source_file
        raw = path.read_bytes()
        data = json.loads(raw)
        info = data['info']
        assert data['result'] == 200 and info['pageSize'] == 200
        page = info['currentPage']
        for offset, row in enumerate(info['list']):
            model_raw = row.get('vehicleModel')
            if not isinstance(model_raw, str):
                continue
            if MATCH_MODE == 'raw' and model_raw not in targets:
                continue
            if MATCH_MODE == 'trim-only' and (model_raw in targets or model_raw.strip() not in targets):
                continue
            model_key = model_raw if MATCH_MODE == 'raw' else model_raw.strip()
            token = row.get('fullLabel')
            assert isinstance(token, str) and token, 'matched record lacks fullLabel'
            key = digest(token.encode('utf-8'))
            reference = {
                'model_key': model_key, 'vehicleModel_raw': model_raw,
                'matching_mode': MATCH_MODE, 'uuid': row.get('uuid'),
                'recordNumber': row.get('recordNumber'),
                'source_file': Path(os.path.relpath(path, ROOT)).as_posix(),
                'source_page_sha256': digest(raw), 'page': page,
                'json_pointer': '/info/list/' + str(offset),
                'full_row_sha256': digest(json.dumps(row, **CANONICAL_ARGS).encode('utf-8')),
                'label_job_id': key, 'fullLabel': token,
                'testBasisStandard_raw': row.get('testBasisStandard'),
                'issueDate_raw': row.get('issueDate'), 'enableDate_raw': row.get('enableDate'),
                'createTime_raw': row.get('createTime'), 'updateTime_raw': row.get('updateTime'),
                'abandonTime_raw': row.get('abandonTime'),
                'is_new_library_only_model': model_key not in old_models,
                'row': row,
            }
            rows.append(reference)
            job = jobs.setdefault(key, {'label_job_id': key, 'fullLabel': token, 'record_refs': []})
            assert job['fullLabel'] == token, 'SHA collision'
            job['record_refs'].append({k: v for k, v in reference.items() if k != 'row'})
    assert len({r['full_row_sha256'] for r in rows}) == len(rows), 'full row duplicate unexpectedly in matched view'

    def priority(job):
        refs = job['record_refs']
        has_code6 = any(r['testBasisStandard_raw'] == '6' for r in refs)
        new_only = any(r['is_new_library_only_model'] for r in refs)
        before = any(isinstance(r['issueDate_raw'], str) and r['issueDate_raw'][:10] <= CUTOFF for r in refs)
        return (not has_code6, not new_only, not before, refs[0]['page'], refs[0]['json_pointer'])

    ordered = sorted(jobs.values(), key=priority)
    for number, job in enumerate(ordered, 1):
        job['priority_order'] = number
        job['download_url'] = BASE + '?' + urlencode({'m': job['fullLabel'], 'p': 1})
    with (ROOT / 'matched_record_sources.jsonl').open('w', encoding='utf-8') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    with (ROOT / 'label_download_queue.jsonl').open('w', encoding='utf-8') as stream:
        for job in ordered:
            stream.write(json.dumps(job, ensure_ascii=False) + '\n')
    summary = {
        'source_checkpoint_sha256': file_sha(SNAPSHOT / 'new_checkpoint.json'),
        'target_model_file_sha256': file_sha(TARGETS),
        'exact_matched_models': len({r['model_key'] for r in rows}),
        'exact_matched_records': len(rows), 'unique_public_label_refs': len(ordered),
        'raw_standard_codes': dict(Counter(str(r['testBasisStandard_raw']) for r in rows)),
        'queue_order': 'code6 first, then models absent from old exact hit set, then raw issueDate <= cutoff; never certification',
        'fullLabel_deduplication_preserves_all_record_variants': True,
        'matching_mode': MATCH_MODE,
        'candidate_only': MATCH_MODE != 'raw',
    }
    write_json(ROOT / 'queue_summary.json', summary)
    return ordered, rows, summary


def pdf_info(raw):
    assert raw.startswith(b'%PDF-'), 'response is not PDF magic bytes'
    document = fitz.open(stream=raw, filetype='pdf')
    assert not document.needs_pass and document.page_count > 0, 'PDF encrypted or empty'
    text = '\n\n'.join(page.get_text() for page in document)
    pages = document.page_count
    document.close()
    lines = [line.strip() for line in text.splitlines()]
    standard_lines = []
    for index, line in enumerate(lines):
        if re.search(r'GB\s*/?\s*T|18386|19753|试验标准|测定', line, re.I):
            standard_lines.append('\n'.join(lines[max(0, index - 1): min(len(lines), index + 3)]))
    return {'pages': pages, 'text': text, 'standard_contexts': list(dict.fromkeys(standard_lines)),
            'battery_energy_words_present': bool(re.search(r'电池.{0,6}(总能量|能量|容量)|电池组总能量', text))}


def accepted_cache(job):
    folder = ROOT / 'receipts'
    for path in sorted(folder.glob(job['label_job_id'] + '_attempt*_receipt.json')):
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if receipt.get('http_status') in [401, 403, 429] or receipt.get('stop_boundary'):
            return None, receipt
        response = ROOT / receipt.get('response_file', 'missing')
        if receipt.get('accepted') and receipt.get('http_status') == 200 and response.is_file():
            if file_sha(response) == receipt.get('sha256'):
                try:
                    parsed = pdf_info(response.read_bytes())
                except Exception:
                    continue
                return (receipt, parsed), None
    return None, None


def fetch(job, interval):
    cached, boundary = accepted_cache(job)
    if boundary:
        return None, boundary
    if cached:
        receipt, parsed = cached
        return {'receipt': receipt, 'parsed': parsed, 'cache_reused': True}, None
    prior = sorted((ROOT / 'receipts').glob(job['label_job_id'] + '_attempt*_receipt.json'))
    if len(prior) >= 3:
        return None, {'stop_boundary': 'three attempts exhausted', 'label_job_id': job['label_job_id']}
    for attempt in range(len(prior) + 1, 4):
        stem = job['label_job_id'] + f'_attempt{attempt:02d}'
        path = ROOT / 'responses' / (stem + '.pdf')
        rp = ROOT / 'receipts' / (stem + '_receipt.json')
        receipt = {
            'label_job_id': job['label_job_id'], 'fullLabel': job['fullLabel'],
            'attempt': attempt, 'method': 'GET', 'requested_url': job['download_url'],
            'observed_utc': timestamp(), 'tls_verified': True,
            'no_credentials_or_captcha_solution_submitted': True,
            'accepted': False, 'record_reference_count': len(job['record_refs']),
        }
        parsed = None
        try:
            request = Request(job['download_url'], method='GET')
            try:
                response = urlopen(request, timeout=45)
            except HTTPError as error:
                response = error
            raw = response.read()
            status = response.status
            if status != 200 or not raw.startswith(b'%PDF-'):
                path = path.with_suffix('.bin')
            path.write_bytes(raw)
            receipt.update(http_status=status, content_type=response.headers.get('Content-Type'),
                           final_url=response.geturl(), bytes=len(raw), sha256=digest(raw),
                           response_file=path.relative_to(ROOT).as_posix(), finished_utc=timestamp())
            if status in [401, 403, 429]:
                receipt['stop_boundary'] = 'HTTP access refusal or rate limit; no bypass'
            elif status == 200:
                try:
                    parsed = pdf_info(raw)
                    receipt['accepted'] = True
                    receipt['pdf_pages'] = parsed['pages']
                except Exception as error:
                    receipt['stop_boundary'] = 'HTTP200 invalid PDF: ' + str(error)
            elif status not in [500, 502, 503, 504]:
                receipt['stop_boundary'] = 'non-retryable HTTP response ' + str(status)
        except (URLError, TimeoutError, OSError) as error:
            receipt.update(error=type(error).__name__, error_detail=str(error), finished_utc=timestamp())
        write_json(rp, receipt)
        if receipt.get('accepted'):
            return {'receipt': receipt, 'parsed': parsed, 'cache_reused': False}, None
        if receipt.get('stop_boundary'):
            return None, receipt
        if attempt == 3:
            receipt['stop_boundary'] = 'transient attempts exhausted; retained all attempts'
            write_json(rp, receipt)
            return None, receipt
        time.sleep(max(interval, 2))


def refresh_manifest():
    entries = []
    for path in sorted(ROOT.rglob('*')):
        if path.is_file() and path.name != '文件_SHA256.csv' and '__pycache__' not in path.parts:
            entries.append({'file': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size, 'sha256': file_sha(path)})
    with (ROOT / '文件_SHA256.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['file', 'bytes', 'sha256'])
        writer.writeheader()
        writer.writerows(entries)


def write_status(state, rows, summary):
    write_json(ROOT / 'label_checkpoint.json', state)
    accepted = {}
    for path in (ROOT / 'extracted').glob('*.json'):
        row = json.loads(path.read_text(encoding='utf-8'))
        accepted[row['label_job_id']] = row
    csv_path = ROOT / '精确命中记录_标签原件与标准原句_只读旁表.csv'
    fields = ['model_key', 'vehicleModel_raw', 'matching_mode', 'uuid', 'recordNumber', 'page', 'json_pointer', 'source_file', 'source_page_sha256',
              'full_row_sha256', 'label_job_id', 'fullLabel', 'testBasisStandard_raw', 'issueDate_raw',
              'enableDate_raw', 'createTime_raw', 'updateTime_raw', 'abandonTime_raw', 'pdf_received',
              'pdf_file', 'pdf_sha256', 'pdf_bytes', 'pdf_pages', 'receipt_file', 'observed_utc',
              'full_text_file', 'full_text_sha256', 'standard_contexts', 'battery_energy_words_present',
              'configuration_identity_certified', 'historical_public_accessibility_certified',
              'same_cycle_comparability_certified', 'can_backfill_frozen_catalogue_parameters']
    with csv_path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = {k: row.get(k, '') for k in fields}
            data = accepted.get(row['label_job_id'])
            out['pdf_received'] = int(data is not None)
            if data:
                for key in ['pdf_file', 'pdf_sha256', 'pdf_bytes', 'pdf_pages', 'receipt_file',
                            'observed_utc', 'full_text_file', 'full_text_sha256', 'battery_energy_words_present']:
                    out[key] = data[key]
                out['standard_contexts'] = json.dumps(data['standard_contexts'], ensure_ascii=False)
            for key in ['configuration_identity_certified', 'historical_public_accessibility_certified',
                        'same_cycle_comparability_certified', 'can_backfill_frozen_catalogue_parameters']:
                out[key] = 0
            writer.writerow(out)
    received_rows = sum(r['label_job_id'] in accepted for r in rows)
    received_models = len({r['model_key'] for r in rows if r['label_job_id'] in accepted})
    status = {**summary, 'completed': state['completed'], 'accepted_unique_pdfs': len(accepted),
              'exact_records_with_pdf': received_rows, 'exact_models_with_pdf': received_models,
              'stop_reason': state['stop_reason'], 'updated_utc': timestamp(),
              'issueDate_semantics_certified': False, 'historical_public_accessibility_certified': False,
              'same_cycle_comparability_certified': False, 'frozen_core_science_modified': False}
    write_json(ROOT / 'summary.json', status)
    (ROOT / 'README.md').write_text(
        '# 新库标签官方原件归档\n\n' +
        ('原字符串严格匹配主队列。\n\n' if not summary['candidate_only'] else
         '仅去首尾空白新增候选，独立归档，不计入936条原字符串严格匹配主队列。\n\n') +
        f'固定2208型号清单本口径命中 {summary["exact_matched_models"]} 型号、{summary["exact_matched_records"]} 条全行记录；'
        f'按实际公开 fullLabel 标识去重后 {summary["unique_public_label_refs"]} 份标签，全部记录状态仍保留。\n\n'
        f'截至 {status["updated_utc"]}：实际HTTP200、SHA一致、PDF魔数和PyMuPDF验证通过 {len(accepted)} 份，'
        f'覆盖 {received_rows} 条记录、{received_models} 型号；完成标志 {state["completed"]}。'
        f'停止原因：{state["stop_reason"] or "无，采集中或已完成（以checkpoint为准）"}。\n\n'
        '来源页、JSON pointer、全行哈希和每次HTTP尝试均保留；同uuid的状态版本不合并。'
        '标签实际全文及标准所在原句逐PDF保存，不因代码5或6而泛化标准映射。'
        'issueDate、enableDate、createTime、abandonTime按原始字段保留；issueDate不等于原试验报告日期或历史公开可取得日期。\n\n'
        '本旁表不认证与免征目录的配置身份、冻结点同工况资格、低温试验报告或逐车税收资格；'
        '不以电耗乘续航回填电池总能量，不改变52张科学CSV及2208待核口径。\n\n'
        '正常匿名GET、TLS验证、单worker、请求间隔至少2秒；401/403/429及HTTP200非PDF立即停，'
        '仅网关5xx/超时最多共3次尝试。公开fullLabel是文档标识，不需要账户令牌。\n\n'
        '复跑：`python collect_matched_labels.py`。脚本只采用receipt与原件SHA一致且仍能解析的成功缓存，'
        '遇到已留存的访问拒绝不会继续请求。`--prepare-only`仅重建队列，不访问网络。\n', encoding='utf-8')
    for folder, description in [('responses', '每次实际响应原字节；成功为PDF，失败原文为bin，均不覆盖。'),
                                ('receipts', '每次正常匿名HTTP尝试的原观察时间、URL、状态、长度与SHA。'),
                                ('extracted', '每份PDF完整文字及标准原句；提取文件不代替官方PDF原件。')]:
        (ROOT / folder / 'README.md').write_text('# ' + folder + '\n\n' + description + '\n', encoding='utf-8')
    refresh_manifest()


def main():
    global ROOT, SNAPSHOT, TARGETS, OLD_MODELS, MATCH_MODE
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--interval', type=float, default=2)
    parser.add_argument('--source-root', type=Path, default=SNAPSHOT,
                        help='Folder containing new_checkpoint.json and its raw response paths')
    parser.add_argument('--output-root', type=Path, default=ROOT)
    parser.add_argument('--target-model-file', type=Path, default=TARGETS)
    parser.add_argument('--old-exact-model-file', type=Path, default=OLD_MODELS)
    parser.add_argument('--matching-mode', choices=['raw', 'trim-only'], default='raw',
                        help='trim-only is a separate candidate queue, excluded from strict raw matching')
    parser.add_argument('--stop-after-total', type=int,
                        help='Stage boundary: pause after this many accepted queue jobs; incomplete remains false')
    parser.add_argument('--max-new-jobs', type=int,
                        help='Stage boundary: limit newly downloaded successful jobs, excluding verified cached jobs')
    args = parser.parse_args()
    ROOT = args.output_root.resolve()
    SNAPSHOT = args.source_root.resolve()
    TARGETS = args.target_model_file.resolve()
    OLD_MODELS = args.old_exact_model_file.resolve()
    MATCH_MODE = args.matching_mode
    ROOT.mkdir(parents=True, exist_ok=True)
    assert args.interval >= 2
    assert args.stop_after_total is None or args.stop_after_total >= 0
    assert args.max_new_jobs is None or args.max_new_jobs >= 0
    for folder in ['responses', 'receipts', 'extracted']:
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    jobs, rows, summary = build_queue()
    state = {'started_utc': timestamp(), 'updated_utc': timestamp(), 'completed': False,
             'unique_label_jobs': len(jobs), 'jobs_validated': 0, 'accepted_pdfs': 0,
             'cache_reused': 0, 'newly_accepted_jobs_this_run': 0, 'stop_reason': '',
             'pause_kind': None, 'source_queue_sha256': file_sha(ROOT / 'label_download_queue.jsonl')}
    write_status(state, rows, summary)
    print(json.dumps({'queue_ready': summary}, ensure_ascii=False), flush=True)
    if args.prepare_only:
        return
    try:
        for position, job in enumerate(jobs, 1):
            if args.stop_after_total is not None and position > args.stop_after_total:
                state['stop_reason'] = f'planned_review_stage_boundary: accepted {position - 1} of {len(jobs)}; resume available'
                state['pause_kind'] = 'planned_review_stage_boundary'
                break
            if args.max_new_jobs is not None and state['newly_accepted_jobs_this_run'] >= args.max_new_jobs:
                cached, boundary = accepted_cache(job)
                if not cached:
                    state['stop_reason'] = 'planned_new_job_budget: resumable, not an access refusal'
                    state['pause_kind'] = 'planned_new_job_budget'
                    break
            handoff_marker = ROOT.parent.parent.parent / '.git/energy_handoff_requested'
            if handoff_marker.exists() and not accepted_cache(job)[0]:
                state['stop_reason'] = 'operator handoff to GitHub cloud worker; successful saved cache preserved'
                state['pause_kind'] = 'cloud_worker_handoff'
                break
            result, boundary = fetch(job, args.interval)
            if boundary:
                state['stop_reason'] = json.dumps(boundary, ensure_ascii=False)
                break
            receipt = result['receipt']
            parsed = result['parsed']
            text_path = ROOT / 'extracted' / (job['label_job_id'] + '.txt')
            text_path.write_text(parsed['text'], encoding='utf-8')
            receipt_path = 'receipts/' + job['label_job_id'] + f'_attempt{receipt["attempt"]:02d}_receipt.json'
            evidence = {'label_job_id': job['label_job_id'], 'fullLabel': job['fullLabel'],
                        'pdf_file': receipt['response_file'], 'pdf_sha256': receipt['sha256'],
                        'pdf_bytes': receipt['bytes'], 'pdf_pages': parsed['pages'],
                        'receipt_file': receipt_path, 'observed_utc': receipt['observed_utc'],
                        'full_text_file': text_path.relative_to(ROOT).as_posix(),
                        'full_text_sha256': file_sha(text_path),
                        'standard_contexts': parsed['standard_contexts'],
                        'battery_energy_words_present': parsed['battery_energy_words_present'],
                        'record_refs': job['record_refs']}
            write_json(ROOT / 'extracted' / (job['label_job_id'] + '.json'), evidence)
            state.update(jobs_validated=position, accepted_pdfs=position, updated_utc=timestamp())
            state['cache_reused'] += int(result['cache_reused'])
            state['newly_accepted_jobs_this_run'] += int(not result['cache_reused'])
            write_json(ROOT / 'label_checkpoint.json', state)
            print(json.dumps({'label': position, 'labels': len(jobs), 'model': job['record_refs'][0]['model_key'],
                              'pdf_sha256': receipt['sha256'], 'bytes': receipt['bytes'],
                              'cached': result['cache_reused']}, ensure_ascii=False), flush=True)
            if position % 20 == 0:
                write_status(state, rows, summary)
            if position < len(jobs) and not result['cache_reused']:
                time.sleep(args.interval)
        else:
            state['completed'] = True
    except KeyboardInterrupt:
        state['stop_reason'] = 'operator interruption; checkpoint resumable'
    except Exception as error:
        state['stop_reason'] = type(error).__name__ + ': ' + str(error)
    state['finished_utc'] = timestamp()
    state['updated_utc'] = state['finished_utc']
    write_status(state, rows, summary)
    print(json.dumps({'completed': state['completed'], 'accepted_pdfs': state['accepted_pdfs'],
                      'stop_reason': state['stop_reason']}, ensure_ascii=False), flush=True)
    sys.exit(0 if state['completed'] or state.get('pause_kind') in {'planned_review_stage_boundary', 'planned_new_job_budget'} else 1)


if __name__ == '__main__':
    main()
