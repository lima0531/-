#!/usr/bin/env python3
"""Independent local verification of reacquired public bytes; performs no network.

Only reads raw pages, receipts, checkpoints, submitted manifest and the fixed
2208 list. Does not read another agent's analysis output. Writes own review only.
"""
import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_sha(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")).encode("utf-8")).hexdigest()


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def run(args):
    root = Path(args.new_snapshot)
    old = Path(args.old_registry)
    fixed = Path(args.fixed_models)
    submitted_manifest = Path(args.manifest)
    output = Path(args.output)
    checkpoint_path = root / "new_checkpoint.json"
    checkpoint_bytes = checkpoint_path.read_bytes()
    checkpoint = json.loads(checkpoint_bytes)
    if not checkpoint.get("completed") or not checkpoint.get("finished_utc"):
        raise SystemExit("New checkpoint is not finished; no partial result is published.")
    manifest = json.loads(submitted_manifest.read_text(encoding="utf-8"))
    expected = {f["path"]: f for f in manifest["files"]}
    fixed_bytes_before = sha(fixed)
    model_rows = list(csv.DictReader(fixed.open(encoding="utf-8-sig", newline="")))
    targets = {r["model_key"] for r in model_rows}
    assert len(model_rows) == len(targets) == 2208
    new_rows = []
    new_lineage = []
    pages = []
    request_times = []
    for page in range(1, 54):
        suffix = f"new_currentPage/page{page:04d}_response.json"
        page_path = root / suffix
        page_bytes = page_path.read_bytes()
        digest = hashlib.sha256(page_bytes).hexdigest()
        data = json.loads(page_bytes)
        info = data["info"]
        receipt_path = page_path.with_name(page_path.name.replace("_response.json", "_receipt.json"))
        receipt = json.loads(receipt_path.read_text())
        request_times.append(receipt["observed_utc"])
        declared = expected[f"raw/responses/new_page{page:04d}.json"]
        checks = {
            "new_api_result_200": data["result"] == 200,
            "echo_page_correct": info["currentPage"] == page,
            "echo_page_size_200": info["pageSize"] == 200,
            "echo_total_10479": info["totalSize"] == 10479,
            "echo_pages_53": info["pages"] == 53,
            "correct_actual_rows": len(info["list"]) == (79 if page == 53 else 200),
            "actual_matches_manifest_bytes": len(page_bytes) == declared["bytes"],
            "actual_matches_manifest_sha": digest == declared["sha256"],
            "receipt_sha_matches_actual": receipt["sha256"] == digest,
            "receipt_size_matches_actual": receipt["bytes"] == len(page_bytes),
            "receipt_http_200": receipt["http_status"] == 200,
            "receipt_request_page": receipt["request_json"]["currentPage"] == page,
            "receipt_no_filter_drift": receipt["request_json"] == {"currentPage": page, "pageSize": 200, "energyType": "8"},
        }
        pages.append({"page": page, "source_file": suffix, "bytes": len(page_bytes), "sha256": digest, "result_raw": data["result"],
                      "rows": len(info["list"]), "observed_utc": receipt["observed_utc"], "checks": checks,
                      "all_checks_pass": all(checks.values())})
        for index, row in enumerate(info["list"], 1):
            new_rows.append(row)
            new_lineage.append({"page": page, "row_ordinal_1_based": index,
                "source_file": suffix, "source_sha256": digest,
                "full_row_sha256": row_sha(row), "uuid": row.get("uuid"), "model": row.get("vehicleModel"),
                "issueDate": row.get("issueDate"), "reportStatus": row.get("reportStatus")})
    # Old raw pages are selected from the established source-page checkpoint,
    # not from wildcard filenames which would mishandle failed attempts.
    old_checkpoint_path = old / "old_checkpoint.json"
    old_checkpoint = json.loads(old_checkpoint_path.read_text())
    old_rows = []
    old_pages = []
    for relative in old_checkpoint["source_page_files"]:
        path = old / relative
        data = json.loads(path.read_text())
        info = data["info"]
        old_pages.append({"source_file": relative, "sha256": sha(path), "page": info["currentPage"], "rows": len(info["list"]),
                          "result": data["result"], "pages_echo": info["pages"], "total_echo": info["totalSize"]})
        old_rows.extend(info["list"])
    new_exact = [r for r in new_rows if r.get("vehicleModel") in targets]
    old_exact = [r for r in old_rows if r.get("vehicleNumber") in targets]
    new_models = {r["vehicleModel"] for r in new_exact}
    old_models = {r["vehicleNumber"] for r in old_exact}
    normalized_target_to_raw = defaultdict(list)
    for model in targets:
        normalized_target_to_raw[normalize(model)].append(model)
    normalized_rows = [r for r in new_rows if normalize(r.get("vehicleModel") or "") in normalized_target_to_raw]
    normalized_raw_models = {r["vehicleModel"] for r in normalized_rows}
    normalized_matched_target_models = {m for r in normalized_rows for m in normalized_target_to_raw[normalize(r["vehicleModel"])]}
    # Diagnose undeclared transformations without accepting them as exact matches.
    trim_rows = [r for r in new_rows if (r.get("vehicleModel") or "").strip() in targets]
    trim_models = {(r.get("vehicleModel") or "").strip() for r in trim_rows}
    uppercase_target_to_raw = defaultdict(list)
    for model in targets:
        uppercase_target_to_raw[normalize(model).upper()].append(model)
    uppercase_rows = [r for r in new_rows if normalize(r.get("vehicleModel") or "").upper() in uppercase_target_to_raw]
    uppercase_matched_target_models = {m for r in uppercase_rows
                                      for m in uppercase_target_to_raw[normalize(r["vehicleModel"]).upper()]}
    trim_valid_dates = [r["issueDate"] for r in trim_rows
                       if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("issueDate")))]
    alternative_operations = {
        "strip_only_candidate": {"rows": len(trim_rows), "models": len(trim_models),
           "additional_rows_not_exact": [{**new_lineage[i], "raw_vehicleModel": r["vehicleModel"]}
                                           for i, r in enumerate(new_rows)
                                           if r in trim_rows and r.get("vehicleModel") not in targets],
           "testBasisStandard_counts": dict(sorted(Counter(r.get("testBasisStandard") for r in trim_rows).items())),
           "nonempty_issueDate_rows": sum(bool(r.get("issueDate")) for r in trim_rows),
           "missing_issueDate_rows": sum(not bool(r.get("issueDate")) for r in trim_rows),
           "valid_date_before_freeze_rows": sum(d < "2023-12-10" for d in trim_valid_dates),
           "unsafe_missing_as_empty_string_before_freeze_rows": sum(str(r.get("issueDate") or "") < "2023-12-10" for r in trim_rows)},
        "NFKC_remove_all_whitespace_uppercase_candidate": {"rows": len(uppercase_rows),
           "fixed_target_models": len(uppercase_matched_target_models),
           "extra_transform_vs_user_declared_method": "uppercase",
           "casefolded_target_collision_groups": {k: v for k, v in uppercase_target_to_raw.items() if len(v) > 1}},
        "interpretation": "These operations reproduce submitted counts but do not prove the producer used them; producer scripts were not attached. Exact byte matching remains separate from every normalization candidate.",
    }
    uuid_counts = Counter(r.get("uuid") for r in new_rows)
    duplicate_ids = {key: count for key, count in uuid_counts.items() if count > 1}
    duplicated = []
    for key in duplicate_ids:
        raw_group = [r for r in new_rows if r.get("uuid") == key]
        differing_keys = [k for k in sorted(set().union(*(r.keys() for r in raw_group)))
                          if len({json.dumps(r.get(k), ensure_ascii=False, sort_keys=True) for r in raw_group}) > 1]
        duplicated.append({"uuid": key, "occurrences": len(raw_group), "differing_fields": differing_keys,
            "records": [l for l in new_lineage if l["uuid"] == key]})
    full_hash_counts = Counter(row_sha(r) for r in new_rows)
    dates = [r.get("issueDate") for r in new_exact if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(r.get("issueDate")))]
    label_tokens = [r.get("fullLabel") for r in new_exact if r.get("fullLabel")]
    exact_profile = {
        "rows": len(new_exact), "model_count": len(new_models),
        "unique_uuids": len({r.get("uuid") for r in new_exact}),
        "full_label_nonempty_rows": len(label_tokens), "distinct_full_label_tokens": len(set(label_tokens)),
        "testBasisStandard_raw_counts": dict(sorted(Counter(r.get("testBasisStandard") for r in new_exact).items())),
        "issueDate_nonempty_rows": sum(bool(r.get("issueDate")) for r in new_exact),
        "issueDate_valid_ymd_rows": len(dates), "issueDate_min": min(dates), "issueDate_max": max(dates),
        "issueDate_strictly_before_2023_12_10_rows": sum(d < "2023-12-10" for d in dates),
        "issueDate_on_or_before_2023_12_10_rows": sum(d <= "2023-12-10" for d in dates),
        "vehicleType_raw_counts": dict(sorted(Counter(r.get("vehicleType") for r in new_exact).items())),
        "enableDate_min": min(r["enableDate"] for r in new_exact if r.get("enableDate")),
    }
    previous_new_rows = []
    for page in range(1, 5):
        suffix = f"new_currentPage/page{page:04d}" + ("_attempt02_response.json" if page == 4 else "_response.json")
        previous_new_rows.extend(json.loads((old / suffix).read_text())["info"]["list"])
    previous_new_models = {r["vehicleModel"] for r in previous_new_rows if r.get("vehicleModel") in targets}
    old_counts = Counter(r["vehicleNumber"] for r in old_exact)
    new_counts = Counter(r["vehicleModel"] for r in new_exact)
    model_sets = {
        "old_exact": sorted(old_models), "new_exact": sorted(new_models),
        "intersection": sorted(old_models & new_models), "union": sorted(old_models | new_models),
        "new_only": sorted(new_models - old_models), "old_only": sorted(old_models - new_models),
        "neither_in_observed_views": sorted(targets - old_models - new_models),
        "previous_new_4page_exact": sorted(previous_new_models),
        "new_library_set_gain_vs_previous_4pages": sorted(new_models - previous_new_models),
        "new_library_set_loss_vs_previous_4pages": sorted(previous_new_models - new_models),
        "union_gain_vs_previous_old_plus_4pages": sorted((old_models | new_models) - (old_models | previous_new_models)),
    }
    model_set_counts = {k: len(v) for k, v in model_sets.items()}
    summary = {
        "review_status": "REACQUIRED_RAW_VERIFIED_USER_PRIVATE_LOGS_NOT_VERIFIED",
        "no_network_requests_in_this_reviewer": True,
        "analysis_independent_of_other_agent_outputs": True,
        "source_checkpoint_finished_utc": checkpoint["finished_utc"],
        "source_checkpoints": {"new_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(), "old_sha256": sha(old_checkpoint_path)},
        "new_observation_start_utc": min(request_times), "new_observation_end_utc": max(request_times),
        "public_raw_page_count": len(pages), "raw_bytes": sum(p["bytes"] for p in pages),
        "all_53_page_checks_pass": all(p["all_checks_pass"] for p in pages),
        "new_raw_rows": len(new_rows), "new_unique_uuid": len(uuid_counts),
        "new_null_uuid_occurrences": uuid_counts.get(None, 0),
        "new_duplicate_uuid_distinct_count": len(duplicate_ids),
        "new_duplicate_uuid_extra_occurrences": sum(c - 1 for c in duplicate_ids.values()),
        "new_unique_full_row_hashes": len(full_hash_counts),
        "new_identical_full_row_repeat_occurrences": sum(c - 1 for c in full_hash_counts.values()),
        "old_raw_pages": len(old_pages), "old_raw_rows": len(old_rows),
        "old_unique_applyIds": len({r.get("applyId") for r in old_rows}),
        "old_exact_target_rows": len(old_exact), "exact_new_profile": exact_profile,
        "new_normalized_match": {"rows": len(normalized_rows), "distinct_raw_model_strings": len(normalized_raw_models),
             "matched_fixed_target_models": len(normalized_matched_target_models), "target_normalization_collision_groups": {
                 k: v for k, v in normalized_target_to_raw.items() if len(v) > 1}},
        "model_set_counts": model_set_counts,
        "diagnostic_alternative_operations": alternative_operations,
        "model_sets": model_sets,
        "new_duplicate_uuid_rows_all_retained": duplicated,
        "input_files": {"submitted_manifest": {"file": str(submitted_manifest), "sha256": sha(submitted_manifest)},
                        "fixed_2208": {"file": str(fixed), "sha256": fixed_bytes_before}},
        "pages": pages, "old_pages": old_pages,
        "unresolved_user_delivery_issues_preserved": ["user_52_vs_53_request_count", "13:0x_vs_reused_17:58_time",
           "unreceived_records_jsonl_bytes_and_manifest_sha", "unreceived_query_runs_jsonl_and_requests_jsonl_bytes",
           "mixed_user_collection_vs_single_snapshot_wording"],
        "frozen_cycle_gap_closed_by_this_review": 0, "jx_battery_energy_gap_closed_by_this_review": 0,
        "no_claim_for_historical_public_availability_or_same_tax_configuration": True,
    }
    assert checkpoint_bytes == checkpoint_path.read_bytes(), "Collector checkpoint changed while reviewing"
    assert fixed_bytes_before == sha(fixed), "Fixed models input changed"
    assert len(old_pages) == 47 and len(old_rows) == len({r.get("applyId") for r in old_rows}) == 9336
    assert summary["all_53_page_checks_pass"]
    assert len(new_rows) == 10479 and len(uuid_counts) == 10476 and len(full_hash_counts) == 10479
    output.mkdir(parents=True, exist_ok=True)
    (output / "reacquired_raw_review.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "2208型号_独立精确交并集核验.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["model_key", "old_exact_rows", "new_exact_rows", "old_hit", "new_hit", "in_union", "in_intersection",
                         "new_library_gain_vs_previous_4pages", "union_gain_vs_previous_old_plus_4pages"])
        for model in sorted(targets):
            writer.writerow([model, old_counts[model], new_counts[model], int(model in old_models), int(model in new_models),
               int(model in old_models | new_models), int(model in old_models & new_models),
               int(model in new_models - previous_new_models), int(model in (old_models | new_models) - (old_models | previous_new_models))])
    # Preserve the earlier attachment-only review and all its unresolved issues.
    marker = "\n<!-- REACQUIRED_RAW_FOLLOWUP -->\n"
    path = output / "README.md"
    prior = path.read_text(encoding="utf-8").split(marker)[0]
    followup = f"""\n## 追加：本环境重新取得53页原字节后独立核验

本环境另行采得53页公开响应，逐页SHA/大小与用户清单53条**全部一致**。这是对相同原字节的重新取得与核验；没有收到或认证用户自己的records.jsonl、query_runs.jsonl、requests.jsonl，也不解决原文52/53请求或13:0x与复用17:58时序冲突。上述首次附件复核及其issues保留，不能据本轮公开响应反推出用户网络过程。

[独立核验脚本](review_reacquired_raw.py)只读新53页、旧47页原件及固定2208名单，没有读取另一agent的分析结果；[核验JSON](reacquired_raw_review.json)和[2208逐型号交并集](2208型号_独立精确交并集核验.csv)可复算。

- 新库53页/{len(new_rows):,}行，末页79；{len(uuid_counts):,}唯一uuid、3个重复uuid，各2个不同完整行，全部保留；{len(full_hash_counts):,}完整行哈希全部不同。
- 新库精确命中{len(new_models)}型号/{len(new_exact)}行；NFKC＋去空白命中{len(normalized_matched_target_models)}固定型号/{len(normalized_rows):,}行（规范化候选单列，不认证配置相同）。
- 旧库精确{len(old_models):,}型号，新库精确{len(new_models)}；**交集{len(old_models & new_models)}，并集{len(old_models | new_models):,}，仅新库{len(new_models - old_models)}，仅旧库{len(old_models - new_models)}，两库该筛选视图未命中{len(targets - old_models - new_models)}**。
- 旧4页新库命中3型号，新完整新库比旧4页净增{len(new_models - previous_new_models)}型号；旧库＋新库并集从{len(old_models | previous_new_models):,}到{len(old_models | new_models):,}，**真正并集新增{len((old_models | new_models) - (old_models | previous_new_models))}**。536不能当并集增量。
- 精确命中{len(new_exact)}行全部有fullLabel；标准代码5/6、issueDate日期分布见核验JSON。早于冻结点仍不证明当时公开可得；没有建立同税目录配置对应，冻结缺口关闭0、JX能量关闭0。

### 原文计数差异的独立复现

原样精确记录为936行，标准代码5＝887／6＝49，有效issueDate为877条，冻结日前458条。原文938行可在**先去首尾空白**后复现：另增原串` BMW6462AAEV`、` BMW6462ABEV`各1行（已列出页／行／uuid），两条均有前导空格；故原文938应称trim候选，不是原样精确。

trim候选938行中，有879条非空日期，冻结日前有效日期**460条**。若把59个缺失日期替成空字符串后做字符串比较，会得到`460＋59＝519`，这正好复现原文519；**缺失日期不可计作早于冻结点**。未收到用户脚本，此复现不证明其内部算法，但519不是有效日期计数。

用户称“NFKC＋去空白”的566型号／1087行，必须再**转大写**才能在这些同字节原行与固定名单上复现；仅NFKC＋去所有Unicode空白为545型号／961行。补充声明大小写变换即可准确标记候选口径，不可把该候选当作原样精确、配置相同或冻结缺口关闭。
"""
    path.write_text(prior + marker + followup, encoding="utf-8")
    with (output / "文件_SHA256.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["file", "bytes", "sha256"])
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "文件_SHA256.csv" and "__pycache__" not in path.parts:
                writer.writerow([path.relative_to(output).as_posix(), path.stat().st_size, sha(path)])
    print(json.dumps({"all_53_page_checks_pass": summary["all_53_page_checks_pass"],
         "rows": len(new_rows), "new_exact_rows": len(new_exact), "model_set_counts": model_set_counts,
         "new_normalized_match": summary["new_normalized_match"]}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--new-snapshot", default="/workspace/purchase_tax_audit/round11/public_new_snapshot")
    p.add_argument("--old-registry", default="/workspace/file_export_proposal/v1_5/energy_registry_20261009/public_energy_registry")
    p.add_argument("--fixed-models", default="/workspace/file_export_proposal/v1_5/energy_registry_20261009/bulk_handoff/2208精确请求型号名单.csv")
    p.add_argument("--manifest", default="/workspace/attachments/267bf06b-eb0c-4833-9ff3-e0283c80d7ce/delivery_manifest.json")
    p.add_argument("--output", default=str(Path(__file__).resolve().parent))
    run(p.parse_args())


if __name__ == "__main__":
    main()
