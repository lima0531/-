#!/usr/bin/env python3
"""Read-only source/PDF audit plus derived phase summary; makes no HTTP requests."""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import fitz


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify(folder, candidate=False):
    queue = [json.loads(x) for x in (folder / 'label_download_queue.jsonl').read_text(encoding='utf-8').splitlines()]
    rows = [json.loads(x) for x in (folder / 'matched_record_sources.jsonl').read_text(encoding='utf-8').splitlines()]
    by_job = {q['label_job_id']: q for q in queue}
    tally, models, signatures = Counter(), set(), set()
    accepted = {}
    validation_rows = []
    total_bytes = 0
    for path in sorted((folder / 'extracted').glob('*.json')):
        evidence = json.loads(path.read_text(encoding='utf-8'))
        job = by_job[evidence['label_job_id']]
        receipt = json.loads((folder / evidence['receipt_file']).read_text(encoding='utf-8'))
        pdf = (folder / evidence['pdf_file']).read_bytes()
        assert receipt['http_status'] == 200 and receipt['accepted'] and receipt['tls_verified']
        assert receipt['sha256'] == evidence['pdf_sha256'] == sha(pdf)
        assert receipt['bytes'] == evidence['pdf_bytes'] == len(pdf)
        assert receipt['requested_url'] == job['download_url']
        assert pdf.startswith(b'%PDF-')
        document = fitz.open(stream=pdf, filetype='pdf')
        assert not document.needs_pass and document.page_count == evidence['pdf_pages'] > 0
        text = '\n\n'.join(p.get_text() for p in document)
        document.close()
        text_bytes = (folder / evidence['full_text_file']).read_bytes()
        assert text_bytes.decode('utf-8') == text
        assert evidence['full_text_sha256'] == sha(text_bytes)
        plain = re.sub(r'\s+', '', text)
        standards = sorted(set(re.findall(r'GB/?T18386(?:\.1)?[—－\-–]20\d\d', plain)))
        assert standards, 'No explicit standard read from accepted PDF'
        for ref in evidence['record_refs']:
            source = folder / ref['source_file']
            source_raw = source.read_bytes()
            assert sha(source_raw) == ref['source_page_sha256']
            data = json.loads(source_raw)
            source_row = data['info']['list'][int(ref['json_pointer'].split('/')[-1])]
            source_hash = sha(json.dumps(source_row, sort_keys=True, ensure_ascii=False).encode('utf-8'))
            assert source_hash == ref['full_row_sha256']
            assert source_row['uuid'] == ref['uuid'] and source_row['fullLabel'] == evidence['fullLabel']
            assert source_row['recordNumber'] == ref['recordNumber']
            if candidate:
                assert source_row['vehicleModel'] != ref['model_key']
                assert source_row['vehicleModel'].strip() == ref['model_key']
            else:
                assert source_row['vehicleModel'] == ref['model_key']
            assert ref['issueDate_raw'] == source_row.get('issueDate')
            assert ref['enableDate_raw'] == source_row.get('enableDate')
            models.add(ref['model_key'])
            tally[(ref['testBasisStandard_raw'], '|'.join(standards))] += 1
        signatures.add(sha(pdf))
        total_bytes += len(pdf)
        accepted[evidence['label_job_id']] = evidence
        validation_rows.append({'label_job_id': evidence['label_job_id'], 'pdf_sha256': sha(pdf),
                                'pdf_bytes': len(pdf), 'pdf_pages': evidence['pdf_pages'],
                                'standard_versions_observed_in_this_pdf': '|'.join(standards),
                                'raw_standard_codes': '|'.join(sorted({r['testBasisStandard_raw'] for r in evidence['record_refs']})),
                                'models': '|'.join(sorted({r['model_key'] for r in evidence['record_refs']})),
                                'source_row_links_checked': len(evidence['record_refs']),
                                'observed_utc': evidence['observed_utc']})
    remaining = [q for q in queue if q['label_job_id'] not in accepted]
    with (folder / 'remaining_label_download_queue.jsonl').open('w', encoding='utf-8') as stream:
        for job in remaining:
            stream.write(json.dumps(job, ensure_ascii=False) + '\n')
    with (folder / '已获标签_PDF与来源行逐项复核.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        fields = ['label_job_id', 'pdf_sha256', 'pdf_bytes', 'pdf_pages',
                  'standard_versions_observed_in_this_pdf', 'raw_standard_codes', 'models',
                  'source_row_links_checked', 'observed_utc']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(validation_rows)
    checkpoint = json.loads((folder / 'label_checkpoint.json').read_text(encoding='utf-8'))
    assert checkpoint['accepted_pdfs'] == len(accepted)
    covered_rows = [r for r in rows if r['label_job_id'] in accepted]
    summary = {
        'audit_result': 'PASS', 'checked_utc': datetime.now(timezone.utc).isoformat(),
        'matching_scope': 'trim-only candidate queue; excluded from raw exact queue' if candidate else 'raw-string exact queue',
        'queued_records': len(rows), 'queued_unique_label_refs': len(queue),
        'accepted_pdfs': len(accepted), 'accepted_unique_pdf_sha256': len(signatures),
        'accepted_record_links': len(covered_rows), 'accepted_models': len(models),
        'accepted_new_library_only_models': len({r['model_key'] for r in covered_rows if r['is_new_library_only_model']}),
        'accepted_pdf_bytes': total_bytes, 'remaining_unique_label_refs': len(remaining),
        'actual_pdf_standard_by_raw_code': [
            {'raw_code': code, 'standard_observed_in_pdf': standard, 'record_links': count}
            for (code, standard), count in sorted(tally.items())],
        'issueDate_valid_pre_freeze_record_links': sum(bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', r['issueDate_raw'] or '')) and r['issueDate_raw'] <= '2023-12-10' for r in covered_rows),
        'source_pointer_full_row_hash_pdf_and_full_text_verified': True,
        'does_not_establish_date_field_semantics_or_historical_public_accessibility': True,
        'does_not_certify_tax_catalogue_configuration_identity': True,
        'same_cycle_comparability_certified': False,
        'frozen_core_science_modified': False,
        'all_queued_pdfs_downloaded': checkpoint['completed'],
        'pause_kind': checkpoint.get('pause_kind'), 'stop_reason': checkpoint['stop_reason'],
    }
    (folder / 'label_phase_verification.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.root.resolve()
    result = {'strict_raw': verify(root), 'whitespace_candidates': verify(root / 'whitespace_candidates', True)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
