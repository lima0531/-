#!/usr/bin/env python3
"""Read-only review of one explicit, source-bound catalogue field correction.

Does not edit any canonical research CSV. The independently converted DOCX
is a reading derivative, never a replacement for the byte-verified Word source.
"""
import csv
import hashlib
import json
import re
import sys
import zipfile
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DATA = ROOT / "round4/data_v1_4"
sys.path.insert(0, str(ROOT / "round3/archive"))
from word_piece_text import extract

MODEL = "SGM6500BEBEV"
BASE_ID = "old-62-Word97--0-7"
PATCH_ID = "old-text-correction-64-SGM6500BEBEV"
BASE_SHA = "7694ac7207998b6af7c895cdd2c1d752421df436d4b28f83195261dd47f6509c"
PATCH_SHA = "c4e238989e7e40ec2c3a6a899ead170b4a745bc72546ba6fd4a5731d8890c6cb"
QUOTE = "勘误：《免征车辆购置税的新能源汽车车型目录》（第六十二批）纯电动乘用车部分第6项，上汽通用汽车有限公司凯迪拉克(CADILLAC)牌SGM6500BEBEV纯电动多用途乘用车，纯电动续驶里程应为608km。"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_csv(rel):
    with (DATA / rel).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    base_source = ROOT / "round3/archive/recovered/免征目录/mf_batch62.doc"
    patch_source = ROOT / "round5/originals/mf_batch64.doc"
    base_text, base_proof = extract(base_source)
    patch_text, patch_proof = extract(patch_source)
    assert hashlib.sha256(base_source.read_bytes()).hexdigest() == BASE_SHA
    assert hashlib.sha256(patch_source.read_bytes()).hexdigest() == PATCH_SHA
    assert patch_text.count(QUOTE) == 1
    # A text quotation is insufficient on its own: enumerate the original
    # passenger table, locate its unique model row, and verify the data-item
    # ordinal named in the correction.
    base_docx = zipfile.ZipFile(OUT / "converted/mf_batch62.docx")
    doc = ET.fromstring(base_docx.read("word/document.xml"))
    table = list(doc.iter(W + "tbl"))[0]
    rows = []
    for tr in table.findall(W + "tr"):
        rows.append(["".join(t.text or "" for t in tc.iter(W + "t")) for tc in tr.findall(W + "tc")])
    assert rows[0] == ["序号", "汽车生产企业名称", "车辆型号", "通用名称", "纯电动续驶里程(km)", "整车整备质量(kg)", "动力蓄电池组总质量(kg)", "动力蓄电池组总能量(kWh)", "备注"]
    model_rows = [(idx, cells) for idx, cells in enumerate(rows) if cells[2] == MODEL]
    assert model_rows == [(6, ["", "", MODEL, "LYRIQ", "502", "2620", "620", "95.7", ""])]
    numbering = ET.fromstring(base_docx.read("word/numbering.xml"))
    num = next(n for n in numbering.findall(W + "num") if n.get(W + "numId") == "8")
    abstract_id = num.find(W + "abstractNumId").get(W + "val")
    abstract = next(n for n in numbering.findall(W + "abstractNum") if n.get(W + "abstractNumId") == abstract_id)
    lvl = next(n for n in abstract.findall(W + "lvl") if n.get(W + "ilvl") == "0")
    assert lvl.find(W + "start").get(W + "val") == "1"
    assert lvl.find(W + "numFmt").get(W + "val") == "decimal"
    assert num.find(W + "lvlOverride") is None
    for tr in table.findall(W + "tr")[1:7]:
        numpr = tr.findall(W + "tc")[0].find(".//" + W + "numPr")
        assert numpr.find(W + "numId").get(W + "val") == "8"
        assert numpr.find(W + "ilvl").get(W + "val") == "0"
    assert rows[5][1] == "上汽通用汽车有限公司"
    assert base_text.count(MODEL) == 1
    assert MODEL in patch_text and "纯电动乘用车部分第6项" in QUOTE

    parameters = read_csv("研究数据/参数版本_原值与计算代理.csv")
    records = [r for r in parameters if r["model_key"] == MODEL]
    ids = {r["record_id"]: r for r in records}
    parent = ids[BASE_ID]
    patch = ids[PATCH_ID]
    assert parent["source_sha256"] == BASE_SHA and patch["source_sha256"] == PATCH_SHA
    assert parent["publish_date_exact"] == "2023-02-20"
    assert patch["publish_date_exact"] == "2023-04-17"
    assert parent["range_raw"] == "502" and patch["range_raw"] == "608"
    for field, value in [("curb_mass", "2620"), ("battery_mass", "620"), ("battery_energy", "95.7")]:
        assert parent[field + "_raw"] == value
        assert patch[field + "_raw"] == ""
        assert patch[field + "_point"] == ""

    snapshots = read_csv("研究数据/重建样本_两截点参数与暴露.csv")
    frozen = next(r for r in snapshots if r["model_key"] == MODEL and r["cutoff"] == "2023-12-10")
    risk_rows = read_csv("研究数据/公告前风险集_连续处理强度输入.csv")
    risk = next(r for r in risk_rows if r["model_key"] == MODEL)
    assert frozen["possible_latest_record_ids"] == PATCH_ID
    assert frozen["range_point"] == "608" and frozen["density_proxy_point"] == ""
    assert risk["announcement_active_observed"] == "1" and risk["descriptive_continuous_did_input_ready"] == "0"

    density = str(Decimal("1000") * Decimal("95.7") / Decimal("620"))
    assert density == parent["density_proxy_point"]
    panel = [r for r in read_csv("研究数据/车型月度面板_2022至2024.csv") if r["model_key"] == MODEL]
    monthly_density_restored = [r["month"] for r in panel if r["parameter_possible_latest_ids"] == PATCH_ID and r["density_proxy_record_point"] == ""]
    assert monthly_density_restored == [f"2023-{m:02d}" for m in range(4, 12)]
    join = next(r for r in read_csv("官方技术清单/重建3328_官方清单标记与资格轨迹.csv") if r["model_key"] == MODEL)
    assert join["official_nonconformance_list_presence_observed"] == "0"
    assert join["post2024_withdrawal_observed"] == "0"

    # Proposed effective view: retain the logical correction ID, date, physical
    # raw values, and unknown identity flags. Only calculation fields inherit.
    candidate = dict(patch)
    inherited_columns = []
    for field in ["curb_mass", "battery_mass", "battery_energy"]:
        for suffix in ["lower", "upper", "point", "values_new", "parse_status_new"]:
            column = field + "_" + suffix
            candidate[column] = parent[column]
            inherited_columns.append(column)
    for suffix in ["lower", "point", "upper"]:
        candidate["density_proxy_" + suffix] = density
    assert candidate["record_id"] == PATCH_ID
    assert all(candidate[f + "_raw"] == "" for f in ["curb_mass", "battery_mass", "battery_energy"])
    assert candidate["full_configuration_match_verified"] == "0"
    assert candidate["entity_verified"] == "0"
    assert candidate["same_cycle_comparability_verified"] == "0"
    assert candidate["low_temperature_evidence_obtained"] == "0"

    field_provenance = []
    for field in ["range", "curb_mass", "battery_mass", "battery_energy"]:
        source = patch if field == "range" else parent
        field_provenance.append({
            "model_key": MODEL,
            "effective_record_id": PATCH_ID,
            "field": field,
            "effective_point": candidate[field + "_point"],
            "physical_raw_in_correction": patch[field + "_raw"],
            "source_record_id": source["record_id"],
            "source_file": source["source_file"],
            "source_sha256": source["source_sha256"],
            "source_location": source["source_location"],
            "field_source_observed_date": source["publish_date_exact"],
            "effective_version_available_date": patch["publish_date_exact"],
            "derivation": "明确替换字段" if field == "range" else "明确目标条目其余字段原值承接",
            "full_configuration_match_verified": "0",
            "legal_eligibility_certified": "0",
        })
    with (OUT / "字段继承建议与逐字段来源.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(field_provenance[0]))
        writer.writeheader()
        writer.writerows(field_provenance)

    summary = {
        "status": "explicit_source_bound_partial_correction_supported",
        "scope": "目录条目字段更正的可重现计算承接；不作逐车法律资格认定",
        "reproducible_assertions_passed": True,
        "canonical_csv_mutated": False,
        "raw_parameter_rows": len(parameters),
        "source_proofs": {"base62": base_proof, "correction64": patch_proof},
        "correction_quote": QUOTE,
        "correction_primary_main_story_character_slice_0based": [patch_text.index(QUOTE), patch_text.index(QUOTE) + len(QUOTE)],
        "target_logical_record_id": BASE_ID,
        "correction_logical_record_id": PATCH_ID,
        "target_table_derivative_location": {"table_0based": 0, "row_0based_including_header": 6, "data_item_1based": 6, "model_column_0based": 2, "range_column_0based": 4, "curb_mass_column_0based": 5, "battery_mass_column_0based": 6, "battery_energy_column_0based": 7},
        "target_source_location_preserved": parent["source_location"],
        "correction_source_location_preserved": patch["source_location"],
        "unambiguous_original_passenger_table_model_match_count": len(model_rows),
        "target_automatic_numbering_independently_checked": {"numId": 8, "level": 0, "number_format": "decimal", "start": 1, "first_six_data_rows_same_numbering_instance": True, "target_rendered_sequence": 6},
        "field_replacement": {"range": {"old": "502", "corrected": "608"}},
        "inherited_unmodified_fields": {"curb_mass": "2620", "battery_mass": "620", "battery_energy": "95.7"},
        "derived_density_proxy_Wh_per_kg": density,
        "effective_view_inherited_calculation_columns": inherited_columns,
        "do_not_use_future_record": "new-01-cell-4193 / 2023-12-26",
        "availability_rule": "更正视图自 2023-04-17 公开观察信息集使用；不将 608 回填此前月度参数观察",
        "expected_delta_if_only_this_source_bound_patch_is_applied": {
            "risk_models": {"before": 2805, "after": 2805},
            "numeric_ready_models": {"before": 2424, "after": 2425},
            "single_value_insufficient_models": {"before": 381, "after": 380},
            "both_numeric_thresholds_met_layer": {"before": 1821, "after": 1822},
            "frozen_range_exposure": {"before": "0", "after": "0"},
            "frozen_density_exposure": {"before": "", "after": "0"},
            "frozen_joint_max_exposure": {"before": "", "after": "0"},
            "monthly_record_density_blank_to_source_bound_value_months": monthly_density_restored,
            "monthly_frozen_exposure_and_ready_flag_updated_rows": len(panel),
            "member_and_eligibility_event_changes": 0,
            "official_marked_threshold_met_count_changes": 0,
        },
    }
    (OUT / "partial_correction_review.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "canonical_csv_mutated": False, "output": str(OUT), "source_match_count": len(model_rows), "monthly_record_density_restored": monthly_density_restored}, ensure_ascii=False))


if __name__ == "__main__":
    main()
