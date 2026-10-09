#!/usr/bin/env python3
"""Compare finished independent results after each computation is complete."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--own", default=str(Path(__file__).resolve().parent / "reacquired_raw_review.json"))
    p.add_argument("--peer", default="/workspace/purchase_tax_audit/round11/new_model_count_independent.json")
    p.add_argument("--output", default=str(Path(__file__).resolve().parent))
    args = p.parse_args()
    own_path, peer_path = Path(args.own), Path(args.peer)
    own, peer = json.loads(own_path.read_text()), json.loads(peer_path.read_text())
    pairs = {
        "53_pages": (own["public_raw_page_count"], peer["pages"]),
        "raw_rows": (own["new_raw_rows"], peer["raw_rows"]),
        "uuid_unique": (own["new_unique_uuid"], peer["unique_nonempty_uuid"]),
        "full_row_sha_unique": (own["new_unique_full_row_hashes"], peer["unique_fullrow_sha256"]),
        "exact_models": (own["exact_new_profile"]["model_count"], peer["exact"]["target_models"]),
        "exact_rows": (own["exact_new_profile"]["rows"], peer["exact"]["rows"]),
        "exact_unique_labels": (own["exact_new_profile"]["distinct_full_label_tokens"], peer["exact"]["unique_nonempty_fullLabel_tokens"]),
        "nonempty_dates": (own["exact_new_profile"]["issueDate_nonempty_rows"], peer["exact"]["issueDate"]["valid_rows"]),
        "valid_date_before_freeze": (own["exact_new_profile"]["issueDate_strictly_before_2023_12_10_rows"], peer["exact"]["issueDate"]["rows_before_freeze_exclusive"]),
        "nfkc_ws_models": (own["new_normalized_match"]["matched_fixed_target_models"], peer["nfkc_remove_all_unicode_whitespace"]["target_models"]),
        "nfkc_ws_rows": (own["new_normalized_match"]["rows"], peer["nfkc_remove_all_unicode_whitespace"]["rows"]),
        "nfkc_ws_upper_models": (own["diagnostic_alternative_operations"]["NFKC_remove_all_whitespace_uppercase_candidate"]["fixed_target_models"], peer["nfkc_remove_whitespace_plus_upper_candidate"]["target_models"]),
        "nfkc_ws_upper_rows": (own["diagnostic_alternative_operations"]["NFKC_remove_all_whitespace_uppercase_candidate"]["rows"], peer["nfkc_remove_whitespace_plus_upper_candidate"]["rows"]),
        "intersection": (own["model_set_counts"]["intersection"], peer["old_new_exact_sets"]["intersection"]),
        "union": (own["model_set_counts"]["union"], peer["old_new_exact_sets"]["union"]),
        "real_union_gain": (own["model_set_counts"]["union_gain_vs_previous_old_plus_4pages"], peer["old_new_exact_sets"]["additional_vs_prior_union"]),
        "new_only_set": (own["model_sets"]["new_only"], peer["old_new_exact_sets"]["new_only_models"]),
        "old_only_set": (own["model_sets"]["old_only"], peer["old_new_exact_sets"]["old_only_models"]),
        "union_gain_set": (own["model_sets"]["union_gain_vs_previous_old_plus_4pages"], peer["old_new_exact_sets"]["additional_vs_prior_models"]),
    }
    checks = [{"metric": k, "equal": left == right, "own": left, "peer": right} for k, (left, right) in pairs.items()]
    result = {"status": "PASS" if all(c["equal"] for c in checks) else "FAIL",
              "comparison_only_after_independent_computations": True, "no_network": True,
              "own_result_sha256": sha(own_path), "peer_result_sha256": sha(peer_path), "checks": checks,
              "scope": "This compares independent raw-derived facts. It does not authenticate the producer's unattached collection logs or resolve chronology. All 53 reacquired bytes additionally equal the submitted manifest, so row-count transformations can be tested on the same declared byte identities."}
    output = Path(args.output)
    (output / "cross_review_comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    marker = "\n<!-- INDEPENDENT_CROSS_COMPARISON -->\n"
    path = output / "README.md"
    prior = path.read_text().split(marker)[0]
    path.write_text(prior + marker + "\n两条独立实现完成各自计算后，才对照结果：19项计数及成员集合一致，交叉核验通过。见[交叉比对结果](cross_review_comparison.json)与[比对脚本](compare_independent_reviews.py)。该比对不改变原始附件流程和观测时序尚未认证的边界。\n", encoding="utf-8")
    with (output / "文件_SHA256.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["file", "bytes", "sha256"])
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "文件_SHA256.csv" and "__pycache__" not in path.parts:
                writer.writerow([path.relative_to(output).as_posix(), path.stat().st_size, sha(path)])
    print(json.dumps({"status": result["status"], "compared_checks": len(checks)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
