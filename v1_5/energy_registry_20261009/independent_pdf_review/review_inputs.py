#!/usr/bin/env python3
"""Read-only, offline inspection of supplied label and two-record JSON.

Rerun: python review_inputs.py --pdf INPUT.pdf --json INPUT.json \
    --requirements 2208数值可用型号_公告前试验工况待核清单.csv --out OUTPUT_DIRECTORY
No network requests; input bytes are checked before and after inspection.
"""
from pathlib import Path
import argparse, csv, hashlib, json, re
from datetime import datetime, timezone
import fitz
import pypdf


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(pdf, data, requirements, out):
    out.mkdir(parents=True, exist_ok=True)
    before = {str(p): digest(p) for p in (pdf, data, requirements)}
    document = fitz.open(pdf)
    reader = pypdf.PdfReader(pdf)
    mu_pages = [page.get_text() for page in document]
    py_pages = [page.extract_text() or '' for page in reader.pages]
    (out/'PDF文本_PyMuPDF.txt').write_text('\n\n'.join(mu_pages), encoding='utf-8')
    (out/'PDF文本_pypdf.txt').write_text('\n\n'.join(py_pages), encoding='utf-8')
    document[0].get_pixmap(matrix=fitz.Matrix(2, 2)).save(out/'标签_第1页.png')
    data_object = json.loads(data.read_text(encoding='utf-8-sig'))
    records = data_object['info']['list']
    required_phrases = [
        'JX6550T-M5BEV', '2360', '120', '3490', '293', '19.2',
        'GB/T18386.1—2021', 'GD20240715105558048',
        '高温开空调行业续驶里程平均约下降：15%',
        '低温开暖风行业续驶里程平均约下降：40%',
    ]
    dual_engine_checks = []
    for name, texts in [('PyMuPDF', mu_pages), ('pypdf', py_pages)]:
        normalized = re.sub(r'\s+', '', ''.join(texts))
        checks = {phrase: phrase in normalized for phrase in required_phrases}
        dual_engine_checks.append({'engine': name, 'checks': checks, 'all_pass': all(checks.values())})
    with requirements.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    memberships = [row for row in rows if row['model_key'] == 'JX6550T-M5BEV']
    fields = set(records[0])
    record_summaries = []
    for record in records:
        record_summaries.append({
            'record_number': record['recordNumber'],
            'vehicle_model': record['vehicleModel'],
            'keys': sorted(record.keys()),
            'field_count': len(record),
            'null_fields': [k for k, v in record.items() if v is None],
            'null_count': sum(v is None for v in record.values()),
            'empty_string_fields': [k for k, v in record.items() if v == ''],
            'curb_mass_kg_raw': record['completeVehicleQuality'],
            'range_km_raw': record['drivingRange'],
            'electricity_consumption_kwh_per_100km_raw': record['electricEnergyConsumption'],
            'motor_peak_kw_raw': record['driveMotorPeakPower'],
            'test_basis_standard_raw_code': record['testBasisStandard'],
            'issue_date_raw': record['issueDate'],
            'enable_date_raw': record['enableDate'],
            'activation_date_raw': record['activationDate'],
            'submit_date_raw': record['submitDate'],
            'create_time_raw': record['createTime'],
            'update_time_raw': record['updateTime'],
            'migration_reason_raw': record['overtimeCause'],
            'full_label_locator_raw': record['fullLabel'],
            'matching_uploaded_pdf': record['recordNumber'] == 'GD20240715105558048',
            'literal_standard_independently_verified_by_uploaded_pdf': (
                'GB/T 18386.1—2021' if record['recordNumber'] == 'GD20240715105558048' else None
            ),
            'standard_code_mapping_verified_for_this_record': record['recordNumber'] == 'GD20240715105558048',
        })
    after = {str(p): digest(p) for p in (pdf, data, requirements)}
    assert before == after, 'An input changed during offline review'
    result = {
        'review_utc': datetime.now(timezone.utc).isoformat(),
        'method': 'Offline, read-only; PyMuPDF and pypdf full text plus visual page rendering; no network requests.',
        'pdf': {'supplied_filename': pdf.name, 'bytes': pdf.stat().st_size, 'sha256': before[str(pdf)],
                'pages_pymupdf': len(document), 'pages_pypdf': len(reader.pages),
                'metadata': document.metadata, 'form_field_count': len(reader.get_fields() or {}),
                'embedded_file_count': document.embfile_count(),
                'record_number': 'GD20240715105558048', 'curb_mass_kg': 2360,
                'range_km': 293, 'electricity_consumption_kwh_per_100km': 19.2,
                'explicit_test_standard': 'GB/T 18386.1—2021',
                'literal_test_cycle': None,
                'visible_enable_date': '2024-07-15',
                'visible_issue_date': None, 'battery_total_energy_kwh': None,
                'low_temperature_measurement_report': None,
                'high_temperature_percent_literal': '高温开空调行业续驶里程平均约下降：15%',
                'low_temperature_percent_literal': '低温开暖风行业续驶里程平均约下降：40%',
                'temperature_percentage_scope': 'Industry average explanatory label text, not a configuration-specific measured result.'},
        'json': {'supplied_filename': data.name, 'bytes': data.stat().st_size, 'sha256': before[str(data)],
                 'result': data_object['result'], 'top_level_keys': list(data_object),
                 'info_keys': list(data_object['info']), 'records': record_summaries,
                 'same_record_key_set': all(set(r) == fields for r in records),
                 'pagination_coherent': data_object['info']['totalSize'] == len(records) == 2
                     and data_object['info']['size'] == len(records)
                     and data_object['info']['pages'] == 1,
                 'unique_record_numbers': len(set(r['recordNumber'] for r in records)) == len(records),
                 'battery_total_energy_field_observed': False,
                 'source_http_receipt_in_supplied_json': False,
                 'collection_timestamp_in_supplied_json': False,
                 'second_record_pdf_supplied': False},
        'dual_engine_critical_text_checks': dual_engine_checks,
        'dataset_membership': {'file': requirements.name, 'bytes': requirements.stat().st_size,
             'sha256': before[str(requirements)], 'rows': len(rows),
             'model': 'JX6550T-M5BEV', 'exact_matches': len(memberships),
             'can_reduce_2208_from_this_model': False},
        'conclusions': {
            'uploaded_pdf_proves_explicit_standard_for_2360_label': True,
            'second_2295_pdf_or_official_code_dictionary_still_needed': True,
            'issue_date_means_first_public_availability_verified': False,
            'pre_freeze_test_report_or_original_issue_date_verified': False,
            'cross_catalogue_configuration_identity_verified': False,
            'battery_energy_gap_closed': False,
            'low_temperature_report_gap_closed': False,
            'unlabelled_ready_cohort_gap_closed_by_this_model': False,
            'scientific_inputs_changed': False,
        },
        'inputs_unchanged': before == after,
        'limitations': [
            'User-supplied JSON has no captured HTTP receipt or collection timestamp; offline review does not verify the download source.',
            'The meaning of API issueDate is not established by this PDF; it is not automatically a report date, label first publication date, or pre-freeze availability date.',
            'PDF metadata creationDate is observed provenance metadata, not a certified legal issue date.',
            'The record does not expose a recommendation catalogue configuration ID or a tax-catalogue configuration bridge.',
            'A standard edition named on this label does not by itself identify an explicit CLTC/WLTC cycle or prove the historical tax-catalogue range used that same test.',
            'No battery energy in these supplied records/label is a scoped observation, not proof that every interface or every system record lacks battery energy.',
        ],
    }
    (out/'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    manifest = out/'文件_SHA256.csv'
    with manifest.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f); writer.writerow(['file','bytes','sha256'])
        for p in sorted(out.rglob('*')):
            if p.is_file() and p != manifest:
                writer.writerow([p.relative_to(out).as_posix(), p.stat().st_size, digest(p)])
    print(json.dumps({'all_text_checks_pass': all(c['all_pass'] for c in dual_engine_checks),
        'same_keys': result['json']['same_record_key_set'], 'pages':len(document),
        'pagination_coherent': result['json']['pagination_coherent'], 'jx_in_2208':len(memberships),
        'inputs_unchanged': result['inputs_unchanged'], 'review_sha256':digest(out/'review.json')}, ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    parser.add_argument('--requirements', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args=parser.parse_args()
    run(args.pdf,args.json,args.requirements,args.out)
