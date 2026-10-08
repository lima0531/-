#!/usr/bin/env python3
"""Finalize companion evidence and manifest without changing scientific tables."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'reconstruction/data_v1_5'

copies = {
    'source_recovery/106原件回收清单_v1_5.csv': '原件回收登记/106原件回收清单_v1_5.csv',
    'catalogues/97份目录_独立科学原值枚举7203行.csv': '目录覆盖/97份目录_独立科学原值枚举7203行.csv',
    'catalogues/97份目录_最终逐源参数覆盖.csv': '目录覆盖/97份目录_最终逐源参数覆盖.csv',
    'parameters/380单值不足_原因与保守区间核查.csv': '数值补充核查/380单值不足_原因与保守区间核查.csv',
    'batch64/第64批_SGM6500BEBEV_原文限定字段勘误.csv': '勘误补充/第64批_SGM6500BEBEV_原文限定字段勘误.csv',
    'batch64/SGM6500BEBEV_字段级更正后的参数_证据旁表.csv': '勘误补充/SGM6500BEBEV_字段级更正后的参数_证据旁表.csv',
    'methodology/字段继承建议与逐字段来源.csv': '勘误补充/字段继承建议与逐字段来源.csv',
}
for source, target in copies.items():
    dst = DATA / target
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / source, dst)

old = DATA / '字段说明_版本边界.md'
historic = DATA / '字段说明_版本边界_历史v1_3.md'
if not historic.exists():
    shutil.copyfile(old, historic)
old.write_text('''# v1.5 字段及版本边界

本轮只修正 SGM6500BEBEV 明确条目中的字段勘误承接。原始7203行参数表保持v1.4原字节，分析读取 `研究数据/参数版本_字段勘误生效视图.csv`。源表的空白仍是空白，继承的是已被明确更正关系指定的第62批同一原条目的解析数值。

生效视图保留原记录ID，并增加以下字段：`composition_kind`说明物理记录或字段更正视图；`target_record_id`连接被更正条目；`corrected_fields`和`inherited_fields`列明更正/承接范围；`field_source_record_ids_json`、`field_source_sha256_json`和`field_observation_upper_bounds_json`逐字段登记来源ID、文件SHA与公开观察上界。`correction_scope_verified`仅认证此段更正范围；`original_field_parse_status_json`保留原物理字段解析状态；`effective_values_scope`说明生效计算值的用途。通过来源ID回连同表父条目即可取得原单元格定位。

所有7203行均有字段来源图，只有 `old-text-correction-64-SGM6500BEBEV` 承接第62批 `old-62-Word97--0-7` 的质量和能量。不能将这一规则推广到仅有型号相同的其他记录。第64批的608km从2023-04-17信息集使用，2023年2—3月仍使用502km；2023-12-26的新记录不参与公告前补齐。

当前研究队列3328、冻结基线1991、公告前风险集2805；单值可用2425、单值不足380、两项常规数值阈值均达到1822。2024撤销观察503=风险集内496+风险集外7，撤销后再列入5为子集。成员、6801条资格事件、6873条来源连接与月末状态未变。

原件回收登记闭合106/106历史索引文件（97目录+9历史撤销）。独立科学原值枚举覆盖97目录7203参数行；这不认证互联网来源集合穷尽或全部车辆类别。380不足旁表为300全外包络达标、47至少一项全外包络未达、32联合跨界、1原空字段；公告前原空字段仅JX6550T-M5BEV电池总能量仍待证。区间结果不替代具体配置认证。

读取五档表用 `官方技术清单/五档数值层_逐型号归属与判据.csv`；风险外撤销用 `官方技术清单/2024撤销观察_风险集外型号.csv`。带“2877行”或“8型号”的旧名仅是兼容入口，实际行数分别2805和7。`100份原件_跨目录身份键检查.csv`是前轮既定扫描范围，不能解释为本轮106份全量身份认证。

`potential_event_count`表示可能最后事件候选数；`0001-01-01`是未知下界占位；月末目录状态不能代表当月所有车辆的法律资格。`publish_date_exact`是主管部门现存页面明确登记的公开观察日，不能等同全球首次上线日。第1批精确首发日仍未知。

历史9份撤销语义表3007条出处记录；补采两份历史撤销完整2020行另列，合计5027行并非唯一型号数。官方技术标记是事后信息，不回填公告前特征。目录能量/质量计算密度代理不能替代推荐目录声明密度。配置身份、M1、完整技术、低温、逐车税收和因果识别认证均未增加；认证0表示尚未取得证据。

`README_版本v1_3.md`、`README_版本v1_4.md`及 `字段说明_版本边界_历史v1_3.md`是历史记录，当前口径以本文件和README为准。
''', encoding='utf-8')

readme = DATA / 'README.md'
body = readme.read_text(encoding='utf-8')
body = body.replace('最终原件登记与380不足原因旁表由round5配套核查更新。', '最终原件登记与380不足原因旁表已更新。106/106历史索引原件同字节回收（97目录+9历史撤销），97目录的7203条科学原值独立枚举零差异。380旁表中300全外包络两项达标、47至少一项全外包络未达、32联合跨界、1真实原空字段；该原空字段仅JX6550T-M5BEV第48批电池总能量。2425单值可用型号中217明确标CLTC、2208未标工况。')
readme.write_text(body, encoding='utf-8')

manifest = DATA / '文件清单_SHA256.txt'
files = sorted(p for p in DATA.rglob('*') if p.is_file() and p != manifest)
records = [(hashlib.sha256(p.read_bytes()).hexdigest(), p.relative_to(DATA).as_posix()) for p in files]
manifest.write_text(''.join(f'{sha}  {rel}\n' for sha, rel in records), encoding='utf-8')
for sha, rel in records:
    assert hashlib.sha256((DATA / rel).read_bytes()).hexdigest() == sha
result = {'canonical_data_files': len(files) + 1, 'manifest_entries': len(records), 'all_manifest_entries_verified': True, 'scientific_tables_changed_by_finalizer': False}
(ROOT / 'canonical_manifest_verification_v1_5.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
