#!/usr/bin/env python3
"""Read-only local audit of the three submitted documents and repository evidence.

Never requests remote content and never fills absent delivery files. Outputs are
limited to --output. Successful local checks are distinct from pending claims.
"""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def meta(path):
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def check(name, ok, evidence):
    return {"name": name, "status": "PASS" if ok else "FAIL", "evidence": evidence}


def audit(args):
    summary_path = Path(args.summary)
    manifest_path = Path(args.manifest)
    old_path = Path(args.old_verification)
    registry = Path(args.registry)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    old = json.loads(old_path.read_text(encoding="utf-8"))
    registry_summary = json.loads((registry / "registry_summary.json").read_text(encoding="utf-8"))
    file_entries = manifest["files"]
    entry_lookup = {f["path"]: f for f in file_entries}
    raw_entries = [f for f in file_entries if f["path"].startswith("raw/responses/")]
    delivered = {"summary.md": summary_path, "old_library_verification.json": old_path}
    checks = []
    for name, path in delivered.items():
        expected = entry_lookup[name]
        actual = meta(path)
        checks.append(check("submitted_byte_identity_" + name,
                            actual["bytes"] == expected["bytes"] and actual["sha256"] == expected["sha256"],
                            {"expected": expected, "actual": actual}))
    paths = [f["path"] for f in file_entries]
    unsafe_paths = [s for s in paths if PurePosixPath(s).is_absolute() or ".." in PurePosixPath(s).parts]
    invalid_hashes = [f["path"] for f in file_entries if not re.fullmatch(r"[0-9a-f]{64}", f["sha256"])]
    invalid_bytes = [f["path"] for f in file_entries if not isinstance(f["bytes"], int) or f["bytes"] < 0]
    expected_raw = {f"raw/responses/new_page{i:04d}.json" for i in range(1, 54)}
    checks.append(check("manifest_structure_only", len(set(paths)) == len(paths) and not unsafe_paths and
                        not invalid_hashes and not invalid_bytes and {f["path"] for f in raw_entries} == expected_raw,
                        {"file_entries": len(file_entries), "raw_page_entries": len(raw_entries),
                         "invalid_sha256": invalid_hashes, "unsafe_paths": unsafe_paths,
                         "invalid_bytes": invalid_bytes, "duplicate_paths": len(paths) - len(set(paths))}))
    declaration_bytes = sum(f["bytes"] for f in file_entries)
    counts = {
        "listed_files": len(file_entries), "raw_response_files_listed": len(raw_entries),
        "non_raw_files_listed": len(file_entries) - len(raw_entries),
        "manifest_is_self_listed": "delivery_manifest.json" in entry_lookup,
        "listed_bytes": declaration_bytes,
        "listed_decimal_MB": declaration_bytes / 1_000_000,
        "listed_binary_MiB": declaration_bytes / (1024 ** 2),
        "manifest_bytes": manifest_path.stat().st_size,
        "listed_plus_manifest_file_count": len(file_entries) + 1,
        "listed_plus_manifest_bytes": declaration_bytes + manifest_path.stat().st_size,
        "raw_response_bytes_listed": sum(f["bytes"] for f in raw_entries),
        "attached_files_available": 3,
        "listed_files_attached_and_byte_verified": 2,
        "listed_files_not_attached": len(file_entries) - len(delivered),
    }
    # Actual old originals are already in the repository, so this claim can be
    # independently recalculated without accepting the submitter's totals.
    old_pages = []
    all_apply_ids = []
    for declared in old["pages"]:
        path = registry / declared["file"]
        page_json = json.loads(path.read_text(encoding="utf-8"))
        info = page_json["info"]
        rows = info["list"]
        ids = [r.get("applyId") for r in rows]
        actual = {
            "page": declared["page"], "file": declared["file"],
            "result": page_json["result"], "echo_currentPage": info["currentPage"],
            "rows": len(rows), "unique_applyId": len(set(ids)),
            "echo_totalSize": info["totalSize"], "echo_pages": info["pages"],
            "response_sha256": sha(path), "bytes": path.stat().st_size,
        }
        mismatches = {k: {"declared": v, "actual": actual.get(k)} for k, v in declared.items()
                      if k not in ("source",) and v != actual.get(k)}
        actual["declared_field_mismatches"] = mismatches
        old_pages.append(actual)
        all_apply_ids.extend(ids)
    old_recalc = {
        "pages": len(old_pages), "rows": sum(p["rows"] for p in old_pages),
        "unique_applyId": len(set(all_apply_ids)), "null_applyId_occurrences": all_apply_ids.count(None),
        "all_pages_match_submitted_verification": not any(p["declared_field_mismatches"] for p in old_pages),
        "page_numbers": [p["page"] for p in old_pages],
        "attempt02_used_pages": [p["page"] for p in old_pages if "attempt02" in p["file"]],
        "failed_first_attempts": [],
    }
    for page in [10, 17]:
        receipt = json.loads((registry / f"old_currentPage/page{page:04d}_receipt.json").read_text())
        detail = {"page": page, "http_status": receipt.get("http_status"),
                  "error": receipt.get("error"), "error_detail": receipt.get("error_detail"),
                  "response_file_saved": bool(receipt.get("file"))}
        if receipt.get("file"):
            path = registry / receipt["file"]
            try:
                json.loads(path.read_text())
                parseable = True
            except (json.JSONDecodeError, UnicodeDecodeError):
                parseable = False
            detail.update({"bytes": path.stat().st_size, "parseable_json": parseable, "sha256": sha(path)})
        old_recalc["failed_first_attempts"].append(detail)
    checks.append(check("old_47_pages_recomputed_from_actual_repository_raw",
        old_recalc["all_pages_match_submitted_verification"] and old_recalc["pages"] == 47 and
        old_recalc["rows"] == old_recalc["unique_applyId"] == 9336 and
        old_recalc["page_numbers"] == list(range(1, 48)) and
        all(p["rows"] == (136 if p["page"] == 47 else 200) for p in old_pages), old_recalc))
    # Only four new page byte identities can be corroborated with local originals.
    new_shared_pages = []
    for page in registry_summary["libraries"]["new"]["pages"]:
        submitted = entry_lookup[f"raw/responses/new_page{page['page']:04d}.json"]
        path = registry / page["file"]
        receipt = json.loads((registry / page["receipt"]).read_text())
        data = json.loads(path.read_text())
        item = {
            "page": page["page"], "repository_file": page["file"],
            "manifest_path": submitted["path"], "actual_bytes": path.stat().st_size,
            "actual_sha256": sha(path), "manifest_bytes": submitted["bytes"],
            "manifest_sha256": submitted["sha256"], "rows_in_repository_raw": len(data["info"]["list"]),
            "currentPage_echo_in_repository_raw": data["info"]["currentPage"],
            "repository_observed_utc": receipt["observed_utc"],
            "repository_observed_Asia_Shanghai": datetime.fromisoformat(receipt["observed_utc"]).astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
            "bytes_equal_manifest_declaration": path.stat().st_size == submitted["bytes"] and sha(path) == submitted["sha256"],
        }
        new_shared_pages.append(item)
    checks.append(check("new_4_page_manifest_hashes_equal_existing_repository_bytes",
                        len(new_shared_pages) == 4 and all(p["bytes_equal_manifest_declaration"] for p in new_shared_pages), new_shared_pages))
    previous_sets = {
        "old_exact_models": registry_summary["core_match_states"]["old_observed"] + registry_summary["core_match_states"]["both_observed"],
        "new_4page_exact_models": registry_summary["core_match_states"]["new_observed"] + registry_summary["core_match_states"]["both_observed"],
        "old_new_overlap": registry_summary["core_match_states"]["both_observed"],
        "union": registry_summary["core_models_with_any_visible_exact_record"],
    }
    issues = [
        {"id": "file_count", "status": "CONFIRMED_DOCUMENT_INCONSISTENCY",
         "detail": "summary将manifest描述为57个交付文件；实际files数组58条=53响应+5非响应。manifest未自列，整套含manifest应为59件。用户消息58件可指数组列出的payload，需明确计数口径。"},
        {"id": "request_count", "status": "UNRESOLVED_DOCUMENT_CONFLICT",
         "summary_claim": 52, "manifest_claim": manifest["new_library"]["network_requests_this_run"],
         "detail": "summary称52次本轮直采+1页复用；manifest称53次本轮网络请求。请求/运行日志未交来，不能替其选择真实值。"},
        {"id": "observation_chronology", "status": "UNRESOLVED_DOCUMENT_CONFLICT",
         "manifest_time_claim": manifest["observed_local_time"],
         "repository_reused_page4_observed_Asia_Shanghai": new_shared_pages[3]["repository_observed_Asia_Shanghai"],
         "detail": "manifest约13:0x上海本地时间早于声称复用的仓库第4页17:58:47收据；同日同区时序不闭合。不能推测时钟/时区原因，需原始日志和生成时间说明。字节相等不证明同一请求。"},
        {"id": "new_snapshot_wording", "status": "CLARIFICATION_REQUIRED",
         "detail": "summary既称53页重新采集又声明1页复用仓库attempt02；应准确写52页新采+1页复用的混合观测集合，不称单一新采或原子事务快照。3个其他共享页与仓库也逐字节相同，但仅此不证明也被复用。"},
        {"id": "old_retry_cause", "status": "CONFIRMED_DOCUMENT_CORRECTION",
         "actual_first_attempts": old_recalc["failed_first_attempts"],
         "detail": "第10页首次503/95字节成立；第17页首轮为TimeoutError，无HTTP状态或保存的响应文件，并非同样503网关文本。二者有效数据均取attempt02，但失败类型不可混称。"},
        {"id": "increment_vs_union", "status": "SET_OPERATION_CORRECTION",
         "previous_repository_sets": previous_sets,
         "detail": "既有1234=旧1233+新3−重合2。539−3=536仅为新库命中型号数差，不能当两库并集新增；新版精确命中集合未交来，旧新交集与真实并集尚不能重算。"},
        {"id": "system_energy_field_scope", "status": "SCOPE_CORRECTION",
         "detail": "未交来53页全字段和详情/标签不能证明整个系统根本不提供电池能量。即便完整列表未见该字段，也只能描述已核列表/标签字段；不得替未检视端点做系统级不存在断言。JX第48批总能量缺口保持。"},
    ]
    pending = [
        "新库第5–53页49件原字节及各自SHA/回显/页长/请求状态；仅有清单声明。",
        "records.jsonl全10479行、10476 uuid、全行哈希唯一及3重复标识状态行保留；未交来不能复算。",
        "query_runs.jsonl与requests.jsonl、网络52/53次数和零错误、13:0x观测时序；未交来不能复算。",
        "539/938精确命中、566/1087规范化命中、519早于冻结点、fullLabel覆盖和标准代码分布；缺原行及完整匹配台账不能复算。",
        "新库新增命中型号与旧库1233集合的交集、并集、版本冲突。",
        "标签PDF、旧库queryDetail及配置/历史公开日期资格。",
    ]
    return {
        "review_status": "PARTIAL_VERIFIED_WITH_DOCUMENT_CORRECTIONS_AND_UNAVAILABLE_NEW_PAYLOAD",
        "no_network_requests": True, "no_scientific_or_export_mutation": True,
        "attached_inputs": [meta(summary_path), meta(manifest_path), meta(old_path)],
        "manifest_declared_counts_and_bytes": counts,
        "checks": checks, "all_completed_local_checks_pass": all(c["status"] == "PASS" for c in checks),
        "old_actual_page_review": old_pages, "new_shared_page_review": new_shared_pages,
        "new_claimed_pagination_arithmetic_only": {"claimed_pages": 53, "claimed_page_size": 200,
            "claimed_last_rows": 79, "computed_expected_rows": 52 * 200 + 79,
            "matches_manifest_row_declaration": 52 * 200 + 79 == manifest["new_library"]["rows"],
            "raw_recount_completed": False},
        "documentation_issues": issues, "pending_not_passed": pending,
        "conclusions": {"old_repository_snapshot_reverified": True,
            "new_53page_delivery_independently_verified": False,
            "new_exact_match_count_independently_verified": False,
            "frozen_cycle_gap_closed_by_this_review": 0, "battery_energy_gap_closed_by_this_review": 0},
    }


def readme(review):
    counts = review["manifest_declared_counts_and_bytes"]
    return f"""# 新库补采交付文件独立只读复核

本次实际收到3件：summary.md、delivery_manifest.json、old_library_verification.json。新库53页原始响应、records.jsonl和两份日志没有随本次附件交来。**本复核确认已有材料的身份及旧库快照；尚未独立验收新库全量交付，也未扣减冻结工况缺口。**

可重跑：[review_manifest.py](review_manifest.py)；逐项证据：[review.json](review.json)。无网络请求，不修改科学主表、导出目录或Git。

## 可独立确认的结果

- summary为4,666 B，SHA256 `5e73040716a54d1e77f0c3e26c64386ec34ce2db77a5bceb9ee3bd1eb53a3104`；旧库核验为15,720 B，SHA256 `4831e97a3cf4e6ffbbbae25916210dec9300636755740740bb02a0dc12315876`。两件均与清单逐字节声明相符。
- 清单实际列{counts['listed_files']}件（53页响应＋5件其他文件），不含清单本身。声明总量为**{counts['listed_bytes']:,} B＝{counts['listed_decimal_MB']:.6f} MB＝{counts['listed_binary_MiB']:.6f} MiB**；若包含清单则59件、{counts['listed_plus_manifest_bytes']:,} B。这是清单求和，尚非缺失payload的实测总量。summary写57件需要订正；用户消息58件可指清单的payload计数，但应明示。
- 清单路径唯一且无越界路径，53响应条目恰覆盖0001–0053，SHA格式均有效。`52×200＋79＝10,479`算术成立，不能替代逐页原文回显复核。
- 仓库已持有旧库47页原件，本轮按交来核验表逐页重新解析并计算SHA，47件全同；9,336行、9,336唯一applyId、页码及总数回显均成立，末页136行。第10和17页必须使用attempt02；第10页首轮503文本不可计为响应数据，第17页首轮超时没有保存响应。
- 新库清单的前4页SHA、字节数与仓库4份有效响应完全相等；第4页对的是attempt02。此项确认身份，不证明这些字节分别来自哪次网络请求，也不代替未交来的第5–53页验证。

## 必须订正或补证的口径

1. **52/53次请求冲突**：summary称52次本轮请求加1页复用，manifest的`network_requests_this_run`为53。原始请求日志尚未交来，不替其认定真实次数。
2. **观测时间冲突**：manifest写上海时间约2026-10-09 13:0x，复用的仓库第4页收据却是同日17:58:47（UTC09:58:47）。时序未闭合；需日志及生成时间解释，不推测时钟或时区原因。
3. **采集集合定义**：既声明1页复用，便应称“52页新采＋1页复用的混合观测集合”。不能称53页同次新采或单一原子事务快照。其余3页哈希也与仓库相等，仅据此不能推断它们被复用。
4. **旧库重试原因**：第10页首轮为HTTP503、95 B；第17页为TimeoutError，无HTTP状态和响应原件。两页都用attempt02成立，但“第17页同结构503”需要订正。
5. **增量与并集**：已有1234＝旧库1233＋新库3−重合2。539−3＝536只表示新库命中数差；是否为536新增命中型号需集合差验算，更不能当作两库并集增量。新版精确命中集合未交来，当前不能重算交集与并集。
6. **能源字段边界**：全系统“根本没有电池能量字段”超出当前证据；应表述为已核列表／标签未见该项，不外推到未查详情或其他端点。JX第48批总能量继续缺失，不能由电耗和续航倒算。

## 尚未独立核验

第5–53页原始字节、全行uuid/哈希、938精确命中记录、519条issueDate早于冻结点、全部fullLabel及标准代码分布、网络零错误、两库交集和版本冲突仍须原始payload与台账支撑。**清单声明、算术自洽与原件身份核对，不等于新库全量完成验收。** issueDate即使早于冻结点，也不能单独认证历史公开可得或同税目录配置身份。
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", default="/workspace/attachments/fcc63a8f-8580-4b34-9550-ebdda069e5a7/summary.md")
    parser.add_argument("--manifest", default="/workspace/attachments/267bf06b-eb0c-4833-9ff3-e0283c80d7ce/delivery_manifest.json")
    parser.add_argument("--old-verification", default="/workspace/attachments/3d25d40c-f714-41dd-a317-67797d52c3de/old_library_verification.json")
    parser.add_argument("--registry", default="/workspace/file_export_proposal/v1_5/energy_registry_20261009/public_energy_registry")
    parser.add_argument("--output", default=str(Path(__file__).resolve().parent))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    review = audit(args)
    (output / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "README.md").write_text(readme(review), encoding="utf-8")
    with (output / "文件_SHA256.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["file", "bytes", "sha256"])
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "文件_SHA256.csv" and "__pycache__" not in path.parts:
                writer.writerow([path.relative_to(output).as_posix(), path.stat().st_size, sha(path)])
    print(json.dumps({"review_status": review["review_status"], "completed_local_checks": len(review["checks"]),
         "all_completed_local_checks_pass": review["all_completed_local_checks_pass"],
         "new_full_delivery_verified": False, "listed_bytes": review["manifest_declared_counts_and_bytes"]["listed_bytes"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
