#!/usr/bin/env python3
"""Publish scoped evidence and corrected documentation without rewriting science.

Run --prepare, finish any concurrent documentation amendments, then --finalize.
Defaults refer to the existing cloud audit and export checkout.
"""
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

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--audit-root', type=Path, default=Path('/workspace/purchase_tax_audit'))
parser.add_argument('--export-root', type=Path, default=Path('/workspace/file_export_proposal'))
parser.add_argument('--prepare', action='store_true')
parser.add_argument('--finalize', action='store_true')
args = parser.parse_args()
AUDIT, EXPORT = args.audit_root.resolve(), args.export_root.resolve()
SOURCE = AUDIT / 'round8'
V5 = EXPORT / 'v1_5'
PROGRESS = V5 / 'progress_20261009'
GOLDEN = json.loads((AUDIT / 'round6/pre_review_scientific_csv_sha256.json').read_text())
ZIP_HASHES = {
    'purchase_tax_data_v1_5.zip': '3fd50d6aa95eca0d8483b5bcc409b4c246b024b1dd707ef8e67d95df84e70f20',
    'purchase_tax_sources_v1_5.zip': '17b10d905721b38526a6fc0191680721bb10dc977e8efbad6a28e2385d0f06a2',
    'review_20261009/review_supplement_20261009.zip': 'd5dfad8e6f2cfd5ae50ef0a76c2e384b5c8e1306a45ca928c96f4fb6ca5bb521',
}
OLD_SHA = '73b31afdaf90fd5efa32063308a9ac4123b0bf2d86f941abbe3e9c4db09e7a3d'
FINAL_SHA = '1963fd09c4502d60c90a4a4a28660d9236ae19a3d126520c54c4ba5c98a5863d'
CURRENT_SHA = '11e493ec70376fde3b463dcbc701bbda91f2bb7fc94c1a567e41e031a4fb8ce7'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def files(root):
    return sorted(p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts)

def record(path, root):
    return {'file': path.relative_to(root).as_posix(), 'bytes': path.stat().st_size, 'sha256': sha(path)}

def protected():
    assert len(GOLDEN) == 52
    for relative, expected in GOLDEN.items():
        path = V5 / relative
        assert path.stat().st_size == expected['bytes'] and sha(path) == expected['sha256'], relative
    for relative, expected in ZIP_HASHES.items():
        assert sha(V5 / relative) == expected, relative

def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def refresh_csv_manifest(root, name, key='file', excluded=()):
    rows = []
    for path in files(root):
        if path == root / name or path.relative_to(root).as_posix() in excluded:
            continue
        item = record(path, root)
        item[key] = item.pop('file')
        rows.append(item)
    write_csv(root / name, rows, [key, 'bytes', 'sha256'])
    return len(rows)

def prepend(path, marker, note):
    text = path.read_text()
    if marker not in text:
        path.write_text(note + '\n\n' + text)

def replace_once(path, old, new):
    text = path.read_text()
    if old in text:
        path.write_text(text.replace(old, new, 1))
    else:
        assert new in text, path

def prepare():
    protected()
    shutil.copytree(AUDIT / 'round7/legacy_fingerprint', SOURCE / 'legacy_fingerprint', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
    refresh_csv_manifest(SOURCE / 'final_gap_status', '文件_SHA256.csv')
    shutil.copytree(SOURCE, PROGRESS, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', 'staging_progress_verification.json', '文件_SHA256.csv'))
    # The ignore above only applies to this copy; retain exact scoped source manifests.
    for folder, name in [('jx_public_final_pass', '文件_SHA256.csv'),
                         ('final_gap_status', '文件_SHA256.csv')]:
        shutil.copy2(SOURCE / folder / name, PROGRESS / folder / name)
    risk = V5 / 'review_20261009/risk_change'
    (risk / '版本命名核查.md').write_text(f'''# 版本命名与旧2488输入准备数：已定位关键文件

此前未对应的旧轨迹表SHA现已找到：`{OLD_SHA}`，852354字节、3328型号、风险2877、输入准备2488。该具体CSV与已打开精简包、日期v1.2实际文件逐字节一致；历史v1.1两次干净构建记录对应项也都是此全SHA，34组保留指纹一致。此结论认证具体CSV身份，不替未打开的40MB归档补造整包名称或交付标签。

| 构建或证据范围 | 轨迹表SHA前16 | 风险 | 输入准备 |
| --- | --- | ---: | ---: |
| 精简包实际文件、历史v1.1构建记录、日期v1.2实际文件 | `73b31afdaf90fd5e` | 2877 | 2488 |
| 最终v1.3、v1.4实际文件 | `1963fd09c4502d60` | 2805 | 2424 |
| 当前v1.5实际文件 | `11e493ec70376fde` | 2805 | 2425 |

最终v1.3/v1.4全SHA为`{FINAL_SHA}`；当前v1.5为`{CURRENT_SHA}`。若旧SHA文件曾被称为“最终v1.3”，该文件的标签应订正。旧文件精确生成时间没有记载，2026-10-08报告日期不能替代生成时刻。

变化已逐型号闭合：**风险2877−73＋1＝2805；输入准备2488−65＋1＝2424，再＋SGM1＝2425。** 73个风险退出中65个原ready=1、8个原不足；CSA6461FBEV3因第27批错绑日期修正恢复风险及ready。v1.5仅新增SGM6500BEBEV的ready，不改变风险集合。2018来源的65个风险退出与两来源合计65个ready退出是不同集合，分别拆分58＋7与7＋1。

本地v1.3还有仅补73条撤销的2804/2423中间阶段，其摘要记录2026-10-08 14:13:51 UTC、基底data_v1_2；最终2805/2424摘要记录14:45:42.521551 UTC、基底corrected_source_base。两份摘要都记录固定data_v1_3输出目录，中间目录现仅保留摘要、清单和差异，不能称完整中间数据快照还在。

同名历史README经过v1.4保留到v1.5；网页现已添加范围注释，主数据及原发布ZIP保持不变。原[命名核查JSON](version_label_audit.json)保留第一次核查的时间和源指纹，并追加本轮对应结果；原不确定项U01只对关键CSV关闭，整包归档身份仍未由单文件证明。完整原件SHA、75型号逐源对照和20输入保护结果见[旧构建指纹闭合](../../progress_20261009/legacy_fingerprint/README.md)。
''')
    old = '**用户所称另一份“v1.3”尚未与本地某个构建指纹建立唯一对应**；原compact README自称从v1.1提取，也不能据此替用户另一份包定版本。详见[版本命名核查.md](版本命名核查.md)。'
    new = '本轮已将用户指出的旧轨迹表完整SHA `'+OLD_SHA+'` 对应到精简包、历史v1.1构建记录及日期v1.2实际文件：风险2877、ready2488。准备数变化为2488−65＋1＝2424，再＋SGM1＝2425；关键CSV身份已闭合，整包标签和旧精确生成时刻仍不能由单文件推断。详见[版本命名核查.md](版本命名核查.md)及[75型号指纹与逐源对照](../../progress_20261009/legacy_fingerprint/README.md)。'
    replace_once(risk / 'README.md', old, new)
    review = V5 / 'review_20261009/README.md'
    old = '你提到的另一个“v1.3／2877”标签，当前提供的复核报告未包含该构建的完整生成指纹，不能仅凭标签把它认定为最终2805构建。同名历史说明现在明确标注其范围；精确对应应使用输入指纹、生成记录及风险集成员差集。'
    new = '本轮追加核查已定位你指出的旧轨迹表全SHA `'+OLD_SHA+'`：与精简包及日期v1.2实际文件一致，历史v1.1构建记录也对应此指纹。该文件风险2877、ready2488，与最终v1.3的2805/2424确为不同构建。准备数量链为2488−65＋1＝2424，再＋SGM1＝2425，见[旧构建指纹及75型号证据](../progress_20261009/legacy_fingerprint/README.md)。具体CSV身份已闭合；未打开的整包名称及旧精确生成时刻不凭单文件推断。'
    replace_once(review, old, new)
    replace_once(review, '当前2425单值可用、380不足、1822两项达标和2805风险集均不变；材料待补清单也不变。',
                 '当前2425单值可用、380不足、1822两项达标和2805风险集均不变。原补充ZIP保留当轮快照；本轮已另补标准登记字段和剩余台账，见[最新进度与补证](../progress_20261009/README.md)。')
    audit_json = risk / 'version_label_audit.json'
    obj = json.loads(audit_json.read_text())
    for row in obj['not_established']:
        if row['claim_id'] == 'U01':
            row.update(followup_status='resolved_for_specific_csv_only',
                       followup_reason='旧完整SHA已匹配精简包、v1.2实际文件及v1.1构建记录；不认证未打开整包。')
    obj['followup_20261009'] = {
        'scope': '具体轨迹CSV指纹与逐型号risk/ready变化；第一次审计快照保留',
        'legacy_csv_sha256': OLD_SHA, 'legacy_risk': 2877, 'legacy_numeric_ready': 2488,
        'final_v1_3_and_v1_4_csv_sha256': FINAL_SHA, 'final_risk': 2805, 'final_numeric_ready': 2424,
        'v1_5_csv_sha256': CURRENT_SHA, 'v1_5_numeric_ready': 2425,
        'risk_change_equation': '2877-73+1=2805', 'ready_change_equation': '2488-65+1=2424;2424+1=2425',
        'evidence': '../../progress_20261009/legacy_fingerprint/legacy_fingerprint_summary.json',
        'whole_unopened_archive_identity_established': False, 'legacy_exact_generation_time_established': False,
    }
    obj['naming_for_followup'] = '引用具体构建应注明全SHA及阶段；旧CSV已对应2877/2488构建，不再称未对应；整包交付标签与旧精确生成时刻仍未由此证明。'
    audit_json.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    prepend(EXPORT / 'README.md', '最新剩余总账', '> 2026-10-09[最新剩余总账与时间判断](v1_5/progress_20261009/README.md)已发布：历史原件缺0份，风险集真实原空为JX的1型号1字段；标准4项登记补齐，旧2488指纹与变动链已对应。[本轮补证包](v1_5/progress_20261009/progress_and_evidence_20261009.zip)含总账、官方原件和核查证据；科学数据仍为v1.5。')
    note = '> 2026-10-09[最新剩余总账与时间判断](progress_20261009/README.md)：原件缺0份，JX真实原空1字段；配置、工况、低温和逐车按用途计数，资料取得日不作保证。标准4项登记已补齐，旧2488轨迹指纹已定位。本轮只补证据和订正说明，52份规范科学CSV及原两个数据ZIP字节未变。[新补证包](progress_20261009/progress_and_evidence_20261009.zip)可单独下载。'
    for name in ['README.md', 'audit_report.md', '原件补齐与字段勘误修订报告_v1_5_20261009.md']:
        prepend(V5 / name, '最新剩余总账', note)
    canonical = V5 / 'reconstruction/data_v1_5'
    prepend(canonical / 'README_版本v1_3.md', '旧2488文件全SHA',
            '> 追加指纹订正（2026-10-09）：旧2488文件全SHA `'+OLD_SHA+'` 对应精简包、v1.1历史构建记录和日期v1.2实际文件；最终v1.3/v1.4全SHA `'+FINAL_SHA+'`。输入准备变化为2488−65＋CSA1＝2424，再＋SGM1＝2425。详见[具体CSV指纹闭合](../../progress_20261009/legacy_fingerprint/README.md)，不由单文件推定未打开整包身份或旧精确生成时间。')
    prepend(canonical / 'README.md', '最新剩余总账', '> [最新剩余总账与时间判断](../../progress_20261009/README.md)已按v1.5对象去重；本轮未改科学CSV。历史原发布ZIP内的说明保留发布快照，当前订正以网页说明为准。')
    protected()

def verify_csv_manifest(root, name):
    rows = list(csv.DictReader((root / name).open(encoding='utf-8-sig')))
    for row in rows:
        relative = row.get('file') or row.get('path') or row.get('relative_path')
        path = root / relative
        assert path.stat().st_size == int(row['bytes']) and sha(path) == row['sha256'], str(path)
    return len(rows)

def finalize():
    protected()
    canonical = V5 / 'reconstruction/data_v1_5'
    sha_file = canonical / '文件清单_SHA256.txt'
    entries = [p for p in files(canonical) if p != sha_file]
    assert len(entries) == 58
    sha_file.write_text(''.join(sha(p) + '  ' + p.relative_to(canonical).as_posix() + '\n' for p in entries))
    refresh_csv_manifest(V5 / 'review_20261009/risk_change', '文件清单_SHA256.csv', 'path')
    refresh_csv_manifest(V5 / 'requirements', '文件_SHA256.csv')
    refresh_csv_manifest(PROGRESS, '文件_SHA256.csv', excluded=('progress_and_evidence_20261009.zip',))
    sub_manifests = {}
    for folder, name in [('legacy_fingerprint', '文件清单_SHA256.csv'), ('jx_public_final_pass', '文件_SHA256.csv'),
                         ('public_archive_final_pass', '文件SHA256清单.csv'), ('final_gap_status', '文件_SHA256.csv')]:
        sub_manifests[folder] = verify_csv_manifest(PROGRESS / folder, name)
    payload = [p for p in files(PROGRESS) if p.name != 'progress_and_evidence_20261009.zip']
    zip_path = PROGRESS / 'progress_and_evidence_20261009.zip'
    prefix = '购置税v1_5_剩余数据总账与公开补证_20261009'
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in payload:
            info = zipfile.ZipInfo(prefix + '/' + path.relative_to(PROGRESS).as_posix(), (2026, 10, 9, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, path.read_bytes(), compresslevel=9)
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None
        assert len(z.infolist()) == len(payload)
        for path in payload:
            assert hashlib.sha256(z.read(prefix + '/' + path.relative_to(PROGRESS).as_posix())).hexdigest() == sha(path)
    assert zip_path.stat().st_size < 32 * 1024 * 1024
    shutil.copy2(zip_path, AUDIT.parent / (prefix + '.zip'))
    # Check only current entry points and authored supplement links, not archived historical prose.
    active = [EXPORT / 'README.md', V5 / 'README.md', V5 / 'audit_report.md',
              V5 / '原件补齐与字段勘误修订报告_v1_5_20261009.md', V5 / 'requirements/需要用户亲自提供的数据.md',
              V5 / 'review_20261009/README.md', V5 / 'review_20261009/risk_change/README.md',
              V5 / 'review_20261009/risk_change/版本命名核查.md', canonical / 'README.md', canonical / 'README_版本v1_3.md']
    active += sorted(PROGRESS.rglob('*.md'))
    links = []
    for doc in active:
        for target in re.findall(r'(?<!!)\[[^\]]+\]\(([^)]+)\)', doc.read_text()):
            target = target.strip().strip('<>')
            if urlsplit(target).scheme or target.startswith('#'):
                continue
            path = (doc.parent / unquote(target.split('#')[0])).resolve()
            assert path.exists(), (str(doc.relative_to(EXPORT)), target)
            links.append({'document': doc.relative_to(EXPORT).as_posix(), 'target': target})
    protected()
    manifest_path = V5 / 'file_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest.update(latest_progress_directory='progress_20261009', scientific_csv_bytes_changed=False,
                    original_data_and_source_zips_unchanged=True)
    artifacts = {a['file']: a for a in manifest['artifacts']}
    for relative in ['progress_20261009/progress_and_evidence_20261009.zip', 'progress_20261009/README.md']:
        artifacts.setdefault(relative, {'file': relative})
    for relative, item in artifacts.items():
        path = V5 / relative
        item.update(bytes=path.stat().st_size, sha256=sha(path),
                    github_file_page='https://github.com/lima0531/-/blob/purchase-tax-v1-4-files/v1_5/' + relative)
    artifacts['progress_20261009/progress_and_evidence_20261009.zip'].update(
        original_file_name=prefix+'.zip', member_files=len(payload), all_members_crc_and_sha_verified=True,
        includes_scientific_data_replacement=False)
    manifest['artifacts'] = list(artifacts.values())
    manifest['files_excluding_this_manifest'] = [record(p, V5) for p in files(V5) if p != manifest_path]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    proof = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'scientific_version': 'v1.5',
             'protected_scientific_csv_files': len(GOLDEN), 'all_scientific_csv_bytes_unchanged': True,
             'both_original_zips_byte_unchanged': True, 'historical_review_zip_unchanged': True,
             'canonical_sha_entries_verified': len(entries),
             'requirements_sha_entries_verified': verify_csv_manifest(V5 / 'requirements', '文件_SHA256.csv'),
             'risk_change_sha_entries_verified': verify_csv_manifest(V5 / 'review_20261009/risk_change', '文件清单_SHA256.csv'),
             'progress_sha_entries_verified': verify_csv_manifest(PROGRESS, '文件_SHA256.csv'),
             'source_submanifest_entries_verified': sub_manifests, 'active_relative_links_verified': len(links),
             'zip_members_verified': len(payload), 'zip_bytes': zip_path.stat().st_size, 'zip_sha256': sha(zip_path),
             'delivery_manifest_entries_verified': len(manifest['files_excluding_this_manifest']), 'links': links}
    (SOURCE / 'staging_progress_verification.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in proof.items() if k != 'links'}, ensure_ascii=False))

assert args.prepare or args.finalize, 'Select --prepare or --finalize'
if args.prepare:
    prepare()
if args.finalize:
    finalize()
