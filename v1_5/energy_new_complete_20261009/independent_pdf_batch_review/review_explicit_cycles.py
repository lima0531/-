#!/usr/bin/env python3
"""Audit literal cycle clauses in the 100 exact and 2 candidate original PDFs.

No standard-to-cycle dictionary is used. All extraction is from PDF originals.
Comparison-only mentions cannot become positive cycle labels. Core CSV untouched.
"""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import fitz
from pypdf import PdfReader


MENTION = re.compile(r"NEDC|CLTC(?:-P)?|WLTC|CATC|(?:新的)?中国工况", re.I)
MAIN_POSITIVE = re.compile(r"(?P<verb>基于|按照|按|采用)(?P<literal>新的中国工况|中国工况|NEDC工况|CLTC(?:-P)?工况|WLTC工况|CATC工况)", re.I)
SUBJECT = re.compile(r"本车型|本车|能耗|里程|电耗|消耗量|试验|测试|数据")
NEGATION = re.compile(r"并非|不是|未|不|非|无|没有")
COMPARISON = re.compile(r"^与|^和|相比|比较|差异|不同|区别")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_page(text, page):
    evidence = []
    sections = []
    other = re.search(r"其他信息\s*[:：]", text)
    boundary = re.search(r"本标识所采用", text)
    if other and boundary and boundary.start() > other.end():
        sections.append((other.end(), boundary.start(), text[other.end():boundary.start()].strip()))
    for match in MENTION.finditer(text):
        section = next((s for s in sections if s[0] <= match.start() < s[1]), None)
        if section:
            original = section[2]
        else:
            left = max(text.rfind("。", 0, match.start()), text.rfind("；", 0, match.start())) + 1
            rights = [v for v in (text.find("。", match.end()), text.find("；", match.end())) if v >= 0]
            right = min(rights) + 1 if rights else len(text)
            original = text[left:right].strip()
        # Context preserves the complete original paragraph. Matching removes
        # layout whitespace only; it never maps a standard code to a cycle.
        flat = re.sub(r"\s+", "", original)
        token = re.sub(r"\s+", "", match.group(0)).upper()
        clauses = re.split(r"[,，;；。.!！?？]", flat)
        containing = [c for c in clauses if token in c.upper()]
        roles = []
        positives = []
        for clause in containing:
            for positive in MAIN_POSITIVE.finditer(clause):
                literal = positive.group("literal")
                normalized = literal.upper()
                if normalized.endswith("工况") and normalized not in ("中国工况", "新的中国工况"):
                    normalized = normalized[:-2]
                if token != normalized and token != normalized.removeprefix("新的"):
                    continue
                prefix = clause[:positive.start()]
                if NEGATION.search(prefix[-8:]):
                    roles.append("negated_or_excluded")
                elif COMPARISON.search(prefix) or not SUBJECT.search(prefix):
                    roles.append("unresolved_clause_not_clear_main_statement")
                else:
                    role = "generic_main_positive_no_named_cycle" if "中国工况" in normalized else "named_cycle_main_positive"
                    roles.append(role)
                    positives.append(normalized)
            if not positives and COMPARISON.search(clause):
                roles.append("comparison_only")
        role = ("named_cycle_main_positive" if "named_cycle_main_positive" in roles else
                "generic_main_positive_no_named_cycle" if "generic_main_positive_no_named_cycle" in roles else
                "negated_or_excluded" if "negated_or_excluded" in roles else
                "comparison_only" if "comparison_only" in roles else "unresolved_mention")
        evidence.append({"page_1_based": page, "keyword_literal": match.group(0), "mention_role": role,
            "positive_literals": sorted(set(positives)), "evidence_complete_paragraph_raw": original,
            "layout_whitespace_removed_for_clause_matching": flat})
    return evidence


def analyse_pages(pages):
    evidence = [record for page_no, page_text in enumerate(pages, 1) for record in inspect_page(page_text, page_no)]
    named = sorted({literal for record in evidence if record["mention_role"] == "named_cycle_main_positive"
                    for literal in record["positive_literals"]})
    generic = sorted({literal for record in evidence if record["mention_role"] == "generic_main_positive_no_named_cycle"
                      for literal in record["positive_literals"]})
    comparison = sorted({record["keyword_literal"].upper() for record in evidence if record["mention_role"] == "comparison_only"})
    return {"evidence": evidence, "named_positive_literals": named,
            "generic_positive_literals_no_named_mapping": generic, "comparison_only_literals": comparison}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", default=str(Path(__file__).resolve().parent))
    args = p.parse_args()
    output = Path(args.output)
    base_path = output / "review.json"
    base = json.loads(base_path.read_text())
    main_csv = output / "102份标签_双引擎标准与来源独立核验.csv"
    main_csv_sha_before = sha(main_csv)
    results = []
    rows = []
    for scope_key in ("exact", "whitespace_candidate"):
        for item in base[scope_key]["items"]:
            path = Path(item["pdf_file"])
            assert sha(path) == item["pdf_sha256"]
            with fitz.open(path) as document:
                fitz_result = analyse_pages([page.get_text("text") for page in document])
            reader = PdfReader(path)
            pypdf_result = analyse_pages([page.extract_text() or "" for page in reader.pages])
            agreed = all(fitz_result[k] == pypdf_result[k] for k in (
                "named_positive_literals", "generic_positive_literals_no_named_mapping", "comparison_only_literals"))
            result = {"scope": scope_key, "label_job_id": item["label_job_id"], "pdf_sha256": item["pdf_sha256"],
                "model_keys": [ref["model_key"] for ref in item["record_refs"]], "standard_literals": item["canonical_standards"],
                "PyMuPDF": fitz_result, "pypdf": pypdf_result, "classification_both_engines_agree": agreed,
                "same_tax_configuration_identity_certified": False, "historical_public_availability_certified": False,
                "can_replace_frozen_cycle_input": False}
            results.append(result)
            for ref in item["record_refs"]:
                rows.append({"scope": scope_key, "model_key": ref["model_key"], "uuid": ref["uuid"],
                    "recordNumber_registry": ref["recordNumber_registry"], "pdf_sha256": item["pdf_sha256"],
                    "standard_literal_set_json": json.dumps(item["canonical_standards"], ensure_ascii=False),
                    "explicit_cycle_literal_positive": ";".join(fitz_result["named_positive_literals"]),
                    "generic_main_positive_without_named_cycle": ";".join(fitz_result["generic_positive_literals_no_named_mapping"]),
                    "comparison_only_mentioned": ";".join(fitz_result["comparison_only_literals"]),
                    "literal_source_pages": ";".join(map(str, sorted({e["page_1_based"] for e in fitz_result["evidence"]}))),
                    "all_cycle_paragraphs_PyMuPDF_json": json.dumps(fitz_result["evidence"], ensure_ascii=False),
                    "all_cycle_paragraphs_pypdf_json": json.dumps(pypdf_result["evidence"], ensure_ascii=False),
                    "classification_both_engines_agree": int(agreed),
                    "same_tax_configuration_identity_certified": 0, "historical_public_availability_certified": 0,
                    "can_replace_frozen_cycle_input": 0, "frozen_2208_gap_closed": 0})
    assert main_csv_sha_before == sha(main_csv), "Main PDF review CSV was modified"
    summaries = {}
    for scope in ("exact", "whitespace_candidate"):
        selected = [r for r in results if r["scope"] == scope]
        named_counts = Counter(literal for r in selected for literal in r["PyMuPDF"]["named_positive_literals"])
        cross = Counter((";".join(r["standard_literals"]), ";".join(r["PyMuPDF"]["named_positive_literals"]) or
                    ";".join(r["PyMuPDF"]["generic_positive_literals_no_named_mapping"]) or "no_explicit_cycle") for r in selected)
        summaries[scope] = {
            "pdfs": len(selected), "named_cycle_positive_pdfs": sum(bool(r["PyMuPDF"]["named_positive_literals"]) for r in selected),
            "named_cycle_positive_models": len({m for r in selected if r["PyMuPDF"]["named_positive_literals"] for m in r["model_keys"]}),
            "named_cycle_positive_pdf_counts": {code: named_counts[code] for code in ("NEDC", "CLTC", "WLTC", "CATC")},
            "generic_china_cycle_main_positive_without_named_mapping_pdfs": sum(bool(r["PyMuPDF"]["generic_positive_literals_no_named_mapping"]) for r in selected),
            "no_explicit_main_cycle_pdfs": sum(not r["PyMuPDF"]["named_positive_literals"] and not r["PyMuPDF"]["generic_positive_literals_no_named_mapping"] for r in selected),
            "comparison_only_named_NEDC_pdfs": sum("NEDC" in r["PyMuPDF"]["comparison_only_literals"] for r in selected),
            "classification_both_engines_agree": all(r["classification_both_engines_agree"] for r in selected),
            "standard_cross_literal_cycle": [{"standard": std, "cycle_literal_or_status": cyc, "pdfs": count}
                                             for (std, cyc), count in sorted(cross.items())]}
    review = {"status": "PASS" if all(r["classification_both_engines_agree"] for r in results) else "REVIEW_REQUIRED",
        "no_network_requests": True, "no_standard_or_code_to_cycle_mapping": True,
        "rule": "A clear main clause with subject plus 基于/按照/按/采用 and named X工况; preceding negation and comparison clauses excluded. Generic 新的中国工况 is recorded separately with no CLTC/CATC/NEDC mapping.",
        "main_pdf_csv_unchanged_sha256": main_csv_sha_before,
        "summaries": summaries, "results": results, "frozen_2208_gap_closed": 0,
        "root_visual_observations_reported": [
            {"model": "LZ7008SLAEV", "render": "代表_GB_T18386-2017.png", "observation": "本车型能耗、里程基于NEDC工况，与中国工况略有差异。 Clear NEDC main clause; China cycle only comparison."},
            {"model": "SC6483ABBBEV", "render": "代表_GB_T18386.1-2021.png", "observation": "GB/T18386.1—2021 printed; no explicit named-cycle statement."}],
        "scope": "Only literal evidence in acquired PDFs. Same tax configuration, freeze-time public availability, eligibility and scientific cycle replacement remain uncertified."}
    (output / "explicit_cycle_literal_review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "102份标签_工况主句与仅比较提及_独立旁表.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    base["explicit_cycle_literal_followup"] = {"status": review["status"], "summary": summaries,
        "evidence": "explicit_cycle_literal_review.json", "main_pdf_csv_unchanged_sha256": main_csv_sha_before,
        "cycle_literal_csv": "102份标签_工况主句与仅比较提及_独立旁表.csv", "frozen_2208_gap_closed": 0}
    base_path.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    marker = "\n<!-- EXPLICIT_CYCLE_LITERAL_FOLLOWUP -->\n"
    readme = output / "README.md"
    prior = readme.read_text().split(marker)[0]
    exact = summaries["exact"]
    readme.write_text(prior + marker + f"""\n## 追加：工况主句与比较句分别核验

对100＋2份原PDF按页重新双引擎读取，保存完整“其他信息”原段、每个工况词的原文和页码。仅将明确主句“本车型能耗、里程基于X工况”等记为positive；否定排除，比较句中的X不认定为本车工况。**没有按标准年份或API代码推定工况。** 原有102份标准核验CSV的SHA保持不变。

[逐PDF工况证据](explicit_cycle_literal_review.json) · [逐记录工况旁表](102份标签_工况主句与仅比较提及_独立旁表.csv) · [提取与判断脚本](review_explicit_cycles.py)

精确100份中，主句明确**NEDC {exact['named_cycle_positive_pdf_counts']['NEDC']}份、CLTC {exact['named_cycle_positive_pdf_counts']['CLTC']}份**（合计{exact['named_cycle_positive_pdfs']}份／{exact['named_cycle_positive_models']}型号）；另**{exact['generic_china_cycle_main_positive_without_named_mapping_pdfs']}份只泛称“新的中国工况”**，不给CLTC/CATC/NEDC代码。这7份中的NEDC仅在“与NEDC工况略有差异”比较句，不能算NEDC主句。剩余{exact['no_explicit_main_cycle_pdfs']}份没有工况主句。BMW候选2份也无明示工况。两引擎判断全部一致。

2017标准的49份里仅40份明示NEDC，9份未明示；2021标准的51份里10份明示CLTC、7份泛称新的中国工况、34份未明示。这正是标准版本不能自动替代工况原文的实际证据。

root已视觉查看两份代表图：LZ7008SLAEV确实写“本车型能耗、里程基于NEDC工况，与中国工况略有差异。”；SC6483ABBBEV只印2021标准，没有明确工况字样。视觉观察与双引擎原文相符。

**本旁表仍不认证同税目录配置、冻结日前公开可得或逐车资格；所有certification/replacement字段为0，冻结2208缺口关闭0。**
""", encoding="utf-8")
    with (output / "文件_SHA256.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["file", "bytes", "sha256"])
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "文件_SHA256.csv" and "__pycache__" not in path.parts:
                writer.writerow([path.relative_to(output).as_posix(), path.stat().st_size, sha(path)])
    print(json.dumps({"status": review["status"], "summaries": summaries}, ensure_ascii=False))


if __name__ == "__main__":
    main()
