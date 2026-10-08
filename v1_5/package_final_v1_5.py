#!/usr/bin/env python3
"""Package v1.5 with immutable prior evidence; verify every ZIP member."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PREFIX = '购置税项目_原件补齐与修订_v1_5_20261009'
TARGET = Path('/workspace') / (PREFIX + '.zip')
PREVIOUS = Path('/workspace/购置税项目_核查收尾_v1_4_20261008.zip')
EXPECTED_PREVIOUS_SHA = '4bf05256dc2b3802e84dd2d8746ccd431b7f64950bb087b13daeb6cbad005a19'
SKIP = {'core_package_result_v1_5.json', 'file_manifest.json', 'github_publication_verification.json'}

def digest(content):
    return hashlib.sha256(content).hexdigest()

manifest = []
names = set()
def add(z, relative, content):
    assert relative not in names, relative
    assert not relative.startswith('/') and '..' not in Path(relative).parts
    names.add(relative)
    z.writestr(PREFIX + '/' + relative, content)
    manifest.append({'relative_path': relative, 'bytes': len(content), 'sha256': digest(content)})

assert digest(PREVIOUS.read_bytes()) == EXPECTED_PREVIOUS_SHA
assert (ROOT / '原件补齐与字段勘误修订报告_v1_5_20261009.md').is_file()
with zipfile.ZipFile(TARGET, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    with zipfile.ZipFile(PREVIOUS) as prior:
        assert prior.testzip() is None
        for info in prior.infolist():
            if info.is_dir():
                continue
            relative = info.filename.split('/', 1)[1]
            if relative in {'README.md', '交付文件_SHA256.txt'}:
                continue
            add(z, relative, prior.read(info.filename))
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts:
            continue
        relative = p.relative_to(ROOT).as_posix()
        if relative in SKIP:
            continue
        add(z, 'round5/' + relative, p.read_bytes())
    add(z, 'README.md', '''# 购置税项目 v1.5

从 [round5/README.md](round5/README.md) 开始，当前规范研究数据是 round5/reconstruction/data_v1_5。round3、round4保留前轮证据和基准；input保留未经修改的精简输入ZIP。当前字段更正只作用于有明确原文指定的SGM6500BEBEV条目，不把同型号不同目录记录自动拼成同配置。

106份历史索引原件现已齐全。完整版原件见《购置税项目_完整原件106份及推荐资料_v1_5_20261009.zip》，两包解压到同一父目录并合并同名顶层文件夹。旧版仍缺两原件或381不足的记录属于历史结论，请按v1.5当前报告读取。

交付文件_SHA256.txt逐文件登记指纹。原件包含106历史原件、3推荐PDF、2官方异字节版本；本主包还保留此前补采历史撤销等证据。原始参数表完整保留，科学计算读取新增字段勘误生效视图。
'''.encode('utf-8'))
    z.writestr(PREFIX + '/交付文件_SHA256.txt', ''.join(r['sha256'] + '  ' + r['relative_path'] + '\n' for r in manifest))
with zipfile.ZipFile(TARGET) as z:
    assert z.testzip() is None
    assert len(z.namelist()) == len(manifest) + 1
    for r in manifest:
        content = z.read(PREFIX + '/' + r['relative_path'])
        assert len(content) == r['bytes'] and digest(content) == r['sha256'], r['relative_path']
assert TARGET.stat().st_size < 32 * 1024 * 1024
result = {'path': str(TARGET), 'bytes': TARGET.stat().st_size, 'sha256': digest(TARGET.read_bytes()), 'files': len(manifest) + 1, 'all_members_crc_and_sha_verified': True, 'original_input_preserved': True, 'canonical_data_root': PREFIX + '/round5/reconstruction/data_v1_5', 'previous_v1_4_package_sha256': EXPECTED_PREVIOUS_SHA}
(ROOT / 'core_package_result_v1_5.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
