#!/usr/bin/env python3
"""Write status from saved evidence, including partial collection counts."""
import csv, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def read(rel): return json.loads((ROOT / rel).read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
analysis = read('new_snapshot_analysis/summary.json')
label = read('label_archive/label_checkpoint.json')
old = read('old_details/checkpoint.json')
candidate = read('label_archive/whitespace_candidates/label_checkpoint.json')
assert label.get('finished_utc') and old.get('finished_utc')
assert candidate.get('finished_utc') and candidate['completed'] and candidate['accepted_pdfs'] == 2
summary = {
    'generated_utc': datetime.now(timezone.utc).isoformat(),
    'scientific_version': 'v1.5', 'source_scientific_csv_bytes_changed': False,
    'new_public_view': analysis['source_view'],
    'new_page_bytes_matching_user_manifest': 53,
    'exact_models': {'new': 539, 'old': 1233, 'intersection': 526, 'union': 1246,
                     'new_only': 13, 'old_only': 707, 'no_match_in_observed_views': 962,
                     'union_increase_vs_previous_round': 12},
    'exact_records': {'new': 936, 'old': 4497, 'combined': 5433},
    'labels': {'fixed_exact_tasks': 936, 'accepted_pdfs': label['accepted_pdfs'],
               'remaining_exact_tasks': 936 - label['accepted_pdfs'],
               'completed': label['completed'], 'stop_reason': label['stop_reason'],
               'whitespace_candidate_tasks': 2,
               'candidate_finished_separately_not_added_to_exact': True},
    'old_details': {'fixed_applyId_tasks': 4497, 'accepted_records': old['accepted_records'],
                    'remaining_tasks': old['remaining_fixed_queue_records'],
                    'completed': old['entire_fixed_queue_complete'],
                    'stop_reason': old['stop_reason']},
    'user_claim_diagnostics': {
        'raw_string_exact': {'models': 539, 'records': 936, 'valid_pre_cutoff_issueDate': 458},
        'trim_only_candidates': {'models': 539, 'records': 938, 'valid_pre_cutoff_issueDate': 460,
                                 'empty_issueDate': 59},
        'nfkc_remove_whitespace_only_candidates': {'models': 545, 'records': 961},
        'nfkc_remove_whitespace_and_uppercase_candidates': {'models': 566, 'records': 1087},
        'invalid_empty_date_string_comparison_can_reproduce_519': True,
        'producer_actual_code_or_request_time_authenticated': False,
        'complete_delivered_payload_identity_now_verified': True,
    },
    'remaining_core_and_conditional_evidence': {
        'historical_originals_missing': 0, 'true_original_blank_field_models': 1,
        'blank_field_model': 'JX6550T-M5BEV', 'blank_field': '历史配置电池组总能量',
        'original_unmarked_frozen_cycle_models': 2208, 'frozen_cycle_gaps_closed_this_round': 0,
        'conditional_configuration_refinement_items': 36,
        'conditional_identity_versions': 285, 'conditional_low_temperature_versions': 19,
        'conditional_reapplication_models': 92, 'mixed_grains_must_not_be_summed': True,
    },
    'metadata_match_is_not_configuration_or_historical_publication_certification': True,
    'producer_log_bytes_and_10479_records_now_verified': True,
    'producer_per_request_times_and_fresh_request_count_not_verified': True,
}
(ROOT / 'completion_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
n, m = label['accepted_pdfs'], old['accepted_records']
(ROOT / 'README.md').write_text(f'''# 新库完整原页验收、口径订正与实际原件批次

更新：2026-10-09（北京时间）。本环境已正常匿名补取新库53/53页、10,479行，**全部53份原响应的SHA256和大小与用户交来的清单一致**。旧库47页、9,336行也按成功尝试重新核验通过。两个独立实现的交并集和计数一致。

本轮还实取并保存了**{n}份精确命中标签PDF、2份前导空格候选PDF，以及{m}条旧库详情**。这两个原件采集批次按预定复核阶段暂停；不是访问拒绝、不是全部采集完成。各原件均有HTTP收据、原字节、SHA、来源位置和实际观察时间。完整进度以[机器摘要](completion_summary.json)及各采集checkpoint为准。

## 需要纠正的三个数字

| 口径 | 型号 | 记录／日期 |
|---|---:|---:|
| 固定2208名单，原字符串精确命中 | 539 | 936记录，458个有效冻结日前issueDate |
| 仅去首尾空格的候选 | 539 | 938记录，460个有效冻结日前issueDate |
| NFKC＋删除Unicode空白候选 | 545 | 961记录 |
| 在上一行基础上再转大写的候选 | 566 | 1087记录 |

两条增加的记录原型号是` BMW6462AAEV`、` BMW6462ABEV`，均带前导空格。原字符串与规范化候选分开保留。938并不等于936条原样精确匹配；566/1087需要额外的大小写折叠才能复现，不能只写“NFKC＋去空白”。

**519不能作为有效历史日期数量**：trim候选中实际有效冻结日前日期460，另59条issueDate为空；把空值转成空字符串也参加日期字符串比较，能复现460＋59＝519。我们未拿到对方代码，故只说明这个操作能复现数字，不断言其实际程序一定如此。issueDate的制度含义和历史首次公开日期仍未认证。

## 两库并集与实际新增

旧库1233，新库539，重合526，**并集1246**；仅新库13，仅旧库707；相对上一轮1234并集真正增加**12型号**。539−3＝536只是新库的命中增量，不是两库并集增量。

另962目标在这两套当前指定公开筛选视图没有原样精确匹配；不等于官网其他资料或历史记录都不存在。全10,479行有10,476个uuid，但全行哈希全部唯一：3组同uuid的不同状态行保留。475型号存在标准、工况或数值取值集合差异线索，需逐版本核对，不能直接认定同配置矛盾。

## 还差什么、规模有多大

| 项目 | 已取得／已完成 | 本轮后待取 |
|---|---:|---:|
| 历史目录及撤销原件 | 106份 | 0份 |
| 新库指定筛选视图 | 53页、10479行 | 0页 |
| 旧库指定筛选视图 | 47页、9336行 | 0页 |
| 原样精确命中新标签 | {n}份／936任务 | {936-n}份自动任务 |
| 前导空格候选标签 | 2份／2任务 | 0份；不并入精确口径 |
| 旧库匹配applyId详情 | {m}条／4497任务 | {4497-m}条自动任务 |
| 真正的原表空能量字段 | 0项补齐 | JX6550T-M5BEV，1型号1字段 |

表中标签与详情是本轮清楚界定的可自动采集队列，不列作需要你手找的数据。当前标签实取约5秒/份（含节奏）；剩余标签约70分钟级。旧详情至少需2.5小时的最低请求节奏，实际还取决于响应延迟，完整自动资料预计数小时，不能承诺全部科学缺口在这个时间内闭合。复核批次与真正无法取得的项分开报告，不将人为阶段暂停说成“找不到”。

主数据的2805风险、2425数值可用、380单值不足仍保持原值；380不等于380个原表空字段。冻结点未标工况的2208型号也未因元数据命中直接扣减。已有标签中的2017/2021标准按各自PDF原文登记；同型号、相同续航或整备质量都不足以自动认证税目录配置身份。首100份中40份有明确NEDC主句、10份有明确CLTC主句、7份仅泛称新的中国工况、43份无明确工况。这些原句另存旁表，不能由2017标准自动推NEDC或由2021推CLTC。

需要你向企业／检测机构索取的硬缺项仍是JX第48批历史配置的电池组总能量及能量—电池版本—配置对应证明：[既有索取模板](../progress_20261009/jx_public_final_pass/向企业索取材料_文本模板.md)。36个配置细化项、285个身份版本、19个低温版本、92个再申请型号是按研究用途触发的条件证据，单位和范围不同，不能加总成“还缺多少条”；先完成自动证据筛选再收窄企业索取范围。

## 来源和未验收的第三方声明

最初附件是3份摘要／清单；后续仓库提交3cb9150已补交完整7文件。解压后全部58项payload的原SHA和57,291,686字节已验收，10479条records逐行位置及原字段和两份53行日志也已验收，见[完整交付验收](provider_delivery_review/README.md)。日志缺少逐请求时间、复用或失败尝试标记，仍不能认证其52/53次本轮新网络请求或“13:0x”采集时间。清单列58件payload，包含清单应为59件；用户所述57.3 MB是十进制约数。第10页首轮503/95字节，第17页首轮实际TimeoutError无响应，均采用已核验的attempt02。详见[声明与身份审查](independent_manifest_review/README.md)。

原页和每条标签／详情各有自己的观测时间；不同轮次不得合并成同一原子事务快照或历史时间序列。全52份科学CSV和6个历史ZIP均保护原指纹。

## 查看与继续采集

- [用户3件原文](user_submitted/README.md)
- [后续完整7文件、58项payload验收](provider_delivery_review/README.md)
- [新库53页原件及收据](public_new_snapshot/README.md)
- [旧库重试与4497固定来源](independent_old_review/README.md)
- [交并集、版本线索及固定下载队列](new_snapshot_analysis/README.md)
- [标签原件、逐PDF标准与剩余队列](label_archive/README.md)
- [旧库详情原件、版本差异及剩余队列](old_details/README.md)
- [标签双引擎独立复核](independent_pdf_batch_review/README.md)
- [旧库详情原件独立复核](independent_old_detail_review/README.md)
- [可直接转给DeepSeek的下一步要求](下一步采集与复核要求.md)

仓库保持public，可在GitHub直接预览以上文档。完整本轮阶段归档：[ZIP下载](https://github.com/lima0531/-/raw/refs/heads/purchase-tax-v1-4-files/v1_5/energy_new_complete_20261009/energy_new_snapshot_and_first_labels_20261009.zip)。本轮为独立旁证与复核修订，科学版本保持v1.5。
''', encoding='utf-8')
(ROOT / '下一步采集与复核要求.md').write_text(f'''# 下一步采集与复核要求（固定队列，明确口径）

这是本轮实际原页验收后的要求，可以直接交给另一个可正常访问官网的研究环境。附件中的第三方建议不代替以下经核验范围。

1. **不再补新库页。** 53/53原页已实取并与用户manifest逐字节同SHA。复用这套快照及[全部10479来源记录](new_snapshot_analysis/10479记录_新库全字段与来源.jsonl)，不把之后再次分页采集的字节混进来。
2. **标签按固定936精确记录逐件取。** 已有{n}份，复用SHA和来源收据，待取{936-n}份。两条BMW前导空格候选已另取，不能把938叫作原样精确。允许按相同fullLabel复用一个文档，但不能删除同uuid不同状态行。保留原PDF、SHA、页码、标准原句、JSONpointer以及对应原页SHA。官方代码5/6只能按各自文档解释，不机械套用JX标准。
3. **再取旧库4497applyId详情。** 已有{m}条，待取{4497-m}条。复用旧47页和已取详情，不重抓9336列表。queryDetail可能不回显applyId／备案号，原字段null要保留，只以真实请求id、返回型号和原记录定位建立观察链接，不能假造唯一回显或同配置证书。
4. **逐版本核查475型号差异线索。** 旧202型号同时有CATC/NEDC代码，另新库有多标准备案；标准／数值不同仅为候选。不得把两库同型号的所有记录做笛卡尔连接后叫配置一致。需要质量、续航、电耗、公告批次、时间和实际配置字段逐版本证据；保留无法一一配对的情况。
5. **日期排空再解析。** 原样精确有效早期issueDate458，trim候选460；59空值不是历史日期。issueDate、enableDate、publicTime、createTime分列，不能以issueDate代证明首次公开或原检测报告日期。
6. **分别报证据数和闭合数。** 当前两库精确并集1246，新增12；冻结2208闭合0。只有证据足以支持同历史配置、明确工况且符合冻结边界时才另提交可复核闭合候选；不要修改主CSV。JX能量不能由电耗×续航倒算，行业平均低温提示不当作实测报告。
7. **正常、温和、可恢复请求。** 单worker、间隔至少2秒，校验TLS，保存所有真实尝试，有限瞬态重试；遇401/403/429／登录／验证码保存断点并停止。人为批次预算暂停与网络拒绝分列；不要轮换身份、IP、绕过验证或索取账户凭证。

旧合同schema和完整接收规格仍可复用：[上轮批量合同](../energy_registry_20261009/bulk_handoff/README.md)。本轮[精确逐记录标签队列](new_snapshot_analysis/标签下载队列_每条精确记录.csv)、[唯一PDF任务](new_snapshot_analysis/标签下载队列_按fullLabel去重文件.csv)、[旧详情4497任务](new_snapshot_analysis/旧库详情下载队列_4497applyId固定来源.csv)及各采集目录剩余队列给出真实ID，不需要重新查询生成猜测ID。

## 下载仓库后复跑

脚本的所有本轮目录并列；无需原 `/workspace/purchase_tax_audit`。标签解析及双引擎复核依赖见[requirements_audit.txt](requirements_audit.txt)，用`python -m pip install -r requirements_audit.txt`安装。标签脚本显式传`--source-root`为本轮`public_new_snapshot`、`--output-root`为本轮`label_archive`、`--target-model-file`为`v1_5/public_completion_20261009/public_cycle/2208型号_整篇工况补证结果_只读旁表.csv`、`--old-exact-model-file`为本轮`independent_old_review/1233型号_旧库精确命中集合.csv`；`--stop-after-total`控制本次累计阶段预算，去掉即可按正常规则继续到全部任务。

旧详情脚本使用与它同一层的`independent_old_review/4497记录_旧库精确命中固定来源键.jsonl`，`--limit`是累计前N条预算，不是每次新增N条；比如前100已完，下次`--limit 200`会先校验缓存再取101—200，`--limit 0`取完整队列。已保存访问拒绝的任务停止，不当作可无限重试。每次完成后必须刷新SHA／checkpoint和全局交付清单再上传，不能只改正文进度。
''', encoding='utf-8')
for folder in [ROOT / 'user_submitted', ROOT / 'public_new_snapshot']:
    paths = sorted(p for p in folder.rglob('*') if p.is_file() and p.name != '文件_SHA256.csv' and '__pycache__' not in p.parts)
    with (folder / '文件_SHA256.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['file', 'bytes', 'sha256']); w.writeheader()
        w.writerows({'file': p.relative_to(folder).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in paths)
print(json.dumps({'label_pdfs': n, 'old_details': m, 'remaining_labels': 936 - n, 'remaining_details': 4497 - m}, ensure_ascii=False))
