#!/usr/bin/env python3
"""Resumable normal anonymous old-library detail evidence collection.

No source-table updates; this directory contains a later observed evidence layer.
--prepare performs only local input validation and writes the fixed queue.
"""
import argparse
import csv
import hashlib
from http.client import HTTPException
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
INPUT = ROOT.parent / 'independent_old_review/4497记录_旧库精确命中固定来源键.jsonl'
ENDPOINT = 'https://yhgscx.miit.gov.cn/fuel-consumption-center/fuel-consumption-center/fcSearchCtr/queryDetail'
TRANSIENT_HTTP = {500, 502, 503, 504}
ACCESS_HTTP = {401, 403, 429}
STANDARD_RE = re.compile(r'GB\s*[/／]\s*T\s*\d+(?:\.\d+)?\s*[-—–－]\s*\d{4}')
GATE_RE = re.compile(r'captcha|verifyCode|验证码|滑块|人机验证|访问频繁', re.I)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def load_queue():
    raw = INPUT.read_bytes()
    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    assert len(records) == 4497, 'fixed_input_count_changed'
    ids = [r['stable_id_raw'] for r in records]
    assert len(ids) == len(set(ids)), 'duplicate_input_applyId'
    for row in records:
        assert row['library'] == 'old'
        assert row['raw_record']['applyId'] == row['stable_id_raw']
        assert row['raw_record']['vehicleNumber'] == row['model_key']
        assert re.fullmatch('[0-9a-f]{32}', row['stable_id_raw']), 'unexpected_applyId_format'
    state = {'input_file': INPUT.relative_to(ROOT.parent).as_posix(),
             'input_bytes': len(raw), 'input_sha256': digest(raw),
             'records': len(records), 'models': len({r['model_key'] for r in records}),
             'prepared_utc': now(), 'network_requests_performed_by_prepare': 0}
    write_json(ROOT / 'queue_manifest.json', state)
    return records, state


def leaves(value, pointer=''):
    if isinstance(value, dict):
        for key, child in value.items():
            token = str(key).replace('~', '~0').replace('/', '~1')
            yield from leaves(child, pointer + '/' + token)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, pointer + '/' + str(index))
    else:
        yield pointer, value


def validate_response(receipt, raw, source):
    checks = {'raw_sha256_matches_receipt': digest(raw) == receipt.get('sha256'),
              'raw_bytes_match_receipt': len(raw) == receipt.get('bytes'),
              'http_200': receipt.get('http_status') == 200,
              'exact_request_applyId': receipt.get('request_json') == {'applyId': source['stable_id_raw']}}
    if not all(checks.values()):
        return None, checks, 'transport_or_cache_integrity'
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None, checks, 'non_json_response'
    if not isinstance(data, dict):
        return data, checks, 'non_object_response'
    checks['business_result_1'] = data.get('result') == 1
    info = data.get('info')
    checks['detail_is_object'] = isinstance(info, dict)
    if not checks['business_result_1'] or not checks['detail_is_object']:
        return data, checks, 'business_or_schema_boundary'
    checks['exact_model_echo'] = info.get('vehicleNumber') == source['model_key']
    # The observed endpoint may intentionally return null applyId/uniqId.
    # That absence is recorded rather than fabricated into an identity echo.
    echoed_id = info.get('applyId')
    checks['applyId_echo_if_present_agrees'] = echoed_id in (None, '') or echoed_id == source['stable_id_raw']
    checks['applyId_nonempty_echo_present'] = echoed_id not in (None, '')
    echoed_number = info.get('uniqId')
    expected_number = source.get('record_number_raw')
    checks['record_number_echo_if_present_agrees'] = echoed_number in (None, '') or not expected_number or echoed_number == expected_number
    checks['record_number_nonempty_echo_present'] = echoed_number not in (None, '')
    semantic_keys = ['business_result_1', 'detail_is_object', 'exact_model_echo',
                     'applyId_echo_if_present_agrees', 'record_number_echo_if_present_agrees']
    if not all(checks[key] for key in semantic_keys):
        return data, checks, 'response_identity_or_schema_mismatch'
    return data, checks, None


def gated(receipt, raw, data):
    if receipt.get('http_status') in ACCESS_HTTP:
        return True
    if isinstance(data, dict) and data.get('result') != 1:
        if GATE_RE.search(str(data.get('msg', ''))):
            return True
    if raw and (not isinstance(data, dict) or data.get('result') != 1) and GATE_RE.search(raw.decode('utf-8', errors='replace')):
        return True
    return False


def accepted_cache(source, stem):
    previous = []
    for receipt_file in sorted((ROOT / 'raw').glob(stem + '_attempt*_receipt.json')):
        receipt = json.loads(receipt_file.read_bytes())
        previous.append((receipt_file, receipt))
        if receipt.get('request_json') != {'applyId': source['stable_id_raw']}:
            raise RuntimeError('cached_request_identity_mismatch')
        response_path = ROOT / receipt.get('file', 'missing')
        raw = response_path.read_bytes() if response_path.is_file() else None
        if raw is not None:
            data, checks, error = validate_response(receipt, raw, source)
            if not error:
                return (receipt_file, receipt, data, checks), previous
            if gated(receipt, raw, data):
                raise RuntimeError('cached_access_boundary_do_not_retry')
        if receipt.get('http_status') in ACCESS_HTTP:
            raise RuntimeError('cached_access_boundary_do_not_retry')
    previous.sort(key=lambda pair: pair[1]['attempt'])
    return None, previous


def fetch(source, index, args, limiter):
    stem = f'detail{index:05d}_{source["stable_id_raw"]}'
    cached, previous = accepted_cache(source, stem)
    if cached:
        return cached, 0
    if previous:
        last = previous[-1][1]
        if last.get('http_status') not in TRANSIENT_HTTP and not last.get('network_error'):
            raise RuntimeError('cached_nontransient_failure_do_not_retry')
        if len(previous) >= 2:
            raise RuntimeError('cached_bounded_retries_exhausted')
    used = 0
    for attempt in range(len(previous) + 1, 3):
        if limiter['last_request_monotonic'] is not None:
            remaining = args.interval - (time.monotonic() - limiter['last_request_monotonic'])
            if remaining > 0:
                time.sleep(remaining)
        if attempt > 1:
            time.sleep(4)
        body = {'applyId': source['stable_id_raw']}
        receipt = {'method': 'POST', 'requested_url': ENDPOINT, 'request_json': body,
                   'invocation_id': limiter['invocation_id'],
                   'input_record_key': source['record_key'], 'source_occurrence': source['source_occurrence'],
                   'expected_model_raw': source['model_key'], 'attempt': attempt,
                   'observed_utc': now(), 'tls_verified': True,
                   'anonymous_request_no_credentials_or_captcha_solution': True,
                   'source_fixed_list_file': source['source_file'],
                   'source_fixed_list_sha256': source['source_sha256'],
                   'source_fixed_json_pointer': source['json_pointer']}
        response_file = ROOT / 'raw' / f'{stem}_attempt{attempt:02d}_response.json'
        receipt_file = ROOT / 'raw' / f'{stem}_attempt{attempt:02d}_receipt.json'
        raw = None
        data = None
        response = None
        limiter['last_request_monotonic'] = time.monotonic()
        limiter['requests_this_invocation'] += 1
        try:
            request = Request(ENDPOINT, data=json.dumps(body).encode(),
                              headers={'Content-Type': 'application/json'}, method='POST')
            try:
                response = urlopen(request, timeout=args.timeout)
            except HTTPError as error:
                response = error
            receipt.update(http_status=response.status, final_url=response.geturl(),
                           content_type=response.headers.get('Content-Type'))
            raw = response.read()
            response_file.write_bytes(raw)
            receipt.update(file=response_file.relative_to(ROOT).as_posix(),
                           bytes=len(raw), sha256=digest(raw))
            response.close()
            data, checks, error = validate_response(receipt, raw, source)
            receipt['validation_checks'] = checks
            receipt['semantic_validation_error'] = error
            receipt['accepted'] = error is None
        except (URLError, TimeoutError, OSError, HTTPException) as error:
            receipt.update(network_error=type(error).__name__, error_detail=str(error), accepted=False)
            partial = getattr(error, 'partial', None)
            if isinstance(partial, bytes):
                response_file.write_bytes(partial)
                receipt.update(file=response_file.relative_to(ROOT).as_posix(), bytes=len(partial),
                               sha256=digest(partial), response_body_is_partial=True)
        finally:
            if response is not None:
                response.close()
        receipt['finished_utc'] = now()
        write_json(receipt_file, receipt)
        with (ROOT / 'requests.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + '\n')
        used += 1
        if receipt['accepted']:
            return (receipt_file, receipt, data, receipt['validation_checks']), used
        if gated(receipt, raw, data):
            raise RuntimeError('access_or_captcha_boundary_do_not_retry')
        if receipt.get('http_status') not in TRANSIENT_HTTP and not receipt.get('network_error'):
            raise RuntimeError(receipt.get('semantic_validation_error', 'nontransient_boundary'))
        if attempt >= 2:
            raise RuntimeError('bounded_transient_retries_exhausted')
    raise RuntimeError('bounded_attempts_exhausted')


def evidence(source, accepted):
    receipt_file, receipt, data, checks = accepted
    info = data['info']
    standard_literals = []
    standard_fields_raw = []
    cycle_raw = []
    dates_raw = []
    configuration_raw = []
    for pointer, value in leaves(info, '/info'):
        key = pointer.rsplit('/', 1)[-1].lower()
        if 'standard' in key:
            standard_fields_raw.append({'json_pointer': pointer, 'value_raw': value})
        if isinstance(value, str):
            for match in STANDARD_RE.finditer(value):
                standard_literals.append({'json_pointer': pointer, 'literal': match.group(0), 'source_value_raw': value})
        if any(word in key for word in ('workcondition', 'otherinfo')):
            cycle_raw.append({'json_pointer': pointer, 'value_raw': value})
        if any(word in key for word in ('date', 'time')):
            dates_raw.append({'json_pointer': pointer, 'value_raw': value})
        if key in {'vehiclequality', 'maximumdesignmass', 'peakpower', 'ratedpower', 'enginenumber',
                   'drivetype', 'transmissiontype', 'fueltype', 'vehicletype', 'reporttype',
                   'vehicleNumber'.lower(), 'oversrasname', 'runingrange', 'pureelectricruningrange',
                   'powerconsumption', 'comprehensiveconditionspowerconsumption'}:
            configuration_raw.append({'json_pointer': pointer, 'value_raw': value})
    source_cycles = [{'json_pointer': '/raw_record/' + pointer.lstrip('/'), 'value_raw': value}
                     for pointer, value in leaves(source['raw_record'])
                     if 'workcondition' in pointer.lower()]
    comparisons = []
    for field in ('vehicleNumber', 'peakPower', 'runingRange', 'powerConsumption', 'reportType'):
        if field in source['raw_record'] and field in info:
            left, right = source['raw_record'][field], info[field]
            if left is not None and right is not None and left != right:
                comparisons.append({'field': field, 'fixed_list_value_raw': left, 'later_detail_value_raw': right,
                                    'interpretation': 'literal_difference_between_observations; configuration/version linkage not certified'})
    return {'record_key': source['record_key'], 'stable_id_raw': source['stable_id_raw'],
            'model_key': source['model_key'], 'source_fixed_list_record': source,
            'detail_file': receipt['file'], 'detail_sha256': receipt['sha256'],
            'receipt_file': receipt_file.relative_to(ROOT).as_posix(),
            'observed_utc': receipt['observed_utc'], 'validation_checks': checks,
            'detail_raw': data, 'standard_literals_with_paths': standard_literals,
            'standard_fields_raw': standard_fields_raw,
            'work_condition_or_explanation_fields_raw': cycle_raw,
            'source_work_condition_fields_raw': source_cycles,
            'detail_date_fields_raw': dates_raw,
            'source_publicTime_raw': source['raw_record'].get('publicTime'),
            'configuration_fields_raw': configuration_raw,
            'fixed_list_vs_later_detail_literal_differences': comparisons,
            'historical_frozen_cycle_gap_closed': False,
            'configuration_identity_certified': False,
            'standard_literal_is_not_automatic_cycle_mapping': True,
            'endpoint_identity_echo_limit': 'Null applyId/uniqId, if returned, is explicitly recorded; request id plus exact model echo links this later endpoint observation, not a configuration certificate.'}


def summarize(outputs, queue, queue_meta, state):
    with (ROOT / 'details_readonly.jsonl').open('w', encoding='utf-8') as handle:
        for row in outputs:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    conflicts = [dict(record_key=row['record_key'], model_key=row['model_key'],
                      differences=row['fixed_list_vs_later_detail_literal_differences'])
                 for row in outputs if row['fixed_list_vs_later_detail_literal_differences']]
    write_json(ROOT / 'list_detail_literal_differences.json', conflicts)
    model_versions = {}
    for row in outputs:
        info = row['detail_raw']['info']
        signature = {key: info.get(key) for key in ('testBasisStandard', 'vehicleQuality', 'maximumDesignMass',
                     'peakPower', 'runingRange', 'powerConsumption', 'otherInfo')}
        serialized = json.dumps(signature, ensure_ascii=False, sort_keys=True)
        versions = model_versions.setdefault(row['model_key'], {})
        version = versions.setdefault(serialized, {'fields_raw': signature, 'record_keys': []})
        version['record_keys'].append(row['record_key'])
    variation = [{'model_key': model, 'versions': list(versions.values()),
                  'interpretation': 'different literal fields across records; not proof of a contradiction or configuration equivalence'}
                 for model, versions in sorted(model_versions.items()) if len(versions) > 1]
    write_json(ROOT / 'model_detail_version_variation.json', variation)
    accepted_ids = {row['stable_id_raw'] for row in outputs}
    remaining = [row for row in queue if row['stable_id_raw'] not in accepted_ids]
    with (ROOT / 'remaining_details_queue.jsonl').open('w', encoding='utf-8') as handle:
        for row in remaining:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
    with (ROOT / 'remaining_details_queue.csv').open('w', encoding='utf-8', newline='') as handle:
        columns = ['record_key', 'applyId_raw', 'model_raw', 'source_occurrence', 'source_file',
                   'source_sha256', 'source_json_pointer', 'source_publicTime_raw', 'request_json']
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in remaining:
            writer.writerow(dict(record_key=row['record_key'], applyId_raw=row['stable_id_raw'],
                                 model_raw=row['model_key'], source_occurrence=row['source_occurrence'],
                                 source_file=row['source_file'], source_sha256=row['source_sha256'],
                                 source_json_pointer=row['json_pointer'],
                                 source_publicTime_raw=row['raw_record'].get('publicTime'),
                                 request_json=json.dumps({'applyId': row['stable_id_raw']}, ensure_ascii=False)))
    state.update(accepted_records=len(outputs), accepted_models=len({r['model_key'] for r in outputs}),
                 standard_literal_records=sum(bool(r['standard_literals_with_paths']) for r in outputs),
                 applyId_nonempty_echo_records=sum(r['validation_checks']['applyId_nonempty_echo_present'] for r in outputs),
                 list_detail_literal_difference_records=len(conflicts),
                 observed_multi_version_models=len(variation),
                 core_2208_frozen_cycle_gap_remaining=2208,
                 entire_fixed_queue_complete=len(outputs) == len(queue),
                 remaining_fixed_queue_records=len(queue) - len(outputs),
                 input=queue_meta, updated_utc=now())
    write_json(ROOT / 'checkpoint.json', state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true', help='Local-only queue validation; performs no network')
    parser.add_argument('--limit', type=int, default=10, help='Absolute first-N queue budget; 0 means all 4497')
    parser.add_argument('--interval', type=float, default=2.0)
    parser.add_argument('--timeout', type=float, default=45.0)
    args = parser.parse_args()
    assert args.interval >= 2 and args.timeout > 0 and args.limit >= 0
    checkpoint_path = ROOT / 'checkpoint.json'
    if not args.prepare and args.limit and checkpoint_path.is_file():
        previous_checkpoint = json.loads(checkpoint_path.read_bytes())
        if args.limit < previous_checkpoint.get('accepted_records', 0):
            parser.error('Requested absolute budget is below already accepted progress; choose a larger --limit or --limit 0. Existing evidence is preserved; no network request made.')
    (ROOT / 'raw').mkdir(exist_ok=True)
    queue, queue_meta = load_queue()
    if args.prepare:
        print(json.dumps(queue_meta, ensure_ascii=False), flush=True)
        return
    selected = queue[:args.limit] if args.limit else queue
    state = {'started_utc': now(), 'endpoint': ENDPOINT, 'selected_record_budget': len(selected),
             'requests_this_invocation': 0, 'single_worker': True, 'interval_seconds': args.interval,
             'max_attempts_per_record': 2, 'completed_selected_budget': False, 'stop_reason': '',
             'read_only_auxiliary_evidence': True,
             'snapshot_boundary': 'Fixed list observed previously; each later detail has its own observed timestamp. No atomic or historical frozen snapshot claim.'}
    limiter = {'last_request_monotonic': None, 'invocation_id': state['started_utc'],
               'requests_this_invocation': 0}
    outputs = []
    try:
        for index, source in enumerate(selected, start=1):
            accepted, requests_used = fetch(source, index, args, limiter)
            state['requests_this_invocation'] = limiter['requests_this_invocation']
            outputs.append(evidence(source, accepted))
            if len(outputs) % 10 == 0 or len(outputs) == len(selected):
                summarize(outputs, queue, queue_meta, state)
                print(json.dumps({'accepted': len(outputs), 'budget': len(selected),
                                  'requests_this_invocation': state['requests_this_invocation']}, ensure_ascii=False), flush=True)
        state['completed_selected_budget'] = True
    except Exception as error:
        state['stop_reason'] = str(error)
        print(json.dumps({'stopped': state['stop_reason'], 'accepted': len(outputs)}, ensure_ascii=False), flush=True)
    state['finished_utc'] = now()
    state['requests_this_invocation'] = limiter['requests_this_invocation']
    state['normal_planned_batch_pause'] = state['completed_selected_budget'] and len(outputs) < len(queue)
    state['pause_reason'] = 'planned_batch_budget_reached' if state['normal_planned_batch_pause'] else None
    summarize(outputs, queue, queue_meta, state)
    raise SystemExit(0 if state['completed_selected_budget'] else 1)


if __name__ == '__main__':
    main()
