#!/usr/bin/env python3
"""Verify the already-uploaded provider batch and reuse its original bytes.

This performs no network requests. Provider timestamps remain provider claims;
missing TLS/anonymous-request attestations are never filled in as true.
"""
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROVIDER = ROOT / 'deepseek_old_details_101_200'
DEST = ROOT / 'old_details'
QUEUE = ROOT / 'independent_old_review/4497记录_旧库精确命中固定来源键.jsonl'
SOURCE = ROOT.parent / 'energy_registry_20261009/public_energy_registry'
EXPECTED_QUEUE_SHA = '54edef6f8a0d0a43f4f790cb4e6493ef70242d016e961ba66bd6f51cbb72d5e9'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    assert sha(QUEUE) == EXPECTED_QUEUE_SHA
    queue = [json.loads(line) for line in QUEUE.read_text().splitlines()]
    assert len(queue) == 4497
    manifest = read(PROVIDER / 'delivery_manifest.json')
    for item in manifest['files']:
        path = PROVIDER / item['path']
        assert path.resolve().is_relative_to(PROVIDER.resolve())
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], item['path']
    assert len(manifest['files']) == manifest['file_count'] == 203
    checkpoint = read(PROVIDER / 'checkpoint.json')
    assert checkpoint['queue_sha256'] == EXPECTED_QUEUE_SHA
    assert checkpoint['accepted'] == 100 and checkpoint['attempts'] == 101
    planned = []
    for index in range(101, 201):
        source = queue[index - 1]
        raw_list = SOURCE / source['source_file']
        assert sha(raw_list) == source['source_sha256']
        offset = int(source['json_pointer'].split('/')[-1])
        assert read(raw_list)['info']['list'][offset] == source['raw_record']
        stem = f"detail{index:05d}_{source['stable_id_raw']}"
        matches = []
        for receipt_file in sorted((PROVIDER / 'raw').glob(stem + '_attempt*_receipt.json')):
            original = read(receipt_file)
            assert original['record_index_1based'] == index
            assert original['applyId'] == source['stable_id_raw']
            assert original['model_key'] == source['model_key']
            for key in ['source_file', 'source_sha256']:
                assert original[key] == source[key]
            assert original['source_json_pointer'] == source['json_pointer']
            response_file = receipt_file.with_name(receipt_file.name.replace('_receipt.json', '_response.json'))
            if original.get('http_status') != 200:
                continue
            assert response_file.stat().st_size == original['bytes']
            assert sha(response_file) == original['sha256']
            body = read(response_file)
            assert body['result'] == 1 and body['info']['vehicleNumber'] == source['model_key']
            assert body['info'].get('applyId') in [None, '', source['stable_id_raw']]
            assert body['info'].get('uniqId') in [None, '', source['record_number_raw']]
            matches.append((receipt_file, response_file, original))
        assert len(matches) == 1, (index, len(matches))
        receipt_file, response_file, original = matches[0]
        normalized = {
            'method': 'POST', 'requested_url': checkpoint['endpoint'],
            'request_json': {'applyId': source['stable_id_raw']},
            'input_record_key': source['record_key'], 'source_occurrence': source['source_occurrence'],
            'expected_model_raw': source['model_key'], 'attempt': original['attempt'],
            'observed_utc': original['observed_utc'],
            'http_status': original['http_status'], 'bytes': original['bytes'], 'sha256': original['sha256'],
            'file': 'raw/' + response_file.name, 'accepted': True,
            'tls_verified': None, 'anonymous_request_no_credentials_or_captcha_solution': None,
            'imported_external_delivery': True,
            'provider_original_receipt_file': '../' + receipt_file.relative_to(ROOT).as_posix(),
            'provider_original_receipt_sha256': sha(receipt_file),
            'provider_original_response_file': '../' + response_file.relative_to(ROOT).as_posix(),
            'provider_original_response_sha256': sha(response_file),
            'source_fixed_list_file': source['source_file'],
            'source_fixed_list_sha256': source['source_sha256'],
            'source_fixed_json_pointer': source['json_pointer'],
            'transport_limit': 'Provider archive verified locally; TLS verification and anonymous-request claims were not attested in original receipts.',
            'normalized_receipt_fields_are_archive_metadata': True,
        }
        planned.append((receipt_file, response_file, normalized))
    # All rows are checked before writing anything into the resumable cache.
    for receipt_file, response_file, normalized in planned:
        dest_response = DEST / normalized['file']
        if dest_response.exists():
            assert sha(dest_response) == normalized['sha256']
        else:
            shutil.copyfile(response_file, dest_response)
        dest_receipt = DEST / 'raw' / receipt_file.name
        if dest_receipt.exists():
            assert read(dest_receipt) == normalized
        else:
            write(dest_receipt, normalized)
    result = {
        'reviewed_utc': datetime.now(timezone.utc).isoformat(),
        'provider_directory': PROVIDER.relative_to(ROOT).as_posix(),
        'provider_manifest_sha256': sha(PROVIDER / 'delivery_manifest.json'),
        'provider_payload_files_verified': 203,
        'queue_sha256': sha(QUEUE), 'queue_range_1based': [101, 200],
        'accepted_original_responses': 100,
        'provider_attempts_retained_in_original_archive': 101,
        'all_fixed_source_pointers_models_and_response_hashes_verified': True,
        'response_bytes_changed': False, 'provider_original_receipts_changed': False,
        'provider_original_observation_times_preserved': True,
        'tls_attestation_unavailable_records': 100,
        'anonymous_request_attestation_unavailable_records': 100,
        'network_requests_performed_by_import': 0,
        'scientific_csv_changed': False, 'frozen_cycle_gaps_closed': 0,
        'verification': 'PASS',
    }
    write(ROOT / 'provider_import_review.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
