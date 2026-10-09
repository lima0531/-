#!/usr/bin/env python3
"""Independent local verification: public filtered page view -> exact-model side tables."""
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parents[1]
REGISTRY = HERE.parent / "public_energy_registry"
DATASET = Path("/workspace/file_export_proposal/v1_5/reconstruction/data_v1_5")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def fp(path):
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def main():
    cycle_path = AUDIT / "round9/public_cycle/2208型号_整篇工况补证结果_只读旁表.csv"
    purpose_path = AUDIT / "round8/final_gap_status/条件需求_型号级交叉台账.csv"
    golden_path = AUDIT / "round6/pre_review_scientific_csv_sha256.json"
    cycle_rows = read_csv(cycle_path)
    core = {row["model_key"] for row in cycle_rows}
    assert len(cycle_rows) == len(core) == 2208
    assert "JX6550T-M5BEV" not in core
    targets = {row["model_key"] for row in read_csv(purpose_path)} | core | {"JX6550T-M5BEV", "GTM6470BFEBEV", "CC7000CG00FBEV"}
    assert len(targets) == 2333
    summary_path = REGISTRY / "registry_summary.json"
    root_summary = json.loads(summary_path.read_text())
    matched = defaultdict(lambda: defaultdict(list))
    code_models = defaultdict(set)
    expected_occurrences = {}
    raw_all = []
    libraries = {}
    input_fingerprints = [fp(cycle_path), fp(purpose_path), fp(summary_path)]
    for library in ("old", "new"):
        cp_path = REGISTRY / f"{library}_checkpoint.json"
        cp = json.loads(cp_path.read_text())
        input_fingerprints.append(fp(cp_path))
        observed = []
        page_signatures = defaultdict(list)
        identifiers = Counter()
        full_rows = Counter()
        verified_pages = []
        assert len(cp["source_page_files"]) == cp["pages_validated"]
        for page_no, relative in enumerate(cp["source_page_files"], 1):
            path = REGISTRY / relative
            receipt_path = path.with_name(path.name.replace("_response.json", "_receipt.json"))
            receipt = json.loads(receipt_path.read_text())
            assert receipt["http_status"] == 200 and receipt["tls_verified"] is True
            assert receipt["file"] == relative
            assert receipt["bytes"] == path.stat().st_size
            assert receipt["sha256"] == sha(path)
            body = receipt["request_json"]
            assert body["currentPage"] == page_no
            filter_name = "fuelType" if library == "old" else "energyType"
            assert body[filter_name] == "8"
            data = json.loads(path.read_bytes())
            assert data["result"] == (1 if library == "old" else 200)
            info = data["info"]
            assert info["currentPage"] == page_no and info["pageSize"] == body["pageSize"] == 200
            assert info["totalSize"] == cp["reported_total"] and info["pages"] == cp["reported_pages"]
            assert info["pages"] == math.ceil(info["totalSize"] / info["pageSize"])
            expected_length = 200 if page_no < info["pages"] else info["totalSize"] - 200 * (info["pages"] - 1)
            assert len(info["list"]) == expected_length
            page_signature = hashlib.sha256(canonical(info["list"]).encode()).hexdigest()
            page_signatures[page_signature].append(page_no)
            verified_pages.append({"page": page_no, "response": relative, "response_sha256": sha(path), "receipt_sha256": sha(receipt_path), "list_content_sha256": page_signature, "rows": len(info["list"]), "filter": {filter_name: "8"}})
            for index, raw in enumerate(info["list"]):
                identity = raw["applyId"] if library == "old" else raw["uuid"]
                model = raw["vehicleNumber"] if library == "old" else raw["vehicleModel"]
                assert identity
                row_hash = hashlib.sha256(canonical(raw).encode()).hexdigest()
                identifiers[identity] += 1
                full_rows[row_hash] += 1
                observed.append(raw)
                raw_all.append((library, raw, relative, index))
                if model in targets:
                    occurrence = f"{library}:{page_no}:{index}"
                    assert occurrence not in expected_occurrences
                    expected_occurrences[occurrence] = {"library": library, "record_key": f"{library}:{identity}:{row_hash}", "source_occurrence": occurrence, "model_key": model, "in_core_2208": model in core, "stable_id_raw": identity, "record_number_raw": raw.get("uniqId") if library == "old" else raw.get("recordNumber"), "raw_full_row_sha256": row_hash, "source_file": relative, "json_pointer": f"/info/list/{index}", "source_sha256": sha(path), "raw_record": raw}
                    matched[model][library].append(raw)
                if library == "old" and model in core:
                    for condition in raw.get("workConditionVos") or []:
                        if condition.get("workConditionType") is not None:
                            code_models[str(condition["workConditionType"])].add(model)
            input_fingerprints += [fp(path), fp(receipt_path)]
        duplicates = [pages for pages in page_signatures.values() if len(pages) > 1]
        assert not duplicates, f"Nonadjacent repeated page detected: {library} {duplicates}"
        assert len(observed) == cp["rows"]
        if cp["completed"]:
            assert cp["pages_validated"] == cp["reported_pages"] and len(observed) == cp["reported_total"]
        libraries[library] = {"completed": cp["completed"], "reported_pages": cp["reported_pages"], "validated_pages": len(verified_pages), "reported_total": cp["reported_total"], "raw_rows": len(observed), "distinct_identifiers": len(identifiers), "distinct_full_rows": len(full_rows), "duplicate_identifier_occurrences": len(observed) - len(identifiers), "duplicate_full_row_occurrences": len(observed) - len(full_rows), "global_repeated_page_groups": duplicates, "verified_pages": verified_pages}
        assert root_summary["libraries"][library]["raw_rows_observed"] == len(observed)
        assert root_summary["libraries"][library]["distinct_stable_ids"] == len(identifiers)
        assert root_summary["libraries"][library]["distinct_full_rows"] == len(full_rows)
    assert libraries["old"]["completed"] and libraries["old"]["raw_rows"] == libraries["old"]["distinct_identifiers"] == 9336
    assert libraries["old"]["validated_pages"] == 47
    assert libraries["new"]["completed"] is False and libraries["new"]["validated_pages"] == 4
    assert libraries["new"]["raw_rows"] == 800 and libraries["new"]["distinct_identifiers"] == 797

    state_counts = Counter()
    any_hit = set()
    for model in core:
        new = matched[model]["new"]
        old = matched[model]["old"]
        status = "both_observed" if new and old else "new_observed" if new else "old_observed" if old else "no_match_in_pages_observed"
        state_counts[status] += 1
        if new or old:
            any_hit.add(model)
    code_union = set().union(*code_models.values())
    assert len(any_hit) == 1234 and len(code_union) == 1232
    assert len(code_models["CATC"]) == 818 and len(code_models["NEDC"]) == 616
    assert len(code_models["CATC"] & code_models["NEDC"]) == 202
    assert state_counts == {"old_observed": 1231, "both_observed": 2, "new_observed": 1, "no_match_in_pages_observed": 974}
    assert dict(state_counts) == root_summary["core_match_states"]
    assert len(any_hit) == root_summary["core_models_with_any_visible_exact_record"]
    assert len(code_union) == root_summary["core_models_with_old_cycle_code_observed"]

    core_table_path = REGISTRY / "2208型号_两库完整视图精确匹配.csv"
    core_table = read_csv(core_table_path)
    assert len(core_table) == len({x["model_key"] for x in core_table}) == 2208
    assert {x["model_key"] for x in core_table} == core
    for row in core_table:
        model = row["model_key"]
        assert int(row["new_raw_rows"]) == len(matched[model]["new"])
        assert int(row["old_raw_rows"]) == len(matched[model]["old"])
        codes = sorted(code for code, models in code_models.items() if model in models)
        assert json.loads(row["old_cycle_codes_raw_json"]) == codes
        assert row["old_source_view_complete"] == "True" and row["new_source_view_complete"] == "False"
        assert row["historical_public_availability_certified"] == row["same_tax_configuration_identity_certified"] == row["can_replace_frozen_scientific_input"] == "False"
    extras_path = REGISTRY / "非2208_其他用途与正对照精确匹配.csv"
    extras = read_csv(extras_path)
    assert len(extras) == 125 and {x["model_key"] for x in extras} == targets - core
    join_path = REGISTRY / "精确目标_全字段记录_只读旁表.jsonl"
    actual_occurrences = {}
    with join_path.open() as handle:
        for line in handle:
            row = json.loads(line)
            occurrence = row["source_occurrence"]
            assert occurrence not in actual_occurrences
            actual_occurrences[occurrence] = row
    assert actual_occurrences == expected_occurrences
    assert len(actual_occurrences) == root_summary["all_target_raw_rows_preserved"] == 5071
    core_join_counts = Counter(row["library"] for row in actual_occurrences.values() if row["in_core_2208"])
    assert core_join_counts == {"old": 4497, "new": 5}

    conflicts = [(lib, raw, relative, index) for lib, raw, relative, index in raw_all if raw.get("reportType") != "3" or (lib == "new" and raw.get("energyType") != "8")]
    assert len(conflicts) == root_summary["response_category_conflict_rows"] == 1
    assert conflicts[0][1]["vehicleNumber"] == "ART5010TSLS09BEV"
    conflict_csv_path = REGISTRY / "筛选视图_响应分类冲突_原行保留.csv"
    conflict_csv = read_csv(conflict_csv_path)
    assert len(conflict_csv) == 1 and conflict_csv[0]["model_raw"] == "ART5010TSLS09BEV"
    assert conflict_csv[0]["source_file"] == conflicts[0][2]
    assert conflict_csv[0]["json_pointer"] == f"/info/list/{conflicts[0][3]}"

    new_boundary_receipt_path = REGISTRY / "new_currentPage/page0005_receipt.json"
    new_boundary = json.loads(new_boundary_receipt_path.read_text())
    boundary_body_path = REGISTRY / new_boundary["file"]
    assert new_boundary["http_status"] == 403
    assert new_boundary["sha256"] == sha(boundary_body_path) and new_boundary["bytes"] == boundary_body_path.stat().st_size
    assert b"No approved upstream IPv4 address" in boundary_body_path.read_bytes()
    assert len(list((REGISTRY / "new_currentPage").glob("page0005*_receipt.json"))) == 1

    golden = json.loads(golden_path.read_text())
    scientific_actual = {}
    assert len(golden) == 52
    for relative, expected in golden.items():
        path = DATASET / Path(relative).relative_to("reconstruction/data_v1_5")
        assert sha(path) == expected["sha256"] and path.stat().st_size == expected["bytes"]
        scientific_actual[relative] = sha(path)
    input_fingerprints += [fp(core_table_path), fp(extras_path), fp(join_path), fp(conflict_csv_path), fp(new_boundary_receipt_path), fp(boundary_body_path), fp(golden_path)]
    checks = [
        "All 47 old accepted receipts and raw page bytes verified; totals/currentPage/pageSize/list lengths reconcile 9336 visible rows.",
        "All 4 accepted new pages verified; 800 raw rows, 797 identifiers, 800 distinct full rows; incomplete 53-page view preserved.",
        "Global list-content hashes for accepted pages are unique within each library, including nonadjacent comparisons.",
        "2208 fixed keys independently joined by exact raw model equality; any-record hits 1234, no hit in observed pages 974.",
        "Old raw cycle-code model sets independently recomputed: union1232/CATC818/NEDC616/intersection202.",
        "Every one of 5071 target JSONL occurrences equals its original page/list entry, complete raw JSON and hash included.",
        "Core target JSONL contains old4497/new5 row occurrences; 125 noncore target rows kept separate.",
        "One response category-conflict row retained and locators independently reconciled.",
        "New page5 HTTP403 body and SHA verified, no further page5 attempt in saved receipts.",
        "All 52 scientific CSV files match golden SHA256 and bytes; side-table freeze/identity replacement flags remain false.",
    ]
    report = {
        "status": "PASS",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "independent_local_read_only_no_network",
        "libraries": libraries,
        "fixed_model_count": len(core),
        "core_models_with_any_visible_exact_record": len(any_hit),
        "core_match_states": dict(state_counts),
        "core_models_with_old_code": len(code_union),
        "old_raw_code_model_counts": {code: len(models) for code, models in code_models.items()},
        "CATC_NEDC_model_intersection": len(code_models["CATC"] & code_models["NEDC"]),
        "target_universe_models": len(targets),
        "target_jsonl_rows": len(actual_occurrences),
        "core_target_jsonl_rows_by_library": dict(core_join_counts),
        "category_conflict_count": len(conflicts),
        "category_conflict_model": conflicts[0][1]["vehicleNumber"],
        "new_page5_boundary": {"http_status": 403, "response_text": boundary_body_path.read_text(), "saved_attempts": 1, "response_sha256": sha(boundary_body_path)},
        "scientific_csv_count": len(scientific_actual),
        "scientific_csv_sha256": scientific_actual,
        "frozen_cycle_gap_closed": 0,
        "numeric_ready_delta": 0,
        "battery_energy_gap_closed": 0,
        "boundaries": [
            "Old complete means all 47 pages/9336 rows of the observed public fuelType8 filtered view, not exhaustive hidden or global historical records.",
            "New incomplete: the 974 no-match models are not certified zero across both libraries; new unobserved pages remain unknown.",
            "Pagination is not an atomic snapshot; stable counts and page uniqueness cannot prove absence of every possible concurrent migration.",
            "CATC/NEDC are preserved raw codes; no mechanical CATC-to-CLTC-P conversion or applied historical tax-configuration mapping.",
            "No exact-model hit count is a frozen-information, same-configuration, legal-eligibility or same-cycle closure count.",
            "403 response was captured as an access boundary; review did not retry, route around it or call the network.",
        ],
        "checks_passed": checks,
        "input_fingerprints": input_fingerprints,
    }
    output = HERE / "registry_join_readonly_review.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "any_hit": len(any_hit), "codes": len(code_union), "CATC": len(code_models["CATC"]), "NEDC": len(code_models["NEDC"]), "intersection": report["CATC_NEDC_model_intersection"], "target_jsonl": len(actual_occurrences), "science52": len(scientific_actual), "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
