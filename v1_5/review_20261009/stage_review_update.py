#!/usr/bin/env python3
"""Stage scoped documentation updates and a small, independently hashed supplement."""
import csv
import hashlib
import json
import re
import shutil
import urllib.parse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = Path('/workspace/file_export_proposal')
ACTIVE = REPO / 'v1_5'
DEST = ACTIVE / 'review_20261009'
ZIP = Path('/workspace/购置税v1_5_复核说明补充_20261009.zip')
PREFIX = ZIP.stem

def sha(content):
    return hashlib.sha256(content).hexdigest()

assert (ROOT / 'batch64_boundary/README.md').is_file()
assert (ROOT / 'batch64_independent/README.md').is_file()
assert (ROOT / 'risk_change/README.md').is_file()
assert not DEST.exists(), 'New supplement directory required'
prior_manifest = json.loads((ACTIVE / 'file_manifest.json').read_text())
prior_artifacts = {r['file']: r for r in prior_manifest['artifacts']}
golden = json.loads((ROOT / 'pre_review_scientific_csv_sha256.json').read_text())
for rel, record in golden.items():
    p = ACTIVE / rel
    assert sha(p.read_bytes()) == record['sha256'] and p.stat().st_size == record['bytes']
for name in ['purchase_tax_data_v1_5.zip', 'purchase_tax_sources_v1_5.zip']:
    p = ACTIVE / name
    assert sha(p.read_bytes()) == prior_artifacts[name]['sha256']

manifest = []
excluded = {'supplement_package_result.json', 'staging_review_verification.json'}
with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.relative_to(ROOT).as_posix() in excluded:
            continue
        rel = p.relative_to(ROOT).as_posix()
        content = p.read_bytes()
        z.writestr(PREFIX + '/' + rel, content)
        manifest.append({'file': rel, 'bytes': len(content), 'sha256': sha(content)})
    z.writestr(PREFIX + '/补充包文件_SHA256.txt', ''.join(r['sha256'] + '  ' + r['file'] + '\n' for r in manifest))
with zipfile.ZipFile(ZIP) as z:
    assert z.testzip() is None
    for r in manifest:
        content = z.read(PREFIX + '/' + r['file'])
        assert sha(content) == r['sha256'] and len(content) == r['bytes']
package = {'file': 'review_20261009/review_supplement_20261009.zip', 'original_file_name': ZIP.name, 'bytes': ZIP.stat().st_size, 'sha256': sha(ZIP.read_bytes()), 'member_files': len(manifest) + 1, 'all_members_crc_and_sha_verified': True, 'includes_scientific_data_replacement': False}
(ROOT / 'supplement_package_result.json').write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding='utf-8')
shutil.copytree(ROOT, DEST, ignore=shutil.ignore_patterns('__pycache__', 'staging_review_verification.json'))
shutil.copyfile(ZIP, DEST / 'review_supplement_20261009.zip')

notice = '''> 2026-10-09复核说明：这里的“40行”指第64批目录表的40条数据，另外1条SGM文字勘误也已核查，本小节共有41条参数记录。首表0基table0为1表头＋40数据，下一张0基table1是客车表，1表头＋7数据。原两个ZIP保留构建时字节；本次新增边界和历史变更说明，科学CSV未改。详见[本轮复核说明](review_20261009/README.md)。\n\n'''
for rel in ['audit_report.md', '原件补齐与字段勘误修订报告_v1_5_20261009.md']:
    p = ACTIVE / rel
    original = p.read_text(encoding='utf-8')
    p.write_text(notice + original, encoding='utf-8')

batch = ACTIVE / 'batch64/README.md'
original = batch.read_text(encoding='utf-8')
addition = '''## 2026-10-09追加：表号、物理行与记录计数\n\n本页所称“全部40行”均指40条**目录表数据**，不包含表头，也不包含随后独立的1条SGM文字勘误。本小节合计41条参数记录（40表格＋1勘误），两种出处均已核查。新转换DOCX的0基table0位于正文child7，41物理行＝1表头＋40数据；0基table1位于child11，是“（二）客车”，8物理行＝1表头＋7客车，属于范围外。旧提取器的`OOXML table=1`使用1基表号，对应这里的0基table0。\n\n首末乘用车型为JWEV2WD和NEQ6470BEVS61，本地转换的PDF阅读衍生物序号连续1—40；SGM独立勘误位于cell410及DOCX正文child8，下个类别标题位于child10。本次未复现“27＋14”两乘用表结构，不能判定另一派生文件的分页方式；同SHA原DOC的章节数据已全部覆盖，无漏核13条。详见[完整边界和逐行核查](../review_20261009/batch64_boundary/README.md)及[另一条独立读取路径](../review_20261009/batch64_independent/README.md)。\n\n'''
batch.write_text(addition + original, encoding='utf-8')

readme = ACTIVE / 'README.md'
readme.write_text('''> 2026-10-09已追加[独立复核意见的核验与说明](review_20261009/README.md)：第64批为40条目录表数据＋1文字勘误；历史风险集变化为2877−73＋1＝2805。科学数据和两个原ZIP保持字节不变，新增说明可单独下载。\n\n''' + readme.read_text(encoding='utf-8'), encoding='utf-8')
historical = ACTIVE / 'reconstruction/data_v1_5/README_版本v1_3.md'
historical.write_text('''> 历史范围注释（2026-10-09）：本文件说明的是**历史补漏及错批日期修正后的最终v1.3构建**，风险集2805、ready2424；不是原上传2877风险口径，也不是仅补73条撤销后的中间2804构建。两步净变化为2877−73＋1＝2805，增加的1个是CSA6461FBEV3恢复在册。生成记录、逐型号差集和来源见[风险集变更链](../../review_20261009/risk_change/README.md)。v1.5沿用同一风险集合，仅将SGM数值ready修复为1，当前ready2425。历史名称不能代替输入指纹和生成记录。\n\n''' + historical.read_text(encoding='utf-8'), encoding='utf-8')
current_data_readme = ACTIVE / 'reconstruction/data_v1_5/README.md'
current_data_readme.write_text('''> 2026-10-09追加[风险集变更来源链](../../review_20261009/risk_change/README.md)及[第64批计数边界](../../review_20261009/batch64_boundary/README.md)。本次只追加说明，科学CSV与v1.5构建逐字节相同。\n\n''' + current_data_readme.read_text(encoding='utf-8'), encoding='utf-8')

repo_readme = REPO / 'README.md'
repo_readme.write_text('''> 最新说明补充：2026-10-09已核完[第64批40／41计数及历史风险集变化](v1_5/review_20261009/README.md)。[小补充包](v1_5/review_20261009/review_supplement_20261009.zip)只含说明与新增核查证据，原两个大ZIP无须重新下载。科学数据仍为v1.5。\n\n''' + repo_readme.read_text(encoding='utf-8'), encoding='utf-8')

# Refresh the batch evidence manifest only for files already covered by it.
batch_manifest = ACTIVE / 'batch64/输出文件_SHA256.csv'
rows = list(csv.DictReader(batch_manifest.open(encoding='utf-8-sig')))
for row in rows:
    name = row.get('file') or row.get('relative_path') or row.get('filename') or row.get('file_name')
    assert name, row
    p = batch_manifest.parent / name
    row['sha256'] = sha(p.read_bytes())
    if 'bytes' in row:
        row['bytes'] = str(p.stat().st_size)
with batch_manifest.open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

data_root = ACTIVE / 'reconstruction/data_v1_5'
data_manifest = data_root / '文件清单_SHA256.txt'
data_files = sorted(p for p in data_root.rglob('*') if p.is_file() and p != data_manifest)
data_manifest.write_text(''.join(sha(p.read_bytes()) + '  ' + p.relative_to(data_root).as_posix() + '\n' for p in data_files), encoding='utf-8')

artifacts = []
for prior in prior_manifest['artifacts']:
    row = dict(prior)
    p = ACTIVE / row['file']
    row['bytes'], row['sha256'] = p.stat().st_size, sha(p.read_bytes())
    artifacts.append(row)
artifacts.append({**package, 'github_file_page': 'https://github.com/lima0531/-/blob/purchase-tax-v1-4-files/v1_5/' + package['file']})
inventory = [{'file': p.relative_to(ACTIVE).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())} for p in sorted(ACTIVE.rglob('*')) if p.is_file() and p != ACTIVE / 'file_manifest.json']
(ACTIVE / 'file_manifest.json').write_text(json.dumps({'version': 'v1.5', 'documentation_supplement_date': '2026-10-09', 'scientific_csv_bytes_changed': False, 'original_data_and_source_zips_unchanged': True, 'artifacts': artifacts, 'files_excluding_this_manifest': inventory}, ensure_ascii=False, indent=2), encoding='utf-8')

links = []
docs = [REPO / 'README.md', ACTIVE / 'README.md', ACTIVE / 'audit_report.md', batch, historical, current_data_readme, ACTIVE / 'requirements/需要用户亲自提供的数据.md'] + list(DEST.rglob('*.md'))
for p in docs:
    for raw in re.findall(r'\]\(([^)]+)\)', p.read_text(encoding='utf-8')):
        if raw.startswith(('https://', 'http://', '#')):
            continue
        target = (p.parent / urllib.parse.unquote(raw.split('#', 1)[0])).resolve()
        assert target.is_file(), (p, raw)
        links.append((p.relative_to(REPO).as_posix(), target.relative_to(REPO).as_posix()))
for rel, record in golden.items():
    assert sha((ACTIVE / rel).read_bytes()) == record['sha256']
for name in ['purchase_tax_data_v1_5.zip', 'purchase_tax_sources_v1_5.zip']:
    assert sha((ACTIVE / name).read_bytes()) == prior_artifacts[name]['sha256']
result = {'protected_scientific_csv_files': len(golden), 'all_scientific_csv_bytes_unchanged': True, 'both_original_zips_byte_unchanged': True, 'active_relative_links_verified': len(links), 'data_sha_entries_verified': len(data_files), 'batch_manifest_entries_refreshed': len(rows), 'supplement': package}
(ROOT / 'staging_review_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
