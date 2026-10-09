#!/usr/bin/env python3
"""Read-only independent PDF archive audit using PyMuPDF and pypdf.

Requires both collection stages to be finished. Does not request network and
does not adopt the collector's extracted text or standard conclusions.
"""
import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import fitz
from pypdf import PdfReader


STANDARD_PATTERN = re.compile(r"GB\s*[/／]\s*T\s*18386(?:\s*[.．]\s*1)?\s*[—－–‐‑−-]\s*(?:19|20)\d{2}", re.I)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def full_row_sha(row):
    # The source-reference producer declares Python's default JSON separators.
    # Verify that recipe, separate from the compact recipe in the raw-row audit.
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def canonical_standard(literal):
    text = compact(literal).upper()
    for char in "—－–‐‑−":
        text = text.replace(char, "-")
    return text


def standards(text):
    return [{"literal": m.group(0), "canonical_for_comparison": canonical_standard(m.group(0)),
             "context": text[max(0, m.start() - 70): m.end() + 90]}
            for m in STANDARD_PATTERN.finditer(text)]


def pointer(document, value):
    current = document
    for part in value.lstrip("/").split("/"):
        decoded = part.replace("~1", "/").replace("~0", "~")
        current = current[int(decoded)] if isinstance(current, list) else current[decoded]
    return current


def read_checkpoint(path, kind):
    raw = path.read_bytes()
    data = json.loads(raw)
    if not data.get("finished_utc"):
        raise SystemExit(f"{kind} collection is not finished; no PDF review is published.")
    if kind == "exact" and (data.get("accepted_pdfs") != 100 or data.get("pause_kind") != "planned_review_stage_boundary"):
        raise SystemExit("Exact stage does not have the required first 100 PDFs.")
    if kind == "candidate" and (not data.get("completed") or data.get("accepted_pdfs") != 2):
        raise SystemExit("BMW candidate stage is not complete with 2 PDFs.")
    return raw, data


def review_stage(root, kind, output):
    checkpoint_path = root / "label_checkpoint.json"
    checkpoint_bytes, checkpoint = read_checkpoint(checkpoint_path, kind)
    queue = [json.loads(line) for line in (root / "label_download_queue.jsonl").read_text().splitlines() if line]
    assert sha(root / "label_download_queue.jsonl") == checkpoint["source_queue_sha256"]
    queue_by_job = {row["label_job_id"]: row for row in queue}
    accepted = []
    for path in sorted((root / "receipts").glob("*_receipt.json")):
        receipt = json.loads(path.read_text())
        if receipt.get("accepted"):
            accepted.append((path, receipt))
    assert len(accepted) == checkpoint["accepted_pdfs"]
    assert len({r["label_job_id"] for _, r in accepted}) == len(accepted)
    items = []
    modelrows = []
    for receipt_path, receipt in accepted:
        job = queue_by_job[receipt["label_job_id"]]
        path = root / receipt["response_file"]
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        doc = fitz.open(path)
        fitz_text = "\n".join(page.get_text("text") for page in doc)
        fitz_pages = len(doc)
        reader = PdfReader(path)
        pypdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        pypdf_pages = len(reader.pages)
        fitz_stds, pypdf_stds = standards(fitz_text), standards(pypdf_text)
        fitz_canon = sorted({s["canonical_for_comparison"] for s in fitz_stds})
        pypdf_canon = sorted({s["canonical_for_comparison"] for s in pypdf_stds})
        text_fitz_path = output / "texts" / f"{kind}_{receipt['label_job_id']}_PyMuPDF.txt"
        text_pypdf_path = output / "texts" / f"{kind}_{receipt['label_job_id']}_pypdf.txt"
        text_fitz_path.write_text(fitz_text, encoding="utf-8")
        text_pypdf_path.write_text(pypdf_text, encoding="utf-8")
        url_params = parse_qs(urlsplit(receipt["requested_url"]).query)
        checks = {
            "pdf_header": raw.startswith(b"%PDF-"), "receipt_http_200": receipt["http_status"] == 200,
            "receipt_tls_verified": receipt["tls_verified"] is True,
            "pdf_sha_matches_receipt": digest == receipt["sha256"],
            "pdf_bytes_matches_receipt": len(raw) == receipt["bytes"],
            "receipt_fullLabel_matches_queue": receipt["fullLabel"] == job["fullLabel"],
            "download_m_matches_fullLabel": url_params.get("m") == [job["fullLabel"]],
            "download_p_equals_1": url_params.get("p") == ["1"],
            "page_count_both_engines_equal": fitz_pages == pypdf_pages == receipt["pdf_pages"],
            "both_engines_have_text": bool(fitz_text.strip()) and bool(pypdf_text.strip()),
            "standard_canonical_sets_equal": fitz_canon == pypdf_canon,
            "literal_standard_found_both": bool(fitz_stds) and bool(pypdf_stds),
        }
        refs = []
        for ref in job["record_refs"]:
            source_path = (root / ref["source_file"]).resolve()
            source = json.loads(source_path.read_text())
            row = pointer(source, ref["json_pointer"])
            source_checks = {
                "source_page_sha256_matches_ref": sha(source_path) == ref["source_page_sha256"],
                "full_row_sha256_matches_ref": full_row_sha(row) == ref["full_row_sha256"],
                "source_fullLabel_matches_job": row["fullLabel"] == job["fullLabel"],
                "source_uuid_matches_ref": row["uuid"] == ref["uuid"],
                "source_model_matches_raw_ref": row["vehicleModel"] == ref["vehicleModel_raw"],
                "source_recordNumber_matches_ref": row["recordNumber"] == ref["recordNumber"],
            }
            model = ref["model_key"]
            model_fitz = compact(model) in compact(fitz_text)
            model_pypdf = compact(model) in compact(pypdf_text)
            number_fitz = compact(ref["recordNumber"]) in compact(fitz_text)
            number_pypdf = compact(ref["recordNumber"]) in compact(pypdf_text)
            source_checks["model_visible_both_text_engines"] = model_fitz and model_pypdf
            record = {"model_key": model, "vehicleModel_raw": ref["vehicleModel_raw"], "uuid": ref["uuid"],
                 "recordNumber_registry": ref["recordNumber"], "source_file": ref["source_file"],
                 "source_page_sha256": ref["source_page_sha256"], "json_pointer": ref["json_pointer"],
                 "testBasisStandard_raw": row["testBasisStandard"],
                 "source_checks": source_checks, "model_visible_PyMuPDF": model_fitz, "model_visible_pypdf": model_pypdf,
                 "recordNumber_visible_PyMuPDF": number_fitz, "recordNumber_visible_pypdf": number_pypdf,
                 "recordNumber_certification_scope": "PDF exact text present" if number_fitz and number_pypdf else "Registry-to-download linkage verified; recordNumber not visible in both PDF text engines",
                 "all_required_source_checks_pass": all(source_checks.values())}
            refs.append(record)
            modelrows.append({"scope": kind, "model_key": model, "vehicleModel_raw": ref["vehicleModel_raw"],
                "uuid": ref["uuid"], "recordNumber_registry": ref["recordNumber"],
                "source_file": ref["source_file"], "json_pointer": ref["json_pointer"], "fullLabel": job["fullLabel"],
                "pdf_file": str(path.relative_to(root)), "pdf_sha256": digest, "pdf_bytes": len(raw),
                "pages_PyMuPDF": fitz_pages, "pages_pypdf": pypdf_pages,
                "testBasisStandard_raw": row["testBasisStandard"],
                "standard_literals_PyMuPDF_json": json.dumps([s["literal"] for s in fitz_stds], ensure_ascii=False),
                "standard_literals_pypdf_json": json.dumps([s["literal"] for s in pypdf_stds], ensure_ascii=False),
                "standard_canonical_set_json": json.dumps(fitz_canon, ensure_ascii=False),
                "model_visible_both": int(model_fitz and model_pypdf),
                "recordNumber_visible_PyMuPDF": int(number_fitz), "recordNumber_visible_pypdf": int(number_pypdf),
                "source_pointer_fullLabel_link_verified": int(all(source_checks.values())),
                "same_tax_configuration_certified": 0, "historical_public_availability_certified": 0,
                "frozen_cycle_gap_closed": 0})
        checks["all_source_pointers_verified"] = all(r["all_required_source_checks_pass"] for r in refs)
        items.append({"label_job_id": receipt["label_job_id"], "scope": kind, "fullLabel": job["fullLabel"],
             "pdf_file": str(path), "receipt_file": str(receipt_path), "receipt_sha256": sha(receipt_path),
             "pdf_sha256": digest, "pdf_bytes": len(raw), "page_count": fitz_pages,
             "checks": checks, "all_required_checks_pass": all(checks.values()),
             "standards_PyMuPDF": fitz_stds, "standards_pypdf": pypdf_stds,
             "canonical_standards": fitz_canon, "record_refs": refs,
             "text_PyMuPDF_file": str(text_fitz_path.relative_to(output)), "text_PyMuPDF_sha256": sha(text_fitz_path),
             "text_pypdf_file": str(text_pypdf_path.relative_to(output)), "text_pypdf_sha256": sha(text_pypdf_path)})
        doc.close()
    assert checkpoint_bytes == checkpoint_path.read_bytes(), f"{kind} checkpoint changed during review"
    return {"scope": kind, "checkpoint_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
            "checkpoint_finished_utc": checkpoint["finished_utc"], "checkpoint_completed": checkpoint["completed"],
            "checkpoint_pause_kind": checkpoint.get("pause_kind"),
            "pdf_count": len(items), "pdf_bytes": sum(i["pdf_bytes"] for i in items),
            "model_count": len({r["model_key"] for r in modelrows}),
            "all_required_checks_pass": all(i["all_required_checks_pass"] for i in items),
            "standard_sets_counts": dict(Counter(";".join(i["canonical_standards"]) for i in items)),
            "recordNumber_visible_both_count": sum(bool(r["recordNumber_visible_PyMuPDF"] and r["recordNumber_visible_pypdf"]) for r in modelrows),
            "literal_by_raw_code": {code: dict(Counter(";".join(json.loads(r["standard_canonical_set_json"]))
                      for r in modelrows if r["testBasisStandard_raw"] == code))
                      for code in sorted({r["testBasisStandard_raw"] for r in modelrows})},
            "items": items}, modelrows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", default="/workspace/purchase_tax_audit/round11/label_archive")
    p.add_argument("--output", default=str(Path(__file__).resolve().parent))
    args = p.parse_args()
    archive, output = Path(args.archive), Path(args.output)
    # Do not inspect or extract PDFs until both collection stages are finished.
    read_checkpoint(archive / "label_checkpoint.json", "exact")
    read_checkpoint(archive / "whitespace_candidates/label_checkpoint.json", "candidate")
    (output / "texts").mkdir(parents=True, exist_ok=True)
    (output / "texts/README.md").write_text("# 独立双引擎PDF全文\n\n每份标签单独保存PyMuPDF和pypdf全文，未使用采集器的既有提取文本。\n", encoding="utf-8")
    exact, exact_rows = review_stage(archive, "exact", output)
    candidate, candidate_rows = review_stage(archive / "whitespace_candidates", "candidate", output)
    # Render two actual documents selected by extracted standard, not API code.
    rendered = []
    for target in ["GB/T18386-2017", "GB/T18386.1-2021"]:
        item = next((item for item in exact["items"] if target in item["canonical_standards"]), None)
        if item:
            name = "代表_" + target.replace("/", "_") + ".png"
            with fitz.open(item["pdf_file"]) as doc:
                doc[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(output / name)
            rendered.append({"file": name, "sha256": sha(output / name), "pdf_sha256": item["pdf_sha256"],
               "model_keys": [r["model_key"] for r in item["record_refs"]], "standard": target})
    result = {"status": "PASS" if exact["all_required_checks_pass"] and candidate["all_required_checks_pass"] else "REVIEW_REQUIRED",
              "no_network_requests": True, "text_engines": ["PyMuPDF", "pypdf"],
              "source_reference_row_hash_recipe": "UTF-8 JSON sort_keys=True, ensure_ascii=False, Python default separators",
              "collector_extraction_not_used": True, "exact": exact, "whitespace_candidate": candidate,
              "rendered_representatives": rendered, "frozen_cycle_gap_closed": 0,
              "scientific_parameters_modified": False,
              "scope": "Standards are only the literal text found in the acquired PDFs; no global dictionary, cycle, tax-configuration, historic-availability or 2208-gap certification."}
    (output / "review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = exact_rows + candidate_rows
    with (output / "102份标签_双引擎标准与来源独立核验.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    readme = f"""# 标签首100份及2份BMW空白候选：独立PDF复核

本复核等待两条采集阶段结束后，只读标签PDF、GET收据和原始列表记录，使用**PyMuPDF与pypdf两条独立文本提取路径**。没有网络请求，没有使用采集器已提取的文本或标准结论，没有修改科学CSV。

[逐文件证据JSON](review.json) · [102份标签逐行核验](102份标签_双引擎标准与来源独立核验.csv) · [复现脚本](review_label_batch.py)

- 原样精确命中队列取得**{exact['pdf_count']}份**、{exact['model_count']}型号，处于正常批次暂停，队列全量未完成。PDF原件共{exact['pdf_bytes']:,} B。
- 去首尾空白的BMW候选单列**{candidate['pdf_count']}份**，没有并入原样精确命中。
- 两条提取路径的标准字面证据一致；精确标签标准分布：`{json.dumps(exact['standard_sets_counts'], ensure_ascii=False)}`；BMW候选：`{json.dumps(candidate['standard_sets_counts'], ensure_ascii=False)}`。
- API代码与已取标签字面对账：`{json.dumps(exact['literal_by_raw_code'], ensure_ascii=False)}`。只描述本次已取得文件，不把代码单独映射为全库标准或NEDC/CLTC。
- SHA/字节数、HTTP200、PDF可解析、页数、型号可见及列表source pointer→fullLabel→下载m参数一致性，整体结果**{result['status']}**。备案号只在实际文本出现时记“可见”；精确标签两引擎均可见备案号{exact['recordNumber_visible_both_count']}份，其余保留注册记录至下载关联，不声称PDF展示备案号。
- [2017代表标签](代表_GB_T18386-2017.png)和[2021代表标签](代表_GB_T18386.1-2021.png)供视觉复核。

**标签标准原文不等于同税目录配置身份或冻结日前公开可得，也不直接证明CATC/NEDC字典、同工况可比或逐车资格。冻结2208缺口关闭0；JX电池总能量缺口没有变化。**
"""
    (output / "README.md").write_text(readme, encoding="utf-8")
    with (output / "文件_SHA256.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["file", "bytes", "sha256"])
        for path in sorted(output.rglob("*")):
            if path.is_file() and path.name != "文件_SHA256.csv" and "__pycache__" not in path.parts:
                writer.writerow([path.relative_to(output).as_posix(), path.stat().st_size, sha(path)])
    print(json.dumps({"status": result["status"], "exact_pdfs": exact["pdf_count"], "exact_models": exact["model_count"],
          "candidate_pdfs": candidate["pdf_count"], "standard_counts": exact["standard_sets_counts"],
          "raw_code_literal": exact["literal_by_raw_code"], "recordNumbers_visible_both": exact["recordNumber_visible_both_count"],
          "representatives": rendered}, ensure_ascii=False))


if __name__ == "__main__":
    main()
