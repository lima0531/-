#!/usr/bin/env python3
"""Stage an independently reviewed collection batch beside unchanged science."""
import argparse, csv, hashlib, json, re, shutil, zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

parser = argparse.ArgumentParser()
parser.add_argument('--audit-root', type=Path, default=Path('/workspace/purchase_tax_audit'))
parser.add_argument('--export-root', type=Path, default=Path('/workspace/file_export_proposal'))
args = parser.parse_args()
AUDIT, EXPORT = args.audit_root.resolve(), args.export_root.resolve()
SOURCE, V5 = AUDIT / 'round11', EXPORT / 'v1_5'
NAME = 'energy_new_complete_20261009'
OUT = V5 / NAME
ZIP_NAME = 'energy_new_snapshot_and_first_labels_20261009.zip'
GOLD = json.loads((AUDIT / 'round6/pre_review_scientific_csv_sha256.json').read_text())
OLD_ZIPS = {
    'purchase_tax_data_v1_5.zip': '3fd50d6aa95eca0d8483b5bcc409b4c246b024b1dd707ef8e67d95df84e70f20',
    'purchase_tax_sources_v1_5.zip': '17b10d905721b38526a6fc0191680721bb10dc977e8efbad6a28e2385d0f06a2',
    'review_20261009/review_supplement_20261009.zip': 'd5dfad8e6f2cfd5ae50ef0a76c2e384b5c8e1306a45ca928c96f4fb6ca5bb521',
    'progress_20261009/progress_and_evidence_20261009.zip': '01fe60c3d5418dd1d5c0534c13d0b813a7e15c988e68624f8baf8502eea6c6c1',
    'public_completion_20261009/public_completion_and_handoff_20261009.zip': '814ecec75a01323257ca17ccfab905f41c4513a8c08a9a00709ab03bb16c3e11',
    'energy_registry_20261009/energy_records_and_review_20261009.zip': '3bf75d9b8c33f51de3cb7b2690db2142d31b68e727fae224a43d7b2ffa2b9184',
}

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def files(root):
    return sorted(p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith('.tmp'))

def record(p, root):
    return {'file': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)}

def inventory(root, exclude=()):
    dest = root / '文件_SHA256.csv'
    prior = dest.read_bytes() if dest.exists() else b'\r\n'
    header = next(csv.reader(prior.decode('utf-8-sig').splitlines()), [])
    fields = header if set(header) == {'file', 'bytes', 'sha256'} else ['file', 'bytes', 'sha256']
    ending = '\r\n' if b'\r\n' in prior else '\n'
    rows = [record(p, root) for p in files(root) if p != dest and p.relative_to(root).as_posix() not in exclude]
    with dest.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator=ending)
        w.writeheader(); w.writerows(rows)
    return len(rows)

def protect():
    assert len(GOLD) == 52
    for rel, expected in GOLD.items():
        p = V5 / rel
        assert p.stat().st_size == expected['bytes'] and sha(p) == expected['sha256'], rel
    for rel, expected in OLD_ZIPS.items():
        assert sha(V5 / rel) == expected, rel

def prepend(p, content):
    raw = p.read_text()
    if NAME not in raw:
        p.write_text(content + '\n\n' + raw)

protect()
assert json.loads((SOURCE / 'public_new_snapshot/new_checkpoint.json').read_text())['completed']
assert json.loads((SOURCE / 'label_archive/label_checkpoint.json').read_text()).get('finished_utc'), 'Do not copy a live label collection.'
assert json.loads((SOURCE / 'old_details/checkpoint.json').read_text()).get('finished_utc'), 'Do not copy a live detail collection.'
assert (SOURCE / 'README.md').is_file() and (SOURCE / 'completion_summary.json').is_file()
shutil.copytree(SOURCE, OUT, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.tmp', 'staging_new_snapshot_verification.json'))
submanifest_checks = {}
for folder in sorted(p for p in OUT.iterdir() if p.is_dir()):
    assert (folder / 'README.md').is_file(), folder.name
    count = 0
    for listing in folder.rglob('文件_SHA256.csv'):
        for row in csv.DictReader(listing.open(encoding='utf-8-sig')):
            p = listing.parent / row['file']
            assert p.is_file() and p.stat().st_size == int(row['bytes']) and sha(p) == row['sha256'], p
            count += 1
    submanifest_checks[folder.name] = count

summary = json.loads((SOURCE / 'completion_summary.json').read_text())
note = '> 最新[新库53页独立验收与实际标签批次](' + NAME + '/README.md)已发布：539型号/936原样精确记录，两库并集1246；938是去首尾空格口径，519误含空日期。科学版本仍为v1.5。'
prepend(EXPORT / 'README.md', note.replace('](' + NAME, '](v1_5/' + NAME))
for name in ['README.md', 'audit_report.md', '原件补齐与字段勘误修订报告_v1_5_20261009.md']:
    prepend(V5 / name, note)
req = V5 / 'requirements'
prepend(req / '需要用户亲自提供的数据.md', '> [新库完整53页及首批标签与详情](../' + NAME + '/README.md)已自动取证。余下标签/详情仍是自动采集队列，不列为需要你人工找的数据；JX历史电池总能量与必要配置身份材料继续分开入账。')
q = json.loads((req / 'requirements_summary.json').read_text())
q['official_energy_new_complete_20261009'] = {
    'report': '../' + NAME + '/README.md', 'scientific_inputs_changed': False,
    'new_view_pages_complete': 53, 'new_view_rows': 10479,
    'exact_new_models': 539, 'exact_new_records': 936, 'exact_union_models': 1246,
    'new_pdf_batch': summary['labels'], 'old_detail_batch': summary['old_details'],
    'frozen_cycle_gaps_closed': 0, 'jx_core_energy_missing': True,
}
(req / 'requirements_summary.json').write_text(json.dumps(q, ensure_ascii=False, indent=2) + '\n')
inventory(req)
canonical = V5 / 'reconstruction/data_v1_5'
prepend(canonical / 'README.md', '> [本轮新库原件验收及口径订正](../../' + NAME + '/README.md)保存在旁证层；52份科学CSV保持原字节。')
dest = canonical / '文件清单_SHA256.txt'
members = [p for p in files(canonical) if p != dest]
assert len(members) == 58
dest.write_text(''.join(sha(p) + '  ' + p.relative_to(canonical).as_posix() + '\n' for p in members))
prior = V5 / 'energy_registry_20261009'
prepend(prior / 'README.md', '> 后续[53页原字节验收、精确交并集及新增标签](../' + NAME + '/README.md)已完成。本页下文保留上一轮4页新库快照，不代表本轮完整结果；旧快照与ZIP未替换。')
inventory(prior, exclude=('energy_records_and_review_20261009.zip',))

zip_path = OUT / ZIP_NAME
inventory(OUT, exclude=(ZIP_NAME,))
payload = [p for p in files(OUT) if p != zip_path]
prefix = '购置税v1_5_新库完整页与首批标签_20261009'
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for path in payload:
        entry = zipfile.ZipInfo(prefix + '/' + path.relative_to(OUT).as_posix(), (2026, 10, 9, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED; entry.external_attr = 0o100644 << 16
        z.writestr(entry, path.read_bytes(), compresslevel=9)
with zipfile.ZipFile(zip_path) as z:
    assert z.testzip() is None and len(z.infolist()) == len(payload)
    for p in payload:
        assert hashlib.sha256(z.read(prefix + '/' + p.relative_to(OUT).as_posix())).hexdigest() == sha(p)
assert zip_path.stat().st_size < 32 * 1024 * 1024

docs = [EXPORT / 'README.md', V5 / 'README.md', req / '需要用户亲自提供的数据.md', canonical / 'README.md'] + list(OUT.rglob('*.md')) + [prior / 'README.md']
links = 0
for doc in docs:
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', doc.read_text()):
        target = target.strip().strip('<>')
        if urlsplit(target).scheme or target.startswith('#'): continue
        assert (doc.parent / unquote(target.split('#')[0])).resolve().exists(), (doc, target)
        links += 1
protect()
gp = V5 / 'file_manifest.json'
global_manifest = json.loads(gp.read_text())
global_manifest.update(latest_official_energy_complete_evidence_directory=NAME, scientific_csv_bytes_changed=False, original_data_and_source_zips_unchanged=True)
artifacts = {x['file']: x for x in global_manifest['artifacts']}
for rel in [NAME + '/README.md', NAME + '/' + ZIP_NAME]: artifacts.setdefault(rel, {'file': rel})
for rel, row in artifacts.items():
    row.update(bytes=(V5 / rel).stat().st_size, sha256=sha(V5 / rel), github_file_page='https://github.com/lima0531/-/blob/purchase-tax-v1-4-files/v1_5/' + rel)
artifacts[NAME + '/' + ZIP_NAME].update(member_files=len(payload), all_members_crc_and_sha_verified=True, includes_scientific_data_replacement=False, original_file_name=prefix + '.zip')
global_manifest['artifacts'] = list(artifacts.values())
global_manifest['files_excluding_this_manifest'] = [record(p, V5) for p in files(V5) if p != gp]
gp.write_text(json.dumps(global_manifest, ensure_ascii=False, indent=2) + '\n')
proof = {'generated_utc': datetime.now(timezone.utc).isoformat(), 'scientific_csv_count': 52,
         'scientific_csv_unchanged': True, 'six_historical_zips_unchanged': True,
         'submanifest_entries_verified': submanifest_checks, 'canonical_sha_entries': 58,
         'zip_members_verified': len(payload), 'zip_bytes': zip_path.stat().st_size,
         'zip_sha256': sha(zip_path), 'relative_links_verified': links,
         'delivery_manifest_entries': len(global_manifest['files_excluding_this_manifest'])}
(SOURCE / 'staging_new_snapshot_verification.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(proof, ensure_ascii=False))
