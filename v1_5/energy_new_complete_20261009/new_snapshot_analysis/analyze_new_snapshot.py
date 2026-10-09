#!/usr/bin/env python3
"""Offline audit of the complete saved public new energy-registry view."""
import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def js(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def read_json(path):
    return json.loads(path.read_bytes())


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path, rows):
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(js(row) + '\n')


def normalized(value):
    # Deliberately does not change case, punctuation, or non-whitespace formats.
    return ''.join(char for char in unicodedata.normalize('NFKC', value) if not char.isspace())


def distribution(records, field):
    return dict(sorted(Counter(js(row['raw_record'].get(field)) for row in records).items()))


def date_profile(records, field, cutoff):
    valid = []
    invalid = []
    for row in records:
        value = row['raw_record'].get(field)
        if value is None or value == '':
            continue
        try:
            parsed = date.fromisoformat(value)
        except (ValueError, TypeError):
            invalid.append({'record_key': row['record_key'], 'value_raw': value})
        else:
            valid.append((row, parsed))
    return {
        'field': field, 'valid_date_rows': len(valid),
        'blank_or_null_rows': len(records) - len(valid) - len(invalid),
        'invalid_nonblank_rows': invalid,
        'minimum_raw_date': min((value.isoformat() for _, value in valid), default=None),
        'maximum_raw_date': max((value.isoformat() for _, value in valid), default=None),
        'rows_before_cutoff_date': sum(value < cutoff for _, value in valid),
        'rows_on_cutoff_date': sum(value == cutoff for _, value in valid),
        'rows_on_or_before_cutoff_date': sum(value <= cutoff for _, value in valid),
        'models_with_any_date_before_cutoff': len({row['model_key'] for row, value in valid if value < cutoff}),
        'public_availability_or_tax_configuration_certified': False,
    }


def main():
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument('--audit-root', type=Path, default=Path('/workspace/purchase_tax_audit'))
    root_args, _ = base_parser.parse_known_args()
    audit = root_args.audit_root
    parser = argparse.ArgumentParser(description=__doc__, parents=[base_parser])
    parser.add_argument('--source', type=Path, default=audit / 'round11/public_new_snapshot')
    parser.add_argument('--targets', type=Path, default=audit / 'round9/public_cycle/2208型号_整篇工况补证结果_只读旁表.csv')
    parser.add_argument('--old-review', type=Path, default=audit / 'round11/independent_old_review')
    parser.add_argument('--previous-table', type=Path, default=audit / 'round10/public_energy_registry/2208型号_两库完整视图精确匹配.csv')
    parser.add_argument('--user-manifest', type=Path, default=audit / 'round11/user_submitted/delivery_manifest_用户原文.json')
    parser.add_argument('--cutoff-date', type=date.fromisoformat, default=date(2023, 12, 10))
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    cp_path = args.source / 'new_checkpoint.json'
    checkpoint = read_json(cp_path)
    if checkpoint.get('completed') is not True:
        raise SystemExit(f"Waiting for complete checkpoint: {checkpoint.get('pages_validated')}/{checkpoint.get('reported_pages')} pages; no partial analysis emitted.")
    assert checkpoint['library'] == 'new' and checkpoint['filters'] == {'energyType': '8'}
    assert checkpoint['rows'] == checkpoint['reported_total']
    assert checkpoint['pages_validated'] == checkpoint['reported_pages'] == len(checkpoint['source_page_files'])
    assert sha(args.targets) == 'a438f95dd4e0f3cf1ada1d27bf53716896d13fceaad2b0e6f424750a84c20d21'
    target_rows = read_csv(args.targets)
    targets = {row['model_key'] for row in target_rows}
    assert len(target_rows) == len(targets) == 2208 and 'JX6550T-M5BEV' not in targets
    normalized_targets = defaultdict(set)
    for model in targets:
        normalized_targets[normalized(model)].add(model)
    normalized_collisions = {key: sorted(values) for key, values in normalized_targets.items() if len(values) > 1}
    old_models_path = args.old_review / '1233型号_旧库精确命中集合.csv'
    old_records_path = args.old_review / '4497记录_旧库精确命中固定来源键.jsonl'
    old_review = read_json(args.old_review / 'review.json')
    assert old_review['status'] == 'PASS'
    old_manifest = {row['file']: row for row in read_csv(args.old_review / '文件_SHA256.csv')}
    for path in [old_models_path, old_records_path]:
        expected = old_manifest[path.name]
        assert sha(path) == expected['sha256'] and path.stat().st_size == int(expected['bytes'])
    old_rows = read_csv(old_models_path)
    old_by_model = {row['model_key']: row for row in old_rows}
    old_models = set(old_by_model)
    assert len(old_rows) == len(old_models) == 1233 and old_models <= targets
    with old_records_path.open(encoding='utf-8') as handle:
        old_records = [json.loads(line) for line in handle]
    assert len(old_records) == 4497
    previous_rows = read_csv(args.previous_table)
    assert len(previous_rows) == 2208
    previous_models = {row['model_key'] for row in previous_rows if int(row['new_raw_rows']) or int(row['old_raw_rows'])}
    assert len(previous_models) == 1234 and previous_models <= targets

    user_manifest = read_json(args.user_manifest)
    user_pages = {}
    for entry in user_manifest['files']:
        match = re.fullmatch(r'raw/responses/new_page(\d{4})\.json', entry['path'])
        if match:
            page = int(match.group(1))
            assert page not in user_pages
            user_pages[page] = entry
    assert len(user_pages) == 53
    all_records = []
    exact_records = []
    by_exact = defaultdict(list)
    by_normalized = defaultdict(list)
    normalized_candidates = []
    by_uuid = defaultdict(list)
    pages = []
    category_conflicts = []
    all_field_names = set()
    for page, rel in enumerate(checkpoint['source_page_files'], 1):
        source_path = args.source / rel
        receipt_path = source_path.with_name(source_path.name.replace('_response.json', '_receipt.json'))
        receipt = read_json(receipt_path)
        assert receipt['http_status'] == 200 and receipt['tls_verified'] is True
        assert receipt['file'] == rel and receipt['bytes'] == source_path.stat().st_size and receipt['sha256'] == sha(source_path)
        assert receipt['request_json'] == {'currentPage': page, 'pageSize': 200, 'energyType': '8'}
        assert receipt['requested_url'].endswith('/fcSearchCtr/queryNewList')
        document = read_json(source_path)
        assert type(document['result']) is int and document['result'] == 200
        info = document['info']
        assert info['currentPage'] == page and info['pageSize'] == 200
        assert info['totalSize'] == checkpoint['reported_total'] and info['pages'] == checkpoint['reported_pages']
        expected_size = 200 if page < info['pages'] else info['totalSize'] - 200 * (info['pages'] - 1)
        assert len(info['list']) == info['size'] == expected_size
        entry = user_pages.get(page)
        pages.append({
            'page': page, 'source_file': rel, 'source_sha256': sha(source_path),
            'actual_bytes': source_path.stat().st_size, 'rows': len(info['list']),
            'business_result': document['result'], 'echo_currentPage': info['currentPage'],
            'echo_totalSize': info['totalSize'], 'echo_pages': info['pages'],
            'receipt_file': receipt_path.relative_to(args.source).as_posix(),
            'source_observed_utc': receipt['observed_utc'],
            'user_manifest_page_path': entry['path'] if entry else None,
            'user_manifest_sha256': entry['sha256'] if entry else None,
            'user_manifest_bytes': entry['bytes'] if entry else None,
            'same_bytes_as_user_manifest': bool(entry and entry['sha256'] == sha(source_path) and entry['bytes'] == source_path.stat().st_size),
        })
        for index, raw in enumerate(info['list']):
            assert isinstance(raw.get('uuid'), str) and raw['uuid']
            model = raw.get('vehicleModel')
            assert isinstance(model, str)
            row_sha = hashlib.sha256(js(raw).encode('utf-8')).hexdigest()
            record = {
                'library': 'new', 'record_key': f"new:{raw['uuid']}:{row_sha}",
                'source_occurrence': f'new:{page}:{index}', 'model_key': model,
                'stable_id_raw': raw['uuid'], 'record_number_raw': raw.get('recordNumber'),
                'raw_full_row_sha256': row_sha, 'source_file': rel,
                'raw_canonical_row_sha256': hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest(),
                'json_pointer': f'/info/list/{index}', 'source_sha256': sha(source_path),
                'source_observed_utc': receipt['observed_utc'],
                'in_core_2208_exact': model in targets,
                'raw_record': raw,
            }
            all_records.append(record)
            by_uuid[raw['uuid']].append(record)
            all_field_names.update(raw)
            if raw.get('reportType') != '3' or raw.get('energyType') != '8':
                category_conflicts.append({'record_key': record['record_key'], 'model_key': model,
                                           'reportType_raw': raw.get('reportType'), 'energyType_raw': raw.get('energyType')})
            if model in targets:
                exact_records.append(record)
                by_exact[model].append(record)
            for candidate_target in sorted(normalized_targets.get(normalized(model), set())):
                by_normalized[candidate_target].append(record)
                if model != candidate_target:
                    normalized_candidates.append({
                        'candidate_target_model': candidate_target, 'raw_registry_model': model,
                        'normalized_value': normalized(model), 'record_key': record['record_key'],
                        'source_occurrence': record['source_occurrence'],
                        'source_file': rel, 'json_pointer': record['json_pointer'],
                        'source_sha256': record['source_sha256'],
                        'not_counted_as_exact_match': True,
                        'same_configuration_or_freeze_comparability_certified': False,
                    })
    assert len(all_records) == checkpoint['rows']
    assert len(by_uuid) == checkpoint['unique_ids']
    assert len({row['raw_full_row_sha256'] for row in all_records}) == checkpoint['unique_full_rows']
    assert len({row['source_occurrence'] for row in all_records}) == len(all_records)
    assert len({row['record_key'] for row in all_records}) == len(all_records)
    new_models = set(by_exact)
    union_models = old_models | new_models
    intersection_models = old_models & new_models
    new_only = new_models - old_models
    old_only = old_models - new_models
    union_added = union_models - previous_models
    previous_missing_now = previous_models - union_models

    duplicate_rows = []
    for identity, records in sorted(by_uuid.items()):
        if len(records) < 2:
            continue
        fields = set().union(*(set(row['raw_record']) for row in records))
        differing = [field for field in sorted(fields)
                     if len({js(row['raw_record'].get(field)) for row in records}) > 1]
        duplicate_rows.append({
            'uuid_raw': identity, 'occurrences': len(records),
            'distinct_full_rows': len({row['raw_full_row_sha256'] for row in records}),
            'model_keys_json': js(sorted({row['model_key'] for row in records})),
            'different_fields_json': js(differing),
            'state_fields_by_record_json': js([
                {'record_key': row['record_key'], **{field: row['raw_record'].get(field)
                  for field in ['recordNumber', 'reportStatus', 'abandonTime', 'abandonOpinion', 'enableDate', 'issueDate']}}
                for row in records]),
            'source_occurrences_json': js([row['source_occurrence'] for row in records]),
            'retained_all_observed_rows': True,
        })

    model_table = []
    conflict_rows = []
    old_full_by_model = defaultdict(list)
    for row in old_records:
        old_full_by_model[row['model_key']].append(row)
    for target in target_rows:
        model = target['model_key']
        new = by_exact[model]
        candidates = by_normalized[model]
        new_codes = sorted({str(row['raw_record'].get('testBasisStandard')) for row in new if row['raw_record'].get('testBasisStandard') is not None})
        old_codes = json.loads(old_by_model[model]['old_cycle_codes_raw_json']) if model in old_by_model else []
        old = old_full_by_model[model]
        new_ranges = sorted({js(row['raw_record'].get('drivingRange')) for row in new})
        old_ranges = sorted({js(row['raw_record'].get('runingRange')) for row in old})
        new_consumption = sorted({js(row['raw_record'].get('electricEnergyConsumption')) for row in new})
        old_consumption = sorted({js(row['raw_record'].get('powerConsumption')) for row in old})
        new_mass = sorted({js(row['raw_record'].get('completeVehicleQuality')) for row in new})
        old_condition_tuples = sorted({js(condition) for row in old for condition in (row['raw_record'].get('workConditionVos') or [])})
        difference_reasons = []
        if len(new_codes) > 1: difference_reasons.append('multiple_new_standard_codes')
        if len(old_codes) > 1: difference_reasons.append('multiple_old_cycle_codes')
        if len(new_ranges) > 1: difference_reasons.append('multiple_new_range_raw_values')
        if len(old_ranges) > 1: difference_reasons.append('multiple_old_range_raw_values')
        if len(new_consumption) > 1: difference_reasons.append('multiple_new_consumption_raw_values')
        if len(old_consumption) > 1: difference_reasons.append('multiple_old_consumption_raw_values')
        if len(new_mass) > 1: difference_reasons.append('multiple_new_curb_mass_raw_values')
        if new and old and new_ranges != old_ranges: difference_reasons.append('new_old_range_raw_value_sets_differ')
        if new and old and new_consumption != old_consumption: difference_reasons.append('new_old_consumption_raw_value_sets_differ_units_not_normalized')
        item = {
            'model_key': model, 'new_exact_records': len(new),
            'new_exact_unique_uuid': len({row['stable_id_raw'] for row in new}),
            'old_exact_records': int(old_by_model[model]['old_raw_rows']) if model in old_by_model else 0,
            'exact_match_state': 'both' if new and model in old_models else 'new_only' if new else 'old_only' if model in old_models else 'not_in_observed_filtered_views',
            'new_nfkc_whitespace_candidate_records_including_exact': len(candidates),
            'new_nfkc_whitespace_candidate_only_records': sum(row['model_key'] != model for row in candidates),
            'new_nfkc_whitespace_raw_variants_json': js(sorted({row['model_key'] for row in candidates if row['model_key'] != model})),
            'new_standard_codes_raw_json': js(new_codes),
            'old_cycle_codes_raw_json': js(old_codes),
            'new_range_raw_values_json': js([json.loads(value) for value in new_ranges]),
            'old_top_range_raw_values_json': js([json.loads(value) for value in old_ranges]),
            'new_consumption_raw_values_json': js([json.loads(value) for value in new_consumption]),
            'old_top_consumption_raw_values_json': js([json.loads(value) for value in old_consumption]),
            'new_curb_mass_raw_values_json': js([json.loads(value) for value in new_mass]),
            'old_work_condition_objects_json': js([json.loads(value) for value in old_condition_tuples]),
            'old_list_curb_mass_missing_detail_not_acquired': bool(old) and not any('completeVehicleQuality' in row['raw_record'] for row in old),
            'version_difference_reasons_json': js(difference_reasons),
            'version_difference_is_same_configuration_conflict_certified': False,
            'multiple_new_standard_codes_observed': len(new_codes) > 1,
            'multiple_old_cycle_codes_observed': len(old_codes) > 1,
            'new_issue_dates_raw_json': js(sorted({row['raw_record']['issueDate'] for row in new if row['raw_record'].get('issueDate')})),
            'new_enable_dates_raw_json': js(sorted({row['raw_record']['enableDate'] for row in new if row['raw_record'].get('enableDate')})),
            'new_overtime_cause_raw_json': js(sorted({row['raw_record']['overtimeCause'] for row in new if row['raw_record'].get('overtimeCause')})),
            'source_effective_record_id': target['effective_record_id'],
            'tax_source_file': target['source_file'], 'tax_source_sha256': target['source_sha256'],
            'same_tax_configuration_identity_certified': False,
            'historical_public_availability_certified': False,
            'unmarked_frozen_cycle_list_closed': False,
            'can_replace_frozen_scientific_input': False,
        }
        model_table.append(item)
        if difference_reasons:
            conflict_rows.append(item)

    queue = []
    by_token = defaultdict(list)
    for record in exact_records:
        raw = record['raw_record']
        token = raw.get('fullLabel')
        assert token is None or isinstance(token, str)
        token_sha = hashlib.sha256(token.encode()).hexdigest() if token else ''
        task = {
            'record_key': record['record_key'], 'source_occurrence': record['source_occurrence'],
            'model_key': record['model_key'], 'uuid_raw': record['stable_id_raw'],
            'record_number_raw': record['record_number_raw'],
            'fullLabel_raw': token or '', 'token_sha256': token_sha,
            'download_url': 'https://yhgscx.miit.gov.cn/file/file/file/download?' + urlencode({'m': token, 'p': 1}) if token else '',
            'proposed_pdf_file': f'labels/{token_sha}.pdf' if token else '',
            'testBasisStandard_raw': raw.get('testBasisStandard'),
            'issueDate_raw': raw.get('issueDate'), 'enableDate_raw': raw.get('enableDate'),
            'source_file': record['source_file'], 'json_pointer': record['json_pointer'],
            'source_sha256': record['source_sha256'], 'source_observed_utc': record['source_observed_utc'],
            'same_tax_configuration_identity_certified': False,
            'historical_public_availability_certified': False,
        }
        queue.append(task)
        if token:
            by_token[token].append(task)
    unique_queue = []
    for token, tasks in sorted(by_token.items(), key=lambda item: item[1][0]['token_sha256']):
        first = tasks[0]
        unique_queue.append({
            'token_sha256': first['token_sha256'], 'fullLabel_raw': token,
            'download_url': first['download_url'], 'proposed_pdf_file': first['proposed_pdf_file'],
            'referencing_records': len(tasks),
            'model_keys_json': js(sorted({task['model_key'] for task in tasks})),
            'record_keys_json': js([task['record_key'] for task in tasks]),
            'source_occurrences_json': js([task['source_occurrence'] for task in tasks]),
            'deduplication_only_reuses_file_not_state_rows': True,
        })
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / '10479记录_新库全字段与来源.jsonl', all_records)
    write_jsonl(output / '新库精确命中_全字段记录.jsonl', exact_records)
    write_csv(output / '2208型号_新旧两库精确匹配及规范化候选.csv', model_table, list(model_table[0]))
    write_csv(output / '规范化候选_不计精确命中.csv', normalized_candidates, ['candidate_target_model', 'raw_registry_model', 'normalized_value', 'record_key', 'source_occurrence', 'source_file', 'json_pointer', 'source_sha256', 'not_counted_as_exact_match', 'same_configuration_or_freeze_comparability_certified'])
    write_csv(output / '重复UUID_状态差异_全行保留.csv', duplicate_rows, ['uuid_raw', 'occurrences', 'distinct_full_rows', 'model_keys_json', 'different_fields_json', 'state_fields_by_record_json', 'source_occurrences_json', 'retained_all_observed_rows'])
    write_csv(output / '版本冲突线索_逐型号.csv', conflict_rows, list(model_table[0]))
    write_csv(output / '标签下载队列_每条精确记录.csv', queue, list(queue[0]) if queue else ['record_key'])
    write_csv(output / '标签下载队列_按fullLabel去重文件.csv', unique_queue, list(unique_queue[0]) if unique_queue else ['fullLabel_raw'])
    old_detail_queue = []
    merged_records = exact_records + [
        {**row, 'in_core_2208_exact': True,
         'raw_canonical_row_sha256': hashlib.sha256(json.dumps(row['raw_record'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()}
        for row in old_records]
    merged_flat_rows = []
    for row in merged_records:
        raw = row['raw_record']
        merged_flat_rows.append({
            'library': row['library'], 'record_key': row['record_key'], 'model_key': row['model_key'],
            'source_occurrence': row['source_occurrence'], 'source_file': row['source_file'],
            'json_pointer': row['json_pointer'], 'source_sha256': row['source_sha256'],
            'source_observed_utc': row['source_observed_utc'],
            'range_raw': raw.get('drivingRange') if row['library'] == 'new' else raw.get('runingRange'),
            'electric_consumption_raw': raw.get('electricEnergyConsumption') if row['library'] == 'new' else raw.get('powerConsumption'),
            'curb_mass_raw_new_only': raw.get('completeVehicleQuality') if row['library'] == 'new' else None,
            'old_list_mass_missing_detail_pending': row['library'] == 'old',
            'testBasisStandard_raw_new_only': raw.get('testBasisStandard') if row['library'] == 'new' else None,
            'workConditionVos_raw_json_old_only': js(raw.get('workConditionVos')) if row['library'] == 'old' else '',
            'record_number_raw': row['record_number_raw'],
            'cross_library_same_configuration_link_certified': False,
        })
    for row in old_records:
        assert re.fullmatch(r'[0-9a-f]{32}', row['stable_id_raw'])
        old_detail_queue.append({
            'record_key': row['record_key'], 'source_occurrence': row['source_occurrence'],
            'model_key': row['model_key'], 'applyId_raw': row['stable_id_raw'],
            'record_number_raw': row['record_number_raw'],
            'request_method': 'POST',
            'request_url': 'https://yhgscx.miit.gov.cn/fuel-consumption-center/fuel-consumption-center/fcSearchCtr/queryDetail',
            'request_json': js({'applyId': row['stable_id_raw']}),
            'proposed_response_file': f"old_details/{row['stable_id_raw']}.json",
            'source_file': row['source_file'], 'json_pointer': row['json_pointer'],
            'source_sha256': row['source_sha256'], 'source_observed_utc': row['source_observed_utc'],
            'body_may_not_echo_applyId_keep_request_mapping': True,
        })
    write_csv(output / '旧库详情下载队列_4497applyId固定来源.csv', old_detail_queue, list(old_detail_queue[0]))
    write_csv(output / '版本对照_逐记录原字段_不做笛卡尔连接.csv', merged_flat_rows, list(merged_flat_rows[0]))
    write_jsonl(output / '两库精确命中_合并可定位记录.jsonl', merged_records)
    write_csv(output / '53页_与用户manifest逐字节对账.csv', pages, list(pages[0]))
    sets = {
        'old_exact_models': sorted(old_models), 'new_exact_models': sorted(new_models),
        'intersection_models': sorted(intersection_models), 'union_models': sorted(union_models),
        'new_only_models': sorted(new_only), 'old_only_models': sorted(old_only),
        'union_models_added_vs_round10': sorted(union_added),
        'round10_union_models_absent_from_current_union': sorted(previous_missing_now),
    }
    (output / '两库交并差_精确型号集合.json').write_text(json.dumps(sets, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    field_rows = []
    for field in sorted(all_field_names):
        field_rows.append({
            'field': field,
            'all_rows_field_present': sum(field in row['raw_record'] for row in all_records),
            'all_rows_nonblank_nonnull': sum(row['raw_record'].get(field) not in (None, '') for row in all_records),
            'exact_rows_field_present': sum(field in row['raw_record'] for row in exact_records),
            'exact_rows_nonblank_nonnull': sum(row['raw_record'].get(field) not in (None, '') for row in exact_records),
        })
    write_csv(output / '新库字段覆盖_全库及精确命中.csv', field_rows, list(field_rows[0]))
    normalized_model_set = {model for model, records in by_normalized.items() if records}
    normalized_record_set = {row['record_key'] for records in by_normalized.values() for row in records}
    # Separate candidate recipes explain how alternative summary counts can
    # arise; no recipe is silently substituted for raw-string exact matching.
    recipe_functions = {
        'raw_string_exact': lambda value: value,
        'outer_whitespace_strip_only': lambda value: value.strip(),
        'nfkc_unicode_whitespace_only': normalized,
        'nfkc_unicode_whitespace_plus_upper_casefold': lambda value: normalized(value).upper(),
    }
    recipe_comparison = {}
    for name, function in recipe_functions.items():
        mapped_targets = defaultdict(set)
        for model in targets: mapped_targets[function(model)].add(model)
        records = [row for row in all_records if function(row['model_key']) in mapped_targets]
        matched_targets = set().union(*(mapped_targets[function(row['model_key'])] for row in records))
        profile_dates = date_profile(records, 'issueDate', args.cutoff_date)
        unsafe_string_count = sum((row['raw_record'].get('issueDate') or '') <= args.cutoff_date.isoformat() for row in records)
        recipe_comparison[name] = {
            'target_models': len(matched_targets), 'raw_records': len(records),
            'rows_with_valid_issueDate_on_or_before_cutoff': profile_dates['rows_on_or_before_cutoff_date'],
            'blank_or_null_issueDate_rows': profile_dates['blank_or_null_rows'],
            'unsafe_empty_string_date_comparison_count_not_valid': unsafe_string_count,
            'testBasisStandard_raw_distribution': distribution(records, 'testBasisStandard'),
            'not_certified_as_user_actual_implementation': True,
        }
    assert len(normalized_model_set) == 545 and len(normalized_record_set) == 961
    assert len(normalized_model_set - new_models) == 6
    assert recipe_comparison['nfkc_unicode_whitespace_plus_upper_casefold']['target_models'] == 566
    assert recipe_comparison['nfkc_unicode_whitespace_plus_upper_casefold']['raw_records'] == 1087
    assert recipe_comparison['outer_whitespace_strip_only']['raw_records'] == 938
    assert recipe_comparison['outer_whitespace_strip_only']['rows_with_valid_issueDate_on_or_before_cutoff'] == 460
    assert recipe_comparison['outer_whitespace_strip_only']['blank_or_null_issueDate_rows'] == 59
    assert recipe_comparison['outer_whitespace_strip_only']['unsafe_empty_string_date_comparison_count_not_valid'] == 519
    strip_only_extras = [
        {'record_key': row['record_key'], 'raw_model': row['model_key'],
         'stripped_candidate': row['model_key'].strip(),
         'source_file': row['source_file'], 'json_pointer': row['json_pointer']}
        for row in all_records if row['model_key'] not in targets and row['model_key'].strip() in targets]
    summary = {
        'status': 'PASS', 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'network_requests_by_this_analysis': 0,
        'input_sha256': {
            'new_checkpoint': sha(cp_path), '2208_target_list': sha(args.targets),
            'user_manifest': sha(args.user_manifest), 'old_1233_model_set': sha(old_models_path),
            'old_4497_records': sha(old_records_path), 'round10_2208_match_table': sha(args.previous_table),
        },
        'source_view': {
            'filters': checkpoint['filters'], 'pages': len(pages),
            'raw_rows': len(all_records), 'reported_totalSize': checkpoint['reported_total'],
            'unique_uuid': len(by_uuid), 'unique_full_row_sha256': len({row['raw_full_row_sha256'] for row in all_records}),
            'duplicate_uuid_groups': len(duplicate_rows),
            'duplicate_uuid_extra_occurrences': sum(len(records) - 1 for records in by_uuid.values()),
            'all_page_receipts_and_echoes_verified': True,
            'earliest_page_observed_utc': min(page['source_observed_utc'] for page in pages),
            'latest_page_observed_utc': max(page['source_observed_utc'] for page in pages),
            'atomic_transaction_snapshot_claimed': False,
            'separate_from_round10_new_page_observations': True,
            'category_conflict_rows': category_conflicts,
        },
        'user_manifest_comparison': {
            'claimed_page_entries': len(user_pages),
            'pages_same_sha256_and_bytes': sum(page['same_bytes_as_user_manifest'] for page in pages),
            'pages_different_or_unlisted': [page['page'] for page in pages if not page['same_bytes_as_user_manifest']],
            'claim_is_byte_digest_consistency_not_authentication_of_unuploaded_delivery': True,
            'our_actual_acquisition_times_are_retained_even_if_bytes_match': True,
        },
        'core_2208': {
            'target_models': 2208, 'old_exact_models': len(old_models), 'old_exact_records': len(old_records),
            'new_exact_models': len(new_models), 'new_exact_records': len(exact_records),
            'new_nfkc_whitespace_candidate_models_including_exact': len(normalized_model_set),
            'new_nfkc_whitespace_candidate_records_including_exact': len(normalized_record_set),
            'candidate_only_target_models': len(normalized_model_set - new_models),
            'candidate_only_record_links': len(normalized_candidates),
            'normalized_target_collisions': normalized_collisions,
            'exact_intersection_models': len(intersection_models), 'exact_union_models': len(union_models),
            'exact_new_only_models': len(new_only), 'exact_old_only_models': len(old_only),
            'no_exact_match_in_either_observed_view': len(targets - union_models),
            'previous_round10_exact_union_models': len(previous_models),
            'exact_union_added_vs_round10': len(union_added),
            'previous_models_absent_now': sorted(previous_missing_now),
            'exact_records_with_fullLabel': len(queue) - sum(not row['fullLabel_raw'] for row in queue),
            'unique_fullLabel_file_tasks': len(unique_queue),
            'old_detail_applyId_tasks': len(old_detail_queue),
            'merged_exact_records_preserved': len(merged_records),
            'model_version_raw_value_difference_candidates': len(conflict_rows),
            'new_multiple_standard_code_models': sum(row['multiple_new_standard_codes_observed'] for row in model_table),
            'old_multiple_cycle_code_models': sum(row['multiple_old_cycle_codes_observed'] for row in model_table),
            'jx_in_core_2208': False,
            'numeric_ready_delta': 0, 'battery_energy_gap_closed': 0,
            'unmarked_frozen_cycle_list_closed': 0,
            'same_tax_configuration_identity_certified': False,
            'historical_public_availability_certified': False,
        },
        'exact_match_profiles': {
            'testBasisStandard_raw': distribution(exact_records, 'testBasisStandard'),
            'vehicleType_raw': distribution(exact_records, 'vehicleType'),
            'productName_raw': distribution(exact_records, 'productName'),
            'reportStatus_raw': distribution(exact_records, 'reportStatus'),
            'overtimeCause_raw': distribution(exact_records, 'overtimeCause'),
            'issueDate': date_profile(exact_records, 'issueDate', args.cutoff_date),
            'enableDate': date_profile(exact_records, 'enableDate', args.cutoff_date),
        },
        'all_rows_profiles': {
            'testBasisStandard_raw': distribution(all_records, 'testBasisStandard'),
            'vehicleType_raw': distribution(all_records, 'vehicleType'),
            'reportStatus_raw': distribution(all_records, 'reportStatus'),
            'issueDate': date_profile(all_records, 'issueDate', args.cutoff_date),
            'enableDate': date_profile(all_records, 'enableDate', args.cutoff_date),
        },
        'observed_field_names': sorted(all_field_names),
        'candidate_recipe_comparison': recipe_comparison,
        'outer_strip_only_extra_records': strip_only_extras,
        'interpretation_boundaries': [
            'Exact match uses raw-string equality; NFKC plus removal of Unicode whitespace only generates candidates, not exact closure.',
            'Codes are raw metadata; do not map code5/6 or CATC/NEDC to trial standard without authoritative dictionary and version evidence.',
            'issueDate is a registry field, not proven first-publication time, and does not itself certify the tax-catalogue configuration.',
            'All state rows are retained for repeated uuid; repeated attachment tokens reuse PDF acquisition only.',
            'Published new and old filtered views are separate non-atomic observations, not a merged transaction or a chronological panel.',
            'The public energy-label fields do not supply a certified battery-pack total energy; energy consumption cannot fill that field.',
            'Matched metadata, accessible fullLabel and dates are evidence tasks, not closed frozen scientific gaps.',
        ],
    }
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    core = summary['core_2208']
    profile = summary['exact_match_profiles']
    (output / 'README.md').write_text(f'''# 新库完整公开视图：离线复核与标签队列

本轮53页完整视图共{len(all_records):,}原始行，与回显totalSize一致；唯一uuid {len(by_uuid):,}，全行哈希{checkpoint['unique_full_rows']:,}全唯一。全部响应字节、收据SHA、业务result=200、请求/回显currentPage、totalSize和页长已验证。最后一页{pages[-1]['rows']}行。本脚本没有请求官网。

与用户交付manifest的53项原页摘要逐页对账：{summary['user_manifest_comparison']['pages_same_sha256_and_bytes']}/53项SHA256及字节数一致。这里核验的是所交manifest与本轮取得的原页一致性，不把未上传的records.jsonl等交付件当作已取得，也不以manifest认证此前采集时间。各页保留本轮真实observed_utc；本轮观测不与round10的4页合成同一事务快照或时间序列。

| 2,208目标精确口径 | 型号数 | 记录数 |
|---|---:|---:|
| 旧库已核集合 | {len(old_models)} | {len(old_records)} |
| 本轮新库 | {len(new_models)} | {len(exact_records)} |
| 两库交集 | {len(intersection_models)} | 不以跨库记录相同认定配置 |
| 两库并集 | {len(union_models)} | 不直接相加型号数 |
| 仅新库 | {len(new_only)} | — |
| 仅旧库 | {len(old_only)} | — |

相对round10并集1,234型号新增{len(union_added)}型号；在两套已取得筛选视图均无精确命中的目标{len(targets-union_models)}型号。这不是“官网及历史库不存在”的结论。JX6550T-M5BEV不在2,208名单。

NFKC后删除Unicode空白得到{len(normalized_model_set)}目标型号、{len(normalized_record_set)}记录的候选（含精确命中），另有{len(normalized_candidates)}条非精确候选关联。候选不计精确命中或冻结缺口闭合。未转换大小写、标点或非空白格式字符。

另按“仅去首尾空白”可得到{recipe_comparison['outer_whitespace_strip_only']['target_models']}/{recipe_comparison['outer_whitespace_strip_only']['raw_records']}；新增两条原字符串为“ BMW6462AAEV”和“ BMW6462ABEV”（第51页零基行135、136）。在NFKC去Unicode空白之外再加upper大小写折叠，可得到{recipe_comparison['nfkc_unicode_whitespace_plus_upper_casefold']['target_models']}/{recipe_comparison['nfkc_unicode_whitespace_plus_upper_casefold']['raw_records']}。这些规则可复现用户所述938及566/1087，但不认证其实际实现；应按明示口径分别报数，不能把候选称为原字符串精确匹配。

日期必须先排除空值并解析为真实日期。原字符串精确记录有效早期issueDate为458；trim候选为460。trim候选另有59条空issueDate：如果错误地将空值转为字符串“”再比较“<=2023-12-10”，会得到460+59=519。这个无效算法能复现用户519，但不认证其实际程序如此实现；519不能作为本轮有效历史日期证据数。具体配方和空值计数在summary.json并列，未据此推定公开时间。

精确命中的{len(exact_records)}记录中{core['exact_records_with_fullLabel']}条有fullLabel，可生成{len(unique_queue)}个唯一PDF文件任务。每条记录下载队列保留固定record_key及原页SHA；文件去重仅复用同token下载，不删备案状态行。{len(duplicate_rows)}组重复uuid的每条状态原行均保留，并列出不同字段。

旧库{len(old_detail_queue)}个applyId详情任务保留每条固定来源及请求体。合并的{len(merged_records)}条精确记录按各自来源定位，不做跨库记录笛卡尔连接；{len(conflict_rows)}型号的标准／工况或range、电耗、整备原值集合差异只列为逐版本配置核查线索，不认证同配置冲突。旧list不含整备质量，标记尚待queryDetail；未擅自统一或缩放电耗单位。

标准代码分布（原代码，不自行映射）：{js(profile['testBasisStandard_raw'])}。issueDate范围{profile['issueDate']['minimum_raw_date']}至{profile['issueDate']['maximum_raw_date']}；早于{args.cutoff_date}的{profile['issueDate']['rows_before_cutoff_date']}条、等于该日{profile['issueDate']['rows_on_cutoff_date']}条。enableDate最早{profile['enableDate']['minimum_raw_date']}。这些字段不是已认证的历史公开日期或同免税配置证明。

**本轮冻结工况清单关闭0、电池总能量字段关闭0、numeric_ready增量0。** 标签原件尚需下载并逐页核对试验标准、日期、车辆/配置和版本冲突；原始电耗不等于电池组总能量。52份科学CSV不由本脚本修改。

- [离线摘要及边界](summary.json)
- [53页与用户manifest对账](53页_与用户manifest逐字节对账.csv)
- [全部10,479行原字段与来源](10479记录_新库全字段与来源.jsonl)
- [精确命中全字段](新库精确命中_全字段记录.jsonl)
- [2,208型号交叉台账](2208型号_新旧两库精确匹配及规范化候选.csv)
- [交并差完整型号集合](两库交并差_精确型号集合.json)
- [规范化候选](规范化候选_不计精确命中.csv)
- [重复uuid状态差异](重复UUID_状态差异_全行保留.csv)
- [标准及工况冲突线索](版本冲突线索_逐型号.csv)
- [逐记录标签下载队列](标签下载队列_每条精确记录.csv)
- [唯一fullLabel文件任务](标签下载队列_按fullLabel去重文件.csv)
- [旧库4,497条详情任务](旧库详情下载队列_4497applyId固定来源.csv)
- [两库合并精确记录及来源](两库精确命中_合并可定位记录.jsonl)
- [逐记录版本对照](版本对照_逐记录原字段_不做笛卡尔连接.csv)
- [字段覆盖](新库字段覆盖_全库及精确命中.csv)
- [可复跑脚本](analyze_new_snapshot.py)
- [输出SHA清单](文件_SHA256.csv)

复跑可传--audit-root重映射原round目录，或分别传--source、--targets、--old-review、--previous-table、--user-manifest、--cutoff-date和--output指向实际下载的仓库路径；原有/workspace前缀不是强制路径。用于仓库下载版时，--source指向本轮public_new_snapshot，--old-review指向本轮independent_old_review，--user-manifest指向本轮user_submitted/delivery_manifest_用户原文.json，--targets指向v1_5/public_completion_20261009/public_cycle/2208型号_整篇工况补证结果_只读旁表.csv，--previous-table指向v1_5/energy_registry_20261009/public_energy_registry/2208型号_两库完整视图精确匹配.csv。

checkpoint未完成时脚本停止，不输出伪完整结果。本脚本固定输入指纹并对本轮已独立复核的545/961/6等候选数设质量断言，仅用于本次固定原页复跑，更新官网快照需另立批次并审查断言，不能替换当前快照。raw_full_row_sha256及record_key沿用原采集Python json.dumps(raw, ensure_ascii=False, sort_keys=True)的UTF-8字节，保留默认空格；另存raw_canonical_row_sha256采用separators=(',', ':')的紧凑形式以满足交接配方，两个字段不混用。所有输入只读，写入限定在--output。
''', encoding='utf-8')
    manifest = [{'file': path.relative_to(output).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}
                for path in sorted(output.rglob('*'))
                if path.is_file() and path.name != '文件_SHA256.csv' and '__pycache__' not in path.parts]
    write_csv(output / '文件_SHA256.csv', manifest, ['file', 'bytes', 'sha256'])
    print(js({'core': summary['core_2208'], 'page_sha_matches': summary['user_manifest_comparison']['pages_same_sha256_and_bytes'], 'profiles': profile}))


if __name__ == '__main__':
    main()
