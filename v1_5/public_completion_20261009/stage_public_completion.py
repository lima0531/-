#!/usr/bin/env python3
"""Stage public follow-up evidence; preserve every canonical science byte."""
import argparse
import csv
import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--audit-root', type=Path, default=Path('/workspace/purchase_tax_audit'))
p.add_argument('--export-root', type=Path, default=Path('/workspace/file_export_proposal'))
a = p.parse_args()
AUDIT, EXPORT = a.audit_root.resolve(), a.export_root.resolve()
SOURCE, V5 = AUDIT / 'round9', EXPORT / 'v1_5'
NAME = 'public_completion_20261009'
OUT = V5 / NAME
GOLD = json.loads((AUDIT / 'round6/pre_review_scientific_csv_sha256.json').read_text())
ZIP_GOLD = {
    'purchase_tax_data_v1_5.zip': '3fd50d6aa95eca0d8483b5bcc409b4c246b024b1dd707ef8e67d95df84e70f20',
    'purchase_tax_sources_v1_5.zip': '17b10d905721b38526a6fc0191680721bb10dc977e8efbad6a28e2385d0f06a2',
    'review_20261009/review_supplement_20261009.zip': 'd5dfad8e6f2cfd5ae50ef0a76c2e384b5c8e1306a45ca928c96f4fb6ca5bb521',
    'progress_20261009/progress_and_evidence_20261009.zip': '01fe60c3d5418dd1d5c0534c13d0b813a7e15c988e68624f8baf8502eea6c6c1',
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def protected():
    assert len(GOLD) == 52
    for rel, expected in GOLD.items():
        path = V5 / rel
        assert path.stat().st_size == expected['bytes'] and sha(path) == expected['sha256'], rel
    for rel, expected in ZIP_GOLD.items():
        assert sha(V5 / rel) == expected, rel

def files(root):
    return sorted(x for x in root.rglob('*') if x.is_file() and '__pycache__' not in x.parts and 'conversion_inputs' not in x.parts)

def fingerprint(path, root):
    return {'file': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}

def manifest(root, name='文件_SHA256.csv', excluded=()):
    rows = [fingerprint(x, root) for x in files(root) if x != root / name and x.relative_to(root).as_posix() not in excluded]
    with (root / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['file','bytes','sha256']);w.writeheader();w.writerows(rows)
    return len(rows)

def prepend(path, note):
    text = path.read_text()
    if NAME not in text:
        path.write_text(note + '\n\n' + text)

protected()
assert (SOURCE / 'README.md').is_file()
shutil.copytree(SOURCE, OUT, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__','conversion_inputs','staging_public_completion_verification.json'))
sub_checks = {}
for folder in sorted(x for x in OUT.iterdir() if x.is_dir()):
    assert (folder / 'README.md').exists(), folder.name
    checked = 0
    for csv_path in folder.rglob('*SHA*.csv'):
        # Input fingerprints may refer to the wider archive; only verify output inventories here.
        if csv_path.name not in ['文件_SHA256.csv','文件清单_SHA256.csv','文件SHA256清单.csv']:
            continue
        rows = list(csv.DictReader(csv_path.open(encoding='utf-8-sig')))
        for row in rows:
            rel = row.get('file') or row.get('relative_path') or row.get('path')
            target = csv_path.parent / rel
            assert target.is_file(), (str(csv_path),rel)
            assert target.stat().st_size == int(row['bytes']) and sha(target) == row['sha256'], str(target)
            checked += 1
    sub_checks[folder.name] = checked
top_note = '> [本轮公开补查与用户接手清单](v1_5/'+NAME+'/README.md)已发布：JX、36配置、19低温及2208工况均有逐项记录；按企业分组的询证表、真实官方查询入口和交回格式已整理。科学版本仍为v1.5。'
prepend(EXPORT / 'README.md', top_note)
v5_note = '> [本轮公开补查与用户接手清单]('+NAME+'/README.md)记录已查路径、有效证据与仍需原机构提供的材料；[按企业合并的询证表]('+NAME+'/user_handoff/README.md)可直接使用。本轮未替空值猜数，52份规范科学CSV保持原字节，历史发布包均保留。'
for name in ['README.md','audit_report.md','原件补齐与字段勘误修订报告_v1_5_20261009.md']:
    prepend(V5 / name, v5_note)
readme = V5 / 'README.md'
readme.write_text(readme.read_text().replace('私有GitHub网页的', '本分支GitHub网页的'))
req = V5 / 'requirements'
prepend(req / '需要用户亲自提供的数据.md', '> 最新[公开补查结果与可操作交接](../'+NAME+'/README.md)和[逐企业询证清单](../'+NAME+'/user_handoff/README.md)已完成；此前数量总账保留，下列条件需求按研究用途使用。')
req_summary = req / 'requirements_summary.json'
obj = json.loads(req_summary.read_text())
obj['public_completion_20261009'] = {
    'latest_handoff': '../'+NAME+'/user_handoff/README.md',
    'public_checks': '../'+NAME+'/README.md',
    'frozen_scientific_parameters_changed': False,
    'public_sources_not_exhausted_claim': '只认证已列公开路径的实际观察；不声称互联网绝无资料',
}
req_summary.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n')
req_entries = manifest(req)
canonical = V5 / 'reconstruction/data_v1_5'
prepend(canonical / 'README.md', '> [本轮剩余数据公开补查与交接](../../'+NAME+'/README.md)已记录来源覆盖、配置及工况边界；本轮科学CSV均未更改。')
canonical_sha = canonical / '文件清单_SHA256.txt'
canonical_files = [x for x in files(canonical) if x != canonical_sha]
assert len(canonical_files) == 58
canonical_sha.write_text(''.join(sha(x)+'  '+x.relative_to(canonical).as_posix()+'\n' for x in canonical_files))
payload_manifest_entries = manifest(OUT, excluded=('public_completion_and_handoff_20261009.zip',))
payload = files(OUT)
prefix = '购置税v1_5_公开补查与企业询证交接_20261009'
zip_path = OUT / 'public_completion_and_handoff_20261009.zip'
payload = [x for x in payload if x != zip_path]
with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for path in payload:
        info = zipfile.ZipInfo(prefix+'/'+path.relative_to(OUT).as_posix(),(2026,10,9,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,path.read_bytes(),compresslevel=9)
with zipfile.ZipFile(zip_path) as z:
    assert z.testzip() is None and len(z.infolist()) == len(payload)
    for path in payload:
        assert hashlib.sha256(z.read(prefix+'/'+path.relative_to(OUT).as_posix())).hexdigest() == sha(path)
assert zip_path.stat().st_size < 32*1024*1024
shutil.copy2(zip_path,AUDIT.parent/(prefix+'.zip'))
docs = [EXPORT/'README.md',V5/'README.md',V5/'audit_report.md',V5/'原件补齐与字段勘误修订报告_v1_5_20261009.md',req/'需要用户亲自提供的数据.md',canonical/'README.md']+sorted(OUT.rglob('*.md'))
link_count=0
for doc in docs:
    for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)',doc.read_text()):
        target=target.strip().strip('<>')
        if urlsplit(target).scheme or target.startswith('#'):
            continue
        target_path=(doc.parent/unquote(target.split('#')[0])).resolve()
        assert target_path.exists(),(str(doc.relative_to(EXPORT)),target)
        link_count+=1
protected()
global_path=V5/'file_manifest.json'
global_manifest=json.loads(global_path.read_text())
global_manifest.update(latest_public_completion_directory=NAME,scientific_csv_bytes_changed=False,original_data_and_source_zips_unchanged=True)
artifacts={x['file']:x for x in global_manifest['artifacts']}
for rel in [NAME+'/README.md',NAME+'/'+zip_path.name]:
    artifacts.setdefault(rel,{'file':rel})
for rel,row in artifacts.items():
    target=V5/rel
    row.update(bytes=target.stat().st_size,sha256=sha(target),github_file_page='https://github.com/lima0531/-/blob/purchase-tax-v1-4-files/v1_5/'+rel)
artifacts[NAME+'/'+zip_path.name].update(member_files=len(payload),all_members_crc_and_sha_verified=True,includes_scientific_data_replacement=False,original_file_name=prefix+'.zip')
global_manifest['artifacts']=list(artifacts.values())
global_manifest['files_excluding_this_manifest']=[fingerprint(x,V5) for x in files(V5) if x!=global_path]
global_path.write_text(json.dumps(global_manifest,ensure_ascii=False,indent=2)+'\n')
proof={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'scientific_version':'v1.5','scientific_csv_count':52,'scientific_csv_unchanged':True,'historical_four_zip_files_unchanged':True,'canonical_sha_entries':58,'requirements_sha_entries':req_entries,'source_submanifest_entries_verified':sub_checks,'payload_manifest_entries':payload_manifest_entries,'zip_members_verified':len(payload),'zip_bytes':zip_path.stat().st_size,'zip_sha256':sha(zip_path),'active_relative_links_verified':link_count,'delivery_manifest_entries':len(global_manifest['files_excluding_this_manifest']),'excluded_scratch_directories':['__pycache__','public_cycle/conversion_inputs']}
(SOURCE/'staging_public_completion_verification.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(proof,ensure_ascii=False))
