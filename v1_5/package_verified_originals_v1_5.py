#!/usr/bin/env python3
"""Package unchanged historic originals with fingerprint and ZIP verification.

Only writes the new v1.5 source ZIP, its index, and verification result.
All paths inside the archive stay relative to purchase_tax_audit, under
the same prefix as the new main package, so both ZIPs can be merged.
"""
import csv
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASK = ROOT.parent
TARGET = Path('/workspace/购置税项目_完整原件106份及推荐资料_v1_5_20261009.zip')
PREFIX = '购置税项目_原件补齐与修订_v1_5_20261009'
REGISTRY = ROOT / 'source_recovery/106原件回收清单_v1_5.csv'

def sha256(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    files = {}
    with REGISTRY.open(encoding='utf-8-sig') as f:
        registered = list(csv.DictReader(f))
    if len(registered) != 106:
        raise ValueError('Historical registry must contain all 106 original targets')
    for row in registered:
        if row['recovery_status'] != 'sha256_exact':
            raise ValueError('Historical original is unavailable: ' + row['source_file'])
        p = Path(row['recovered_path'])
        rel = str(p.relative_to(TASK))
        if rel in files:
            raise ValueError('Duplicate original path: ' + rel)
        actual_sha = sha256(p)
        if actual_sha != row['source_sha256'] or p.stat().st_size != int(row['source_bytes']):
            raise ValueError('Historic fingerprint differs: ' + row['source_file'])
        if row['recovered_sha256'] != actual_sha or int(row['recovered_bytes']) != p.stat().st_size:
            raise ValueError('Recovery metadata differs: ' + row['source_file'])
        files[rel] = p
    if len(files) != 106:
        raise ValueError('Historical source count differs')
    historical_catalogues = sum(r['scope'] == '目录' for r in registered)
    historical_withdrawals = sum(r['scope'] == '历史撤销' for r in registered)
    if historical_catalogues != 97 or historical_withdrawals != 9:
        raise ValueError('Unexpected historic catalogue/withdrawal scope counts')
    # Compare ancillary source files with their saved acquisition receipts,
    # rather than merely calculating fresh hashes during packaging.
    recommendation_pdfs = sorted((TASK / 'round3/technical').glob('rec*_original.pdf'))
    if len(recommendation_pdfs) != 3:
        raise ValueError('Expected exactly three retained recommendation PDFs')
    ancillary_verified = []
    for p in recommendation_pdfs:
        receipt = p.with_name(p.stem + '_request.json')
        meta = json.loads(receipt.read_text(encoding='utf-8'))
        if meta.get('sha256') != sha256(p) or int(meta['bytes']) != p.stat().st_size:
            raise ValueError('Recommendation source differs from acquisition receipt: ' + p.name)
        files[str(p.relative_to(TASK))] = p
        ancillary_verified.append(dict(file=p.name, receipt=str(receipt.relative_to(TASK)), sha256=meta['sha256']))
    for name in ['batch26_7368842.wps', 'batch26_7368844.docx']:
        p = TASK / 'round3/archive/version_search' / name
        receipt = p.with_name(p.name + '.request.json')
        meta = json.loads(receipt.read_text(encoding='utf-8'))
        if meta.get('sha256') != sha256(p) or int(meta['bytes']) != p.stat().st_size:
            raise ValueError('Alternate byte version differs from acquisition receipt: ' + name)
        files[str(p.relative_to(TASK))] = p
        ancillary_verified.append(dict(file=p.name, receipt=str(receipt.relative_to(TASK)), sha256=meta['sha256']))
    if len(files) != 111:
        raise ValueError('Expected 106 historical + 3 recommendation + 2 alternate source files')
    manifest = [dict(relative_path=rel, bytes=p.stat().st_size, sha256=sha256(p))
                for rel, p in sorted(files.items())]
    instructions = (
        '购置税项目 v1.5 原件包（2026-10-09）\n'
        '包含历史归档同 SHA256 原件 106 份（97 份目录、9 份历史正式撤销），'
        '3 份推荐目录 PDF，以及第26批官方公开的2份异字节比较版本，共111份源文件。\n'
        '用户补交的第1批 PDF 和第64批 DOC 已按历史 SHA256 核验，本包包含这两份；'
        '不再需要寻找这两份文件。其他原件亦与历史指纹逐一核对。\n'
        '和 v1.5 主核查数据包解压至同一个父文件夹，合并同名顶层文件夹'
        '“购置税项目_原件补齐与修订_v1_5_20261009”即可。内部路径保留 round3、round4、round5 等证据位置。\n'
        '原件未重写、转换或改名；转换的 DOCX 和提取文字属于主包核查伴随件。'
        '本包的 SHA256 清单使用相对于顶层文件夹的路径。\n'
        '历史106份目标原件已全部取得，不代表所有互联网目录、补丁或撤销页面在全球范围内已穷尽。'
        '第1批原件的署名日期和政策执行日期不能自动当成原官网首次公开日期；该日期证据边界仍保留。\n'
        '目录同型号和原件哈希不能认证跨目录同配置、M1类别、低温报告或逐车制造及减免税资格；'
        '这些事项须查看主包的材料清单和配置/逐车证明边界。\n'
    )
    with zipfile.ZipFile(TARGET, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for rel, p in sorted(files.items()):
            z.write(p, f'{PREFIX}/{rel}')
        z.writestr(f'{PREFIX}/原件包_SHA256.txt',
                   ''.join(r['sha256'] + '  ' + r['relative_path'] + '\n' for r in manifest))
        z.writestr(f'{PREFIX}/原件包使用说明.txt', instructions)
    with zipfile.ZipFile(TARGET) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP CRC verification failed')
        if len(z.namelist()) != 113 or len(set(z.namelist())) != 113:
            raise ValueError('Expected 111 source members + 2 explanatory members, all unique')
        for row in manifest:
            b = z.read(f"{PREFIX}/{row['relative_path']}")
            if len(b) != row['bytes'] or hashlib.sha256(b).hexdigest() != row['sha256']:
                raise ValueError('ZIP member differs from source: ' + row['relative_path'])
    if TARGET.stat().st_size >= 32 * 1024 * 1024:
        raise ValueError('Source ZIP exceeds 32 MiB artifact limit')
    with (ROOT / '原件分包索引_v1_5.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['relative_path', 'bytes', 'sha256'])
        w.writeheader()
        w.writerows(manifest)
    result = dict(path=str(TARGET), bytes=TARGET.stat().st_size, sha256=sha256(TARGET),
                  prefix=PREFIX, historical_exact_originals=106,
                  historical_catalogues=historical_catalogues,
                  historical_withdrawals=historical_withdrawals,
                  recommendation_pdfs=3, official_alternate_byte_versions=2,
                  source_files=111, zip_members=113,
                  total_uncompressed_source_bytes=sum(r['bytes'] for r in manifest),
                  historical_source_bytes_and_sha_verified=True,
                  ancillary_acquisition_receipt_fingerprints_verified=ancillary_verified,
                  all_members_crc_and_sha_verified=True,
                  original_source_files_modified=False,
                  repository_uploaded=False)
    (ROOT / 'original_package_result_v1_5.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
