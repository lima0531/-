#!/usr/bin/env python3
"""Verify archived observations and publish a raw-field-only compact table."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    records = [json.loads(line) for line in (ROOT / 'details_readonly.jsonl').read_text().splitlines()]
    checkpoint = json.loads((ROOT / 'checkpoint.json').read_bytes())
    queue = [json.loads(line) for line in (ROOT / 'remaining_details_queue.jsonl').read_text().splitlines()]
    source_raw = (ROOT.parent / 'independent_old_review/4497记录_旧库精确命中固定来源键.jsonl').read_bytes()
    source_queue = [json.loads(line) for line in source_raw.splitlines()]
    source_by_id = {row['stable_id_raw']: row for row in source_queue}
    assert len(source_queue) == len(source_by_id) == 4497
    assert hashlib.sha256(source_raw).hexdigest() == checkpoint['input']['input_sha256']
    ids = set()
    raw_bytes = 0
    for row in records:
        raw = (ROOT / row['detail_file']).read_bytes()
        receipt = json.loads((ROOT / row['receipt_file']).read_bytes())
        assert hashlib.sha256(raw).hexdigest() == row['detail_sha256'] == receipt['sha256']
        assert len(raw) == receipt['bytes']
        response = json.loads(raw)
        assert response == row['detail_raw']
        assert receipt['http_status'] == 200 and response['result'] == 1
        assert receipt['request_json'] == {'applyId': row['stable_id_raw']}
        assert response['info']['vehicleNumber'] == row['model_key']
        assert row['source_fixed_list_record'] == source_by_id[row['stable_id_raw']]
        assert row['stable_id_raw'] not in ids
        ids.add(row['stable_id_raw'])
        raw_bytes += len(raw)
    remaining_ids = {row['stable_id_raw'] for row in queue}
    assert len(remaining_ids) == len(queue)
    assert not ids & remaining_ids
    assert ids | remaining_ids == set(source_by_id)
    assert all(row == source_by_id[row['stable_id_raw']] for row in queue)
    assert len(records) + len(queue) == 4497
    assert checkpoint['accepted_records'] == len(records)
    assert checkpoint['remaining_fixed_queue_records'] == len(queue)
    requests = [json.loads(line) for line in (ROOT / 'requests.jsonl').read_text().splitlines()]
    standards = Counter(row['detail_raw']['info'].get('testBasisStandard') for row in records)
    literal_counts = Counter()
    source_cycles = Counter()
    for row in records:
        for literal in {item['literal'] for item in row['standard_literals_with_paths']}:
            literal_counts[literal] += 1
        for item in row['source_fixed_list_record']['raw_record'].get('workConditionVos', []):
            source_cycles[item.get('workConditionType')] += 1
    summary = {
        'reviewed_utc': datetime.now(timezone.utc).isoformat(),
        'fixed_queue_records': 4497,
        'fixed_queue_input_sha256': hashlib.sha256(source_raw).hexdigest(),
        'accepted_detail_records': len(records),
        'accepted_detail_models': len({row['model_key'] for row in records}),
        'remaining_automatic_queue_records': len(queue),
        'accepted_original_response_bytes': raw_bytes,
        'actual_network_attempts_total': len(requests),
        'http_status_counts_all_attempts': dict(Counter(str(row.get('http_status')) for row in requests)),
        'network_error_counts_all_attempts': dict(Counter(row.get('network_error') for row in requests if row.get('network_error'))),
        'testBasisStandard_raw_values_counts': dict(standards),
        'document_standard_literals_record_counts': dict(literal_counts),
        'source_workConditionType_raw_values_counts': dict(source_cycles),
        'applyId_nonempty_response_echo_records': sum(bool(row['detail_raw']['info'].get('applyId')) for row in records),
        'uniqId_nonempty_response_echo_records': sum(bool(row['detail_raw']['info'].get('uniqId')) for row in records),
        'list_detail_literal_difference_records': sum(bool(row['fixed_list_vs_later_detail_literal_differences']) for row in records),
        'source_and_later_detail_temporal_boundary_retained': True,
        'standard_to_cycle_mapping_performed': False,
        'historical_frozen_2208_gap_closed': 0,
        'historical_frozen_2208_gap_remaining': 2208,
        'configuration_identity_certified': False,
        'normal_planned_batch_pause': checkpoint['normal_planned_batch_pause'],
        'verification': 'PASS',
    }
    (ROOT / 'archive_review_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    columns = ['record_key', 'applyId_raw', 'model_raw', 'source_publicTime_raw',
               'testBasisStandard_raw', 'document_standard_literals_with_paths',
               'source_workConditionVos_raw', 'detail_workConditionType_raw', 'detail_otherInfo_raw',
               'vehicleQuality_raw', 'maximumDesignMass_raw', 'peakPower_raw', 'runingRange_raw',
               'powerConsumption_raw', 'detail_date_fields_raw',
               'list_detail_literal_differences', 'detail_file', 'detail_sha256', 'receipt_file', 'observed_utc']
    with (ROOT / '旧库已取详情_字面标准与工况_只读旁表.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in records:
            info = row['detail_raw']['info']
            value = {
                'record_key': row['record_key'], 'applyId_raw': row['stable_id_raw'], 'model_raw': row['model_key'],
                'source_publicTime_raw': row['source_publicTime_raw'],
                'testBasisStandard_raw': info.get('testBasisStandard'),
                'document_standard_literals_with_paths': json.dumps(row['standard_literals_with_paths'], ensure_ascii=False),
                'source_workConditionVos_raw': json.dumps(row['source_fixed_list_record']['raw_record'].get('workConditionVos'), ensure_ascii=False),
                'detail_workConditionType_raw': info.get('workConditionType'),
                'detail_otherInfo_raw': info.get('otherInfo'),
                'detail_date_fields_raw': json.dumps(row['detail_date_fields_raw'], ensure_ascii=False),
                'list_detail_literal_differences': json.dumps(row['fixed_list_vs_later_detail_literal_differences'], ensure_ascii=False),
                'detail_file': row['detail_file'], 'detail_sha256': row['detail_sha256'],
                'receipt_file': row['receipt_file'], 'observed_utc': row['observed_utc'],
            }
            for name in ('vehicleQuality', 'maximumDesignMass', 'peakPower', 'runingRange', 'powerConsumption'):
                value[name + '_raw'] = info.get(name)
            writer.writerow(value)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
