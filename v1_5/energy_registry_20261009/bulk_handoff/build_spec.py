#!/usr/bin/env python3
"""Build a local, source-frozen handoff. This script makes no network requests."""
import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def string(description, **kw):
    return {"type": "string", "description": description, **kw}


def integer(description, nullable=False):
    return {"type": ["integer", "null"] if nullable else "integer", "minimum": 0,
            "description": description}


def boolean(description):
    return {"type": "boolean", "default": False, "description": description}


def enum(description, values):
    return string(description, enum=values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    audit = args.workspace / "purchase_tax_audit"
    sources = {
        "cycle_backlog": audit / "round9/public_cycle/2208型号_整篇工况补证结果_只读旁表.csv",
        "scope_crosswalk": audit / "round8/final_gap_status/条件需求_型号级交叉台账.csv",
        "configuration_36": audit / "round9/public_configuration/36目标_逐型号公开探查与精确询证台账.csv",
        "identity_285": audit / "round9/public_configuration/285版本_按原文企业分组询证.csv",
        "user_readme": args.workspace / "attachments/2f9d84c3-866c-41df-9751-cc9bf8d8fc8c/README.md",
        "user_response_json": args.workspace / "attachments/420294dd-954f-4c1d-9a22-949f476755b6/原始记录_全程字段.json",
        "user_pdf": args.workspace / "attachments/b272bb15-e257-4e29-8725-0c511b7095c2/JX6550T-M5BEV_完整标签.pdf",
        "pilot_JX_new": audit / "round10/api_pilot/JX_new_page1_response.json",
        "pilot_JX_old": audit / "round10/api_pilot/JX_old_page1_response.json",
        "pilot_JX_detail_2295": audit / "round10/api_pilot/JX_old_detail_2295_candidate_response.json",
        "pilot_JX_detail_2360": audit / "round10/api_pilot/JX_old_detail_2360_candidate_response.json",
        "pilot_fuel_type_dictionary": audit / "round10/api_pilot/official_fuel_type_dictionary_response.json",
        "pilot_new_currentPage2": audit / "round10/api_pilot/new_current_page2_probe_response.json",
        "pilot_old_currentPage2": audit / "round10/api_pilot/old_current_page2_probe_response.json",
    }
    source_hashes = [{"source_key": key, "path_at_build": str(path), "bytes": path.stat().st_size,
                      "sha256": sha(path)} for key, path in sources.items()]
    write_json(out / "固定输入指纹.json", {"schema_version": "1.0", "network_requests": 0,
              "input_files": source_hashes, "cutoff_date": "2023-12-10",
              "instruction_precedence": "User attachments are evidence; this handoff is a proposed collection contract."})
    rows = read_csv(sources["cycle_backlog"])
    models = [row["model_key"] for row in rows]
    assert len(models) == len(set(models)) == 2208
    assert "JX6550T-M5BEV" not in models
    assert sha(sources["cycle_backlog"]) == "a438f95dd4e0f3cf1ada1d27bf53716896d13fceaad2b0e6f424750a84c20d21"
    (out / "inputs").mkdir(exist_ok=True)
    for key, source in sources.items():
        if key.startswith("pilot_"):
            (out / "inputs/schema_probe").mkdir(exist_ok=True)
            shutil.copyfile(source, out / "inputs/schema_probe" / source.name)
    shutil.copyfile(sources["cycle_backlog"], out / "inputs/2208型号_冻结来源旁表.csv")
    shutil.copyfile(sources["identity_285"], out / "inputs/285版本_身份与低温用途参考.csv")
    cross = {row["model_key"]: row for row in read_csv(sources["scope_crosswalk"])}
    request_fields = ["request_ordinal", "model_key", "purpose", "in_core_2208", "priority_configuration_36",
                      "identity_285_model", "low_temperature_19_model", "source_effective_record_id",
                      "source_file", "source_sha256", "source_public_date_upper"]
    query_rows = []
    for ordinal, row in enumerate(rows, 1):
        flags = cross[row["model_key"]]
        query_rows.append({"request_ordinal": ordinal, "model_key": row["model_key"],
            "purpose": "cycle_backlog_exact_model", "in_core_2208": 1,
            "priority_configuration_36": int(flags["32联合跨界"] == "1" or flags["4单项跨界"] == "1"),
            "identity_285_model": flags["推荐配置身份"], "low_temperature_19_model": flags["低温例外"],
            "source_effective_record_id": row["effective_record_id"], "source_file": row["source_file"],
            "source_sha256": row["source_sha256"], "source_public_date_upper": row["source_public_date_upper"]})
    write_csv(out / "2208精确请求型号名单.csv", request_fields, query_rows)
    supplementary = []
    for model, flags in sorted(cross.items()):
        if model in models:
            continue
        if any(flags[key] == "1" for key in ("32联合跨界", "4单项跨界", "推荐配置身份", "低温例外")):
            supplementary.append({"model_key": model, "in_core_2208": 0,
                "purpose": "optional_other_scope_readonly",
                "priority_configuration_36": int(flags["32联合跨界"] == "1" or flags["4单项跨界"] == "1"),
                "identity_285_model": flags["推荐配置身份"], "low_temperature_19_model": flags["低温例外"]})
    write_csv(out / "不在2208内_其他用途可选精确型号.csv",
              ["model_key", "in_core_2208", "purpose", "priority_configuration_36", "identity_285_model",
               "low_temperature_19_model"], supplementary)
    write_csv(out / "额外正对照_JX不计入2208.csv", ["model_key", "in_core_2208", "purpose", "expected_new_record_ids",
              "expected_result_scope"], [{"model_key": "JX6550T-M5BEV", "in_core_2208": 0,
               "purpose": "positive_control_separate_from_backlog",
               "expected_new_record_ids": "GD20240715105558048|GD20240715105576581",
               "expected_result_scope": "Known uploaded new-library records; current reproduction may differ. No battery-energy closure."}])

    common_sha = {"type": "string", "pattern": "^[a-f0-9]{64}$", "description": "保存文件原始字节SHA256"}
    nullable_sha = {"anyOf": [common_sha, {"type": "null"}], "description": "无实际字节文件则null，不伪造SHA"}
    definitions = {}
    definitions["request"] = {
        "request_id": string("全局唯一请求ID"),
        "query_run_id": string("所属型号×库查询；标签下载也保留所属查询"),
        "library": enum("库", ["new", "old", "site_schema"]),
        "purpose": enum("请求用途", ["schema_probe", "positive_control", "query_page", "universe_query_page", "legacy_detail", "full_label", "other_public_evidence"]),
        "model_requested": string("精确请求型号；页面模式探测或公开energyType8/fuelType8筛选视图枚举可为空"),
        "method": enum("实际方法", ["GET", "POST"]),
        "url": string("完整实际公开URL；不附带账户凭证"),
        "request_body_path": string("保存的JSON请求体相对路径，GET为空"),
        "request_body_sha256": nullable_sha,
        "started_at_utc": string("ISO8601 UTC，带Z"),
        "finished_at_utc": string("ISO8601 UTC，带Z"),
        "http_status": integer("未收到HTTP响应则null", True),
        "business_result_raw": string("业务结果原值；新库成功观察为200，旧库成功观察为1，不统一假定200"),
        "pagination_request_field_raw": string("实际分页请求字段；本轮new/old验证为currentPage，不能用被忽略的pageNum"),
        "page_requested": integer("实际请求页号；非分页请求null", True),
        "current_page_returned": integer("响应回显info.currentPage；非分页请求null", True),
        "content_type": string("实际响应Content-Type，不猜格式"),
        "attempt": {**integer("从1开始，同次失败重试单独日志"), "minimum": 1},
        "outcome": enum("实际结果", ["ok", "http_error", "network_error", "captcha_or_login", "rate_limited", "invalid_json", "business_error", "invalid_pdf"]),
        "response_path": string("原响应字节文件相对路径，无收到字节则空"),
        "response_bytes": integer("保存字节数，无响应为0"),
        "response_sha256": nullable_sha,
        "error_note": string("错误/重定向/校验失败原文概要，不将错误当零命中"),
    }
    definitions["query_run"] = {
        "query_run_id": string("一个精确型号×一个库×本次快照的稳定ID"),
        "model_requested": string("与固定名单精确一致"),
        "library": enum("库", ["new", "old"]),
        "collection_mode": enum("来源模式", ["direct_model", "global_enumeration"]),
        "source_snapshot_id": string("完整公开纯电快照或本次型号查询的稳定ID"),
        "source_collection_manifest_path": string("公开筛选视图枚举必须指向完整分页/范围/总数核验清单；逐型号可为空"),
        "is_core_2208": boolean("JX正对照和可选补充任务为false"),
        "request_model_field": enum("经页面/schema确认的实际字段；公开筛选视图枚举没有型号条件时为空", ["vehicleModel", "vehicleNumber", ""]),
        "request_filters_json": string("实际全部请求过滤项含默认状态/日期；无日期过滤也明写"),
        "energy_filter_field_raw": enum("实际库中纯电筛选字段；未筛为空", ["energyType", "fuelType", ""]),
        "energy_filter_value_raw": string("实际正常前端/动态字典值，纯电观察8；不由reportType推断"),
        "source_enumeration_complete": boolean("指定公开筛选视图分页/总行数/状态版本核验完成后true，不保证返回行都是真纯电或涵盖全部隐藏历史"),
        "page_size": integer("实际页长，不超过接口正常范围"),
        "reported_total_first": integer("首屏API查询范围总数；global模式是指定公开energyType8/fuelType8视图，不是本型号配置数；不支持则null", True),
        "reported_total_last": integer("末屏API查询范围总数；global模式同样为指定公开筛选视图；不支持则null", True),
        "reported_pages": integer("服务端报告页数；没有则null", True),
        "pages_fetched_successfully": integer("有效且不同页码的响应数"),
        "source_collection_raw_row_count": integer("所属实际查询/公开筛选视图快照全部原行数，必须在源manifest可核查"),
        "raw_records_seen": integer("此型号台账保留的原行发生数；direct含近似命中，global是精确匹配发生数；不拿视图总数冒充目标数"),
        "distinct_identifier_count": integer("不同UUID/uniqId等数量，只做剖面；不能要求等于报告总行数"),
        "distinct_full_row_hash_count": integer("全字段规范JSON行哈希不同值数；相同哈希的原发生次数仍保留"),
        "exact_model_records": integer("精确型号的原响应行发生次数，不冒充配置数/版本数"),
        "nonexact_model_records": integer("近似/错型号原响应行次数，原记录仍保留"),
        "pages_complete": boolean("实际页号、全部原行数与总数对账，无忽略页号/截断/未解释漂移；UUID重复本身不使其false"),
        "observed_history_filter_scope": string("只描述实际接口可见范围；不声称涵盖库中隐藏历史"),
        "status": enum("每型号每库必须有一个结果", ["complete_hits", "complete_zero_hits", "complete_nonexact_only", "error", "blocked", "truncated", "inconsistent", "not_attempted"]),
        "response_paths_json": string("按页顺序的原响应相对路径JSON数组"),
        "stop_reason": string("中止/错误/零命中边界，勿写全网无数据"),
    }
    definitions["record"] = {
        "record_key": string("发生项ID：库+快照+ID+全字段row_hash+页号+行序；不得把同UUID状态版本删掉"),
        "record_entity_key": string("库+稳定ID，只关联实体，不能当唯一历史记录键"),
        "record_version_key": string("库+稳定ID+全字段row_hash，允许一个UUID多个状态版本"),
        "full_row_sha256": {**common_sha, "description": "完整原列表对象规范JSON(sort_keys=True,ensure_ascii=False,separators=(',',':')) UTF8 SHA256；不删除null/日期/abandonTime字段"},
        "source_snapshot_id": string("该次快照ID"),
        "source_page_number": {**integer("原响应回显页号"), "minimum": 1},
        "source_row_index_zero_based": integer("原info.list中的0-based位置，完整相同行也各保留发生项"),
        "query_run_id": string("所属查询"),
        "library": enum("库", ["new", "old"]),
        "model_requested": string("精确请求型号"),
        "vehicle_model_raw": string("返回型号原值，新旧字段均逐库识别"),
        "model_exact_match": boolean("只按原始型号精确相等；不得按商品名/质量替代"),
        "record_id_raw": string("备案号原文，不等同检测报告编号"),
        "uuid_raw": string("UUID原值"),
        "enterprise_raw": string("申报企业原文，未认证历史法律身份"),
        "announcement_batch_raw": string("实际字段原值，不等同购置税目录批次"),
        "response_report_type_raw": string("列表reportType原值，不能当请求selector"),
        "response_energy_or_fuel_type_raw": string("列表若有energyType/fuelType则原文记录；不存在留空不填请求值"),
        "view_filter_record_type_consistency": enum("仅对实际返回分类/请求视图做一致性观察，不认证真实动力类别", ["consistent_observed", "inconsistent_observed", "unresolved"]),
        "pure_electric_identity_certified": boolean("不能由请求energyType8/fuelType8推所有返回行均是真纯电；默认false"),
        "configuration_key_raw": string("若实际官方字段/原件有配置键才填；否则空"),
        "curb_mass_raw": string("整备质量原值和单位；不与电池质量混淆"),
        "driving_range_raw": string("续驶里程原值"),
        "electric_energy_consumption_raw": string("消耗量原值，不是电池总能量"),
        "test_basis_standard_code_raw": string("代码原值，不无依据映射5"),
        "issue_date_raw": string("issueDate原值，字段语义未证不称官方出具日期"),
        "create_time_raw": string("createTime原值"),
        "submit_date_raw": string("submitDate原值"),
        "enable_date_raw": string("enableDate原值"),
        "activation_date_raw": string("activationDate原值"),
        "update_time_raw": string("updateTime原值"),
        "abandon_time_raw": string("abandonTime原值；同UUID两条不同撤销日期都保留"),
        "migration_note_raw": string("例如老数据切换新油耗系统，照录"),
        "post_cutoff_registration_or_migration_observed": boolean("2023-12-10后登记/提交/启用/迁移观察标记；不等于此前从未公开"),
        "public_time_raw": string("旧库publicTime原值，例2023-06，保持月精度；非首次公开/试验日"),
        "public_time_precision": enum("只描述原字段精度", ["month", "day", "timestamp", "unparsed", "not_present"]),
        "apply_id_raw": string("旧库列表applyId，queryDetail实际请求键，详情可能不回传，不能丢列表映射"),
        "work_condition_vos_raw_json": string("旧库workConditionVos全列表原文JSON；多工况不折成一个值"),
        "work_condition_type_raw": string("实际代码原文，如CATC；不机械等于CLTC-P"),
        "legacy_detail_evidence_ids_json": string("queryDetail原响应证据ID数组"),
        "full_label_reference_raw": string("实际标签路径/公开下载标识原值；不伪造"),
        "label_evidence_ids_json": string("逐记录关联标签证据ID JSON数组"),
        "raw_response_path": string("所属响应文件相对路径"),
        "raw_record_json_pointer": string("原JSON精确位置，如/info/list/0"),
        "standard_revision_officially_observed": boolean("逐条PDF、旧queryDetail字面标准原响应或正式代码字典有版本依据"),
        "work_condition_code_officially_observed": boolean("旧列表实际工况代码已观察，例CATC；这不认证其对应CLTC-P"),
        "explicit_test_cycle_officially_observed": boolean("逐条对应原件明确写具体试验工况名；仅CATC原代码不标此命名flag为true"),
        "issue_date_semantics_verified": boolean("须另有官方字段释义/对应原件，默认false"),
        "historical_public_availability_certified": boolean("独立证据证明冻结点前公开，不由issueDate推出"),
        "same_tax_configuration_identity_certified": boolean("正式跨目录配置桥已证；质量/续航相同不足"),
        "same_cycle_comparability_certified": boolean("工况、配置及适用历史版本全部核验前false"),
        "can_replace_frozen_scientific_input": boolean("默认false，批量采集阶段不能自动改科学输入"),
        "bridge_evidence_paths_json": string("上述证书flag的独立依据路径JSON数组；未证[]"),
        "scope_note": string("未提供/矛盾/不同配置/历史可得性未证边界"),
    }
    definitions["legacy_detail"] = {
        "detail_evidence_id": string("详情证据ID"),
        "record_key": string("所属旧库列表记录"),
        "request_id": string("下载日志ID"),
        "apply_id_requested": string("取自该条列表的applyId；不得由型号猜造"),
        "response_path": string("原queryDetail响应相对路径"),
        "response_sha256": common_sha,
        "model_raw": string("详情vehicleNumber原文"),
        "curb_mass_raw": string("详情vehicleQuality原文"),
        "range_raw": string("详情runingRange等原字段，保留映射位置"),
        "power_consumption_raw": string("详情powerConsumption原文"),
        "standard_revision_raw": string("实际testBasisStandard字面值，例GB/T 18386.1-2021"),
        "standard_evidence_quote": string("详情说明原文，不能用代码猜值"),
        "standard_json_pointer": string("例如/info/testBasisStandard或/info/energyConsumptionMarkDes"),
        "other_info_raw": string("详情otherInfo原文，新的中国工况不能机械CLTC-P"),
        "work_condition_code_raw": string("所关联列表workConditionVos原代码；详情缺时注明来自列表"),
        "work_condition_source_path": string("该代码原始响应路径"),
        "work_condition_json_pointer": string("实际原JSON位置，如/info/list/0/workConditionVos/0/workConditionType"),
        "cycle_named_explicit_raw": string("仅明确写CLTC-P/NEDC等时填；CATC单独保留代码，不填映射名"),
        "issue_date_semantics_verified": boolean("旧publicTime/列表备案号不推出检测/试验日期"),
        "historical_public_availability_certified": boolean("须另证；publicTime本身不机械当首次公开"),
        "same_tax_configuration_identity_certified": boolean("须正式桥；相同质量/续航不够"),
        "scope_note": string("JSON为公开详情原响应；不能假称已取得官方PDF/试验报告"),
    }
    definitions["version_conflict"] = {
        "conflict_id": string("稳定冲突ID"),
        "model_key": string("精确型号"),
        "left_record_key": string("候选关联左记录"),
        "right_record_key": string("候选关联右记录"),
        "candidate_pair_basis": string("例同型号+质量/续航一致，仅候选关联，不是配置认证"),
        "field": string("冲突字段，如electric_energy_consumption"),
        "left_raw_value": string("原值和单位"),
        "right_raw_value": string("原值和单位"),
        "left_source_path": string("左侧原响应/PDF路径"),
        "right_source_path": string("右侧原响应/PDF路径"),
        "left_source_locator": string("JSONpointer或PDF页码"),
        "right_source_locator": string("JSONpointer或PDF页码"),
        "resolution_status": enum("处置", ["unresolved_keep_separate", "different_configuration_proven", "official_correction_proven"]),
        "resolution_evidence_paths_json": string("未取得时[]；不能编造迁移/口径差异原因"),
        "same_configuration_identity_certified": boolean("同质量续航仍false"),
        "merge_allowed": boolean("保守默认false；需正式版本/配置对应和修订依据"),
        "scope_note": string("冲突不是可平均值或可任取其一的证据"),
    }
    definitions["label_evidence"] = {
        "label_evidence_id": string("全局证据ID，同字节去重但保留每记录映射"),
        "record_key": string("所属记录"),
        "label_type": enum("实际原件类别", ["full", "abbreviated", "legacy_public_document"]),
        "request_id": string("下载请求日志ID"),
        "download_url": string("页面正常公开下载URL，不包含账户凭证"),
        "pdf_path": string("原PDF相对路径，下载失败空"),
        "pdf_bytes": integer("原PDF字节数"),
        "pdf_sha256": nullable_sha,
        "pdf_valid": boolean("实际可解析PDF，非200验证码HTML"),
        "pdf_page_count": integer("实际页数"),
        "text_path": string("文本/OCR旁件相对路径，原PDF不修改"),
        "extraction_method": string("读取工具/版本/OCR；无文本须注明需人工"),
        "model_on_label_raw": string("标签所印型号原文"),
        "record_id_on_label_raw": string("标签所印备案号，未印则空"),
        "standard_revision_raw": string("原文标准编号及年版，逐PDF核对"),
        "standard_evidence_quote": string("逐条原文引句"),
        "standard_evidence_page": {**integer("1开始；没有则null", True), "minimum": 1},
        "cycle_explicit_raw": string("仅填原件显式工况；标准标题不转CLTC"),
        "cycle_evidence_quote": string("显式工况原文；没有为空"),
        "cycle_evidence_page": {**integer("1开始；没有则null", True), "minimum": 1},
        "evidence_level": enum("区分显式工况和仅标准", ["explicit_cycle_and_standard", "explicit_cycle_only", "standard_revision_only", "neither", "unreadable_or_failed"]),
        "issue_date_on_label_raw": string("标签所印日期；无则空，不挪API日期过来"),
        "battery_total_energy_on_label_raw": string("仅原件明确电池总能量，没写为空，禁止倒算"),
        "low_temperature_values_scope": enum("低温字段属性", ["industry_average", "model_specific_declaration", "model_specific_report", "not_present", "unresolved"]),
        "low_temperature_report_id_raw": string("只抄实际报告编号；备案号不代替"),
        "low_temperature_original_report_path": string("对应真实报告原件路径；无则空"),
        "scope_note": string("标签匹配、不一致、日期和低温字段边界"),
    }
    for kind, properties in definitions.items():
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                  "title": f"public_energy_{kind}_v1", "type": "object",
                  "additionalProperties": False, "required": list(properties), "properties": properties}
        if kind == "query_run":
            schema["allOf"] = [
                {"if": {"properties": {"status": {"enum": ["complete_hits", "complete_zero_hits", "complete_nonexact_only"]}}, "required": ["status"]},
                 "then": {"properties": {"pages_complete": {"const": True}}}},
                {"if": {"properties": {"status": {"enum": ["complete_hits", "complete_zero_hits", "complete_nonexact_only"]},
                                         "collection_mode": {"const": "global_enumeration"}}, "required": ["status", "collection_mode"]},
                 "then": {"properties": {"source_enumeration_complete": {"const": True}, "source_collection_manifest_path": {"minLength": 1}}}},
                {"if": {"properties": {"status": {"const": "complete_zero_hits"}}, "required": ["status"]},
                 "then": {"properties": {"exact_model_records": {"const": 0}, "nonexact_model_records": {"const": 0}}}},
            ]
        write_json(out / "schema" / f"{kind}.schema.json", schema)
        write_csv(out / "templates" / f"{kind}s_空表模板.csv", list(properties), [])
    write_json(out / "schema/delivery_manifest.schema.json", {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False,
        "required": ["schema_version", "frozen_model_list_sha256", "started_at_utc", "finished_at_utc", "network_request_count",
                     "core_model_count", "core_model_library_run_count", "counts", "completed", "stopped_reason", "files"],
        "properties": {
            "schema_version": {"const": "1.0"}, "frozen_model_list_sha256": common_sha,
            "started_at_utc": string("ISO8601 UTC"), "finished_at_utc": string("ISO8601 UTC"),
            "network_request_count": integer("全部实际请求，含失败与标签下载"),
            "core_model_count": {"const": 2208}, "core_model_library_run_count": integer("完成全部时4416，不含正对照"),
            "counts": {"type": "object", "description": "分库、逐状态计数；配置记录/PDF数与型号数分列；显式工况/仅标准/历史公开桥/同配置税桥分别统计"},
            "completed": boolean("4416个核心型号×库结果全有；分页中止则false"), "stopped_reason": string("实际中止边界"),
            "files": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                        "required": ["path", "bytes", "sha256"], "properties": {"path": string("包内相对路径"),
                        "bytes": integer("原字节数"), "sha256": common_sha}}}},
        "allOf": [{"if": {"properties": {"completed": {"const": True}}, "required": ["completed"]},
                   "then": {"properties": {"core_model_library_run_count": {"const": 4416}, "stopped_reason": {"const": ""}}}}]})
    write_json(out / "bulk_contract_summary.json", {
        "schema_version": "1.0", "network_requests_performed_by_this_handoff": 0,
        "science_files_written": 0, "core_model_count": 2208,
        "core_model_library_run_count_when_complete": 4416,
        "jx_in_core_2208": False,
        "input_cycle_source_sha256": sha(sources["cycle_backlog"]),
        "request_model_list_sha256": sha(out / "2208精确请求型号名单.csv"),
        "source_copy_sha256": sha(out / "inputs/2208型号_冻结来源旁表.csv"),
        "supplementary_non_core_model_count": len(supplementary),
        "priority_intersections_inside_core": {
            "configuration_36": sum(int(row["priority_configuration_36"]) for row in query_rows),
            "identity_285_models": sum(int(row["identity_285_model"]) for row in query_rows),
            "low_temperature_19_models": sum(int(row["low_temperature_19_model"]) for row in query_rows)},
        "certification_flags_default_false": True,
        "new_library_schema_evidence": "User-uploaded response plus current JX pilot confirm /info/list, totalSize/pages, vehicleModel; actual currentPage2 probe confirms pagination.",
        "old_library_schema_evidence": "Current pilot JX queryList HTTP200 business result1 /info/list, vehicleNumber; queryDetail applyId returns literal standard and curb mass. Copied with fixed SHA.",
        "business_success_codes_observed": {"new": 200, "old": 1},
        "pagination_field_verified": "currentPage",
        "pagination_rejected_recipe": "pageNum=2 was ignored and returned info.currentPage=1 with repeated first page; cannot serve as enumeration proof.",
        "new_bev_filter": {"field": "energyType", "value": "8"},
        "old_bev_filter": {"field": "fuelType", "value": "8", "basis": "Official FC_FUEL_TYPE dictionary, exact dictName 纯电动"},
        "old_work_condition_observed": "CATC (raw code only; not an automatic CLTC-P mapping)",
        "jx_cross_version_consumption_conflict": {"old_kwh_per_100km": "22.8", "new_kwh_per_100km": "19.2", "merge_allowed": False},
        "complete_universe_cache_reuse": "If independently verified complete snapshots of the specified public energyType8/fuelType8 filter views are delivered, match fixed models locally rather than repeat 4416 live queries; download labels/details by stable record references.",
        "scope_boundary": "Completeness concerns the public filter view, not all hidden history or certified BEV identity of every returned row. Keep response classification inconsistencies as separate evidence without dropping rows.",
        "universe_collection_completion_not_assumed": True})
    output_hashes = [{"file": str(path.relative_to(out)), "bytes": path.stat().st_size, "sha256": sha(path)}
                     for path in sorted(out.rglob("*")) if path.is_file() and path.name != "文件_SHA256.csv"
                     and "__pycache__" not in path.parts]
    write_csv(out / "文件_SHA256.csv", ["file", "bytes", "sha256"], output_hashes)
    print(json.dumps({"result": "PASS", "core_models": len(models), "model_list_sha256": sha(out / "2208精确请求型号名单.csv"),
                      "output_manifest_entries": len(output_hashes), "network_requests": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
