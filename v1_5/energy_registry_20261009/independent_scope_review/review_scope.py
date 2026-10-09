#!/usr/bin/env python3
"""Local, read-only review of a new JX label against the frozen scientific set."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import fitz


MODEL = "JX6550T-M5BEV"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def metadata(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def decode_frontend(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    decoded = []
    for match in re.finditer(r'eval\(("(?:[^"\\]|\\.)*")\);', raw):
        try:
            decoded.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            pass
    return "\n".join(decoded) if decoded else raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("/workspace/file_export_proposal/v1_5/reconstruction/data_v1_5"))
    parser.add_argument("--round9", type=Path, default=Path("/workspace/purchase_tax_audit/round9"))
    parser.add_argument("--pdf", type=Path, default=Path("/workspace/attachments/b272bb15-e257-4e29-8725-0c511b7095c2/JX6550T-M5BEV_完整标签.pdf"))
    parser.add_argument("--records", type=Path, default=Path("/workspace/attachments/420294dd-954f-4c1d-9a22-949f476755b6/原始记录_全程字段.json"))
    parser.add_argument("--uploaded-readme", type=Path, default=Path("/workspace/attachments/2f9d84c3-866c-41df-9751-cc9bf8d8fc8c/README.md"))
    parser.add_argument("--gold", type=Path, default=Path("/workspace/purchase_tax_audit/round6/pre_review_scientific_csv_sha256.json"))
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    golden = json.loads(args.gold.read_text(encoding="utf-8"))
    scientific_before = {}
    for relative, expected in golden.items():
        path = args.dataset / Path(relative).relative_to("reconstruction/data_v1_5")
        actual = metadata(path)
        assert actual["sha256"] == expected["sha256"], relative
        assert actual["bytes"] == expected["bytes"], relative
        scientific_before[relative] = actual["sha256"]
    assert len(scientific_before) == 52

    trajectory_path = args.dataset / "官方技术清单/重建3328_官方清单标记与资格轨迹.csv"
    snapshot_path = args.dataset / "研究数据/重建样本_两截点参数与暴露.csv"
    exposure_path = args.dataset / "研究数据/公告前风险集_连续处理强度输入.csv"
    effective_path = args.dataset / "研究数据/参数版本_字段勘误生效视图.csv"
    cycle_path = args.round9 / "public_cycle/2208型号_整篇工况补证结果_只读旁表.csv"
    trajectory = rows(trajectory_path)
    snapshots = rows(snapshot_path)
    exposures = rows(exposure_path)
    effective = rows(effective_path)
    cycle = rows(cycle_path)
    risk = {x["model_key"] for x in trajectory if x["in_preannouncement_active_riskset"] == "1"}
    ready = {x["model_key"] for x in trajectory if x["in_preannouncement_active_riskset"] == "1" and x["numeric_input_ready"] == "1"}
    explicit = {x["model_key"] for x in trajectory if x["in_preannouncement_active_riskset"] == "1" and x["numeric_input_ready"] == "1" and x["range_cycle_explicit"]}
    unmarked = ready - explicit
    cycle_set = {x["model_key"] for x in cycle}
    assert (len(risk), len(ready), len(explicit), len(unmarked)) == (2805, 2425, 217, 2208)
    assert len(cycle) == len(cycle_set) == 2208 and cycle_set == unmarked
    assert MODEL in risk and MODEL not in ready and MODEL not in cycle_set

    jx_trajectory = [x for x in trajectory if x["model_key"] == MODEL]
    jx_snapshots = [x for x in snapshots if x["model_key"] == MODEL]
    jx_exposures = [x for x in exposures if x["model_key"] == MODEL]
    jx_effective = [x for x in effective if x["model_key"] == MODEL]
    frozen = next(x for x in jx_snapshots if x["cutoff"] == "2023-12-10")
    assert frozen["battery_energy_point"] == "" and frozen["two_parameter_point_available"] == "0"
    late = next(x for x in jx_snapshots if x["cutoff"] == "2023-12-31")
    assert late["battery_energy_point"] == "65.17" and late["possible_date_upper_max"] == "2023-12-26"

    api_snapshot = json.loads(args.records.read_text(encoding="utf-8-sig"))
    records = api_snapshot["info"]["list"]
    assert len(records) == api_snapshot["info"]["totalSize"] == 2
    assert {x["vehicleModel"] for x in records} == {MODEL}
    assert {x["completeVehicleQuality"] for x in records} == {"2295", "2360"}
    assert {x["issueDate"] for x in records} == {"2021-09-30"}
    assert {x["activationDate"] for x in records} == {"2024-07-15"}
    assert {x["overtimeCause"] for x in records} == {"老数据切换新油耗系统"}

    pdf = fitz.open(args.pdf)
    text = "\n".join(page.get_text() for page in pdf)
    assert len(pdf) == 1
    assert "GD20240715105558048" in text and MODEL in text
    assert "GB/T 18386.1—2021" in text
    assert "电池组总能量" not in text
    assert not any(word in text for word in ("CLTC", "NEDC", "WLTC"))
    pdf_meta = pdf.metadata
    pdf.close()

    fields = ("issueDate", "activationDate", "enableDate", "submitDate", "createTime", "updateTime", "overtimeCause")
    frontend = []
    frontend_paths = sorted((args.round9 / "public_configuration/portal").glob("energy_script_*.js"))
    assert len(frontend_paths) == 2
    for path in frontend_paths:
        source = decode_frontend(path)
        finding = metadata(path)
        finding["occurrences"] = {field: source.count(field) for field in fields}
        finding["activationDate_label_mapping_verified"] = bool(re.search(r'label:\s*"启用日期",\s*prop:\s*"activationDate"', source))
        finding["issueDate_contexts"] = [source[max(0, m.start() - 150):m.end() + 200] for m in re.finditer("issueDate", source)]
        frontend.append(finding)
    assert sum(x["occurrences"]["issueDate"] for x in frontend) == 0
    assert any(x["activationDate_label_mapping_verified"] for x in frontend)

    input_paths = [args.pdf, args.records, args.uploaded_readme, args.gold, trajectory_path, snapshot_path, exposure_path, effective_path, cycle_path, *frontend_paths]
    report = {
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "local_read_only_no_network_no_scientific_mutation",
        "input_provenance_scope": "User-uploaded PDF/API response snapshot plus existing frozen local science and cached public frontend. This review does not independently establish a current network retrieval from the official host.",
        "model": MODEL,
        "membership": {"risk_models": len(risk), "numeric_ready_models": len(ready), "numeric_insufficient_models": len(risk-ready), "ready_explicit_cycle_models": len(explicit), "ready_unmarked_cycle_models": len(unmarked), "round9_cycle_rows": len(cycle), "round9_cycle_set_exact_matches_ready_unmarked": cycle_set == unmarked, "jx_in_risk": MODEL in risk, "jx_numeric_ready": MODEL in ready, "jx_in_2208_cycle_scope": MODEL in cycle_set},
        "jx_canonical_rows": {"trajectory": jx_trajectory, "cutoff_snapshots": jx_snapshots, "exposure": jx_exposures, "effective_parameter_versions": jx_effective},
        "provided_api_records": [{key: x.get(key) for key in ("recordNumber", "vehicleModel", "completeVehicleQuality", "drivingRange", "electricEnergyConsumption", "driveMotorPeakPower", "testBasisStandard", "issueDate", "enableDate", "activationDate", "submitDate", "createTime", "updateTime", "overtimeCause", "fullLabel", "hypothermyDrivingRange", "hypothermyDrivingRangeReportNum", "hypothermyDrivingRangeReportNumPath")} for x in records],
        "pdf_local_evidence": {**metadata(args.pdf), "pages": 1, "metadata": pdf_meta, "recordNumber": "GD20240715105558048", "standard_explicit": "GB/T 18386.1—2021", "cycle_explicit": None, "activation_date_printed": "2024-07-15", "issue_date_printed": None, "battery_total_energy_present": False, "industry_low_temperature_decline_text": "低温开暖风行业续驶里程平均约下降：40%", "industry_average_is_model_low_temperature_test": False},
        "cached_frontend_field_semantics": {"files": frontend, "activationDate_chinese_label": "启用日期", "issueDate_chinese_label": None, "issueDate_report_issuance_semantics_verified": False, "reason": "issueDate has zero occurrences in the two cached frontend files; an English field name does not prove report-issuance meaning."},
        "time_and_identity_boundaries": {"api_issueDate_claimed": "2021-09-30", "api_issueDate_meaning_verified": False, "current_record_migration_date": "2024-07-15", "pdf_creation_date": pdf_meta.get("creationDate"), "official_historical_first_public_availability_verified": False, "available_before_20231210_certified": False, "same_tax48_configuration_certified": False, "same_range_and_curb_mass_are_candidate_links_only": True, "standard_revision_does_not_automatically_prove_specific_cycle": True, "no_future_energy_backfill": True},
        "closure_effect": {"new_candidate_model_in_separate_evidence_table": 1, "api_record_rows_observed_in_user_snapshot": 2, "full_label_pdfs_in_user_uploads": 1, "explicit_standard_revision_in_received_pdf": 1, "numeric_ready_delta": 0, "numeric_insufficient_delta": 0, "2208_cycle_gap_closed": 0, "battery_total_energy_gap_closed": 0, "cross_catalogue_configuration_identity_closed": 0, "official_low_temperature_test_report_closed": 0, "pre_freeze_public_information_gap_closed": 0},
        "instructions_in_attachment_not_executed": ["bulk-query recommendation", "replace previous public-source query instructions"],
        "input_fingerprints": [metadata(path) for path in input_paths],
        "scientific_csv_count": len(scientific_before),
        "scientific_csv_sha256_before": scientific_before,
    }
    scientific_after = {}
    for relative in scientific_before:
        path = args.dataset / Path(relative).relative_to("reconstruction/data_v1_5")
        scientific_after[relative] = sha(path)
    assert scientific_after == scientific_before
    report["scientific_csv_sha256_unchanged"] = True
    report["checks_passed"] = [
        "Risk/ready/cycle counts recomputed, 2805/2425/217/2208.",
        "All 2208 cycle-input keys exactly equal ready minus explicit-cycle.",
        "JX is risk-set member, numeric insufficient, and outside cycle-2208.",
        "Tax48 pre-freeze energy stays blank; 65.17 belongs only to 2023-12-26 later source.",
        "API snapshot has exactly two JX records and migration/date evidence retained separately.",
        "Received PDF explicitly states 2021 standard, current activation, and no specific cycle/capacity.",
        "Cached frontend maps activationDate, but has no issueDate semantics evidence.",
        "All 52 scientific CSV fingerprints match the golden set and are unchanged after review.",
    ]
    (args.output / "review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "README.md").write_text("""# JX官方能耗新材料：范围与冻结口径独立复核

用户交付的标签提供了有价值的新旁证，但 **JX6550T-M5BEV不在2208个工况待补型号的集合内**，不能据此把2208改成2207。52份科学CSV与既定SHA256基准完全一致，本复核未联网、未修改旧数据或Git。

## 集合口径

重新读取3328行规范轨迹表及2208行工况旁表：公告前风险集2805，其中单值可用2425；2425中明确标注工况217，未标2208。工况旁表的型号集合与“2425减217”逐键完全一致。JX属于风险集中的380个单值不足型号，`numeric_input_ready=0`、`descriptive_continuous_did_input_ready=0`，故不属于2425，也不属于2208。

第48批原记录`old-48-Word97--0-20`的电池总能量为空；2023-12-10快照保持空值。2023-12-31快照的65.17kWh仅来自2023-12-26减免第1批`new-01-cell-12377`，不能倒填公告前。新材料也未提供总能量。

## 新材料已证明及尚未证明

输入API快照确有两条该型号记录，整备质量2295/2360kg、续航293km；本次收到的完整PDF只对应2360kg、备案号`GD20240715105558048`，80,946字节，SHA256为`0721063c8b32892350150e56381ef4280bd6d10913429f85c5e476065c5a40ec`。PDF明确写按GB/T18386.1—2021测定，但未明确写NEDC/CLTC/WLTC，试验标准版次不能自动改成一个具体工况标签。第二条API记录也有`testBasisStandard=5`，其独立PDF及标准字典映射须由主线另验。

两个API记录的`issueDate`为2021-09-30；`enableDate`、`activationDate`、`submitDate`为2024-07-15，创建和更新也为该日，`overtimeCause`为“老数据切换新油耗系统”。PDF纸面只显示启用日2024-07-15；本地元数据生成日同为2024-07-15。缓存前端两份JS全解码后，`activationDate`明确映射“启用日期”，`issueDate`出现0次，故本轮不能确认它的中文语义，不能直接称为“官方检测报告出具日期”。这也不能证明该标签在2023-12-10前已公开可得；记录迁移日期不是否认历史试验存在，历史字段日期也不是证明此前公开。

整备质量和续航相同只形成配置候选连接，不能确认税48、推荐目录NC010086和能耗备案是同一配置/申报版本。若用于冻结输入，仍须配置对应及此前公开可得的证据；若只研究历史测试事实，可另设事后获取的历史证据旁表，保留日期语义未知标记。

标签“低温开暖风行业续驶里程平均约下降40%”是行业提示，不是该型号按附录A完成的低温报告；快照相应低温续驶里程、报告编号和报告路径均为空，不能关闭低温例外证据缺口。

## 可关闭的工作项

可新增1型号、2条能耗备案快照、1份已收到的完整标签，记录显式试验标准版次及2024年启用信息。当前可关闭的是“找到公开能耗资料路径/记录”的采集项；核心总能量、跨目录配置认证、公告前公开可得时间、明确同工况比较和车型低温检测报告仍未闭合。

所有新增内容适合先放证据旁表。本复核计算影响为：2425不变，380不变，2208不变，JX总能量缺口仍为1型号1字段。批量取得其他型号资料后，逐版本核对配置、时间和具体工况，另行统计能关闭的数量；不能以查询命中数直接减去工况缺口。

## 证据及复现

- [逐项复核JSON](review.json)保留规范原行、日期、字段语义检查、上传件及全部科学文件SHA256。
- [复核脚本](review_scope.py)仅本地读文件，参数可重映射数据根目录和上传件路径。
- [输出SHA清单](文件_SHA256.csv)不包含自身。

本报告区分用户交付的原文件/接口快照与当前官方服务的独立联网重取；后者由主线另验。附件中的批量查询建议及“替换交接说明”措辞属于待评估意见，本独立只读复核没有执行这些指令。
""", encoding="utf-8")
    with (args.output / "文件_SHA256.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "bytes", "sha256"])
        writer.writeheader()
        for path in sorted(args.output.glob("*")):
            if path.is_file() and path.name != "文件_SHA256.csv":
                writer.writerow({"file": path.name, "bytes": path.stat().st_size, "sha256": sha(path)})
    print(json.dumps({"output": str(args.output), "risk": len(risk), "ready": len(ready), "cycle_gap": len(unmarked), "jx_in_2208": False, "scientific_52_unchanged": True, "checks": len(report["checks_passed"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
