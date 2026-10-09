#!/usr/bin/env python3
"""Create a read-only cycle-evidence ledger after whole-source extraction."""
import argparse, collections, csv, hashlib, json, re, unicodedata, zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET
from extract_full_sources import ROOT, REQ, NS, KEY, readcsv, dump, sha

def norm(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',value)).upper()
CYCLE=re.compile(r'CLTC|NEDC|WLTC|WLTP|CATC|UDDS|FTP|工况|等速|缩短法|常规法|测量法',re.I)
STD=re.compile(r'\b(?:GB(?:\s*/\s*T)?|QC\s*/\s*T|ISO|SAE|UNECE|ECE)\s*\d{3,}(?:[.－—-]\d+)*\b',re.I)

def word_inventory(p):
    rows=[];locations={};tables=0;physical_rows=0;media=[];text_parts=[]
    with zipfile.ZipFile(p) as z:
        media=[n for n in z.namelist() if n.startswith('word/media/')]
        for name in sorted(z.namelist()):
            if not re.match(r'word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml$',name):continue
            text_parts.append(name);root=ET.fromstring(z.read(name))
            table_paras=set()
            for ti,tbl in enumerate(root.findall('.//w:tbl',NS)):
                tables+=1
                for ri,tr in enumerate(tbl.findall('w:tr',NS)):
                    physical_rows+=1
                    table_paras.update(tr.findall('.//w:p',NS))
                    cells=[''.join(t.text or '' for t in tc.findall('.//w:t',NS)) for tc in tr.findall('w:tc',NS)]
                    scope=' | '.join(cells);loc=f'{name}:table_{ti}:row_{ri}'
                    locations[loc]=(cells,scope)
                    if ri==0 or ('车辆型号' in scope and ('续驶' in scope or '能量' in scope)):
                        rows.append({'location':loc,'scope_type':'physical_table_first_row_or_explicit_header','text':scope,'technical_keyword_matches':'|'.join(m.group() for m in KEY.finditer(scope))})
            for pi,para in enumerate(root.findall('.//w:p',NS),1):
                if para in table_paras:continue
                text=''.join(t.text or '' for t in para.findall('.//w:t',NS))
                if text.strip():rows.append({'location':f'{name}:outside_table_paragraph_{pi}','scope_type':'body_note_or_auxiliary_story','text':text,'technical_keyword_matches':'|'.join(m.group() for m in KEY.finditer(text))})
    return locations,rows,{'tables':tables,'physical_rows':physical_rows,'media_files':media,'text_parts':text_parts}

def main():
    global REQ
    parser=argparse.ArgumentParser();parser.add_argument('--requirements',type=Path,default=REQ);args=parser.parse_args();REQ=args.requirements.resolve()
    targets=readcsv(REQ/'2208数值可用型号_公告前试验工况待核清单.csv')
    fields=readcsv(REQ/'2208型号_工况清单字段来源长表.csv')
    ranges=[r for r in fields if r['field']=='range']
    assert len(ranges)==2208 and len({r['model_key'] for r in ranges})==2208
    backlog={norm(r['model_key']):r['model_key'] for r in targets}
    sources=readcsv(ROOT/'71份工况来源原件_同字节定位.csv')
    proofs={p['source_file']:p for p in json.loads((ROOT/'full_source_extraction_proof.json').read_text())}
    hits=readcsv(ROOT/'整篇正文_工况与标准检索命中.csv')
    bysource=collections.defaultdict(list)
    for r in ranges:bysource[r['source_file']].append(r)
    model_rows=[];source_rows=[];header_rows=[];classification=[];pair_checks=[]
    method_counts=collections.Counter();detected_counts=collections.Counter();image_count=0;page_count=0
    for src in sources:
        logical=src['source_file'];stem=Path(logical).stem;proof=proofs[logical]
        units=json.loads((ROOT/proof['units_file']).read_text());local_hits=[h for h in hits if h['source_file']==logical]
        ispdf='pages' in proof
        if ispdf:
            fmt='PDF';detected_counts[fmt]+=1;page_count+=proof['pages'];image_count+=len(proof['pages_with_images'])
            assert not proof['blank_text_pages'] and proof['pages']==proof['second_reader_pages']
            location_data={};inventory=[];wordmeta={'tables':'','physical_rows':'','media_files':[],'text_parts':[]}
        else:
            fmt='CFB_WORD_WPS' if 'cfb' in proof else 'ZIP_DOCX';detected_counts[fmt]+=1
            p=ROOT/'converted'/f'{stem}.docx' if fmt=='CFB_WORD_WPS' else Path(src['physical_path'])
            location_data,inventory,wordmeta=word_inventory(p);image_count+=len(wordmeta['media_files'])
            for h in inventory:header_rows.append({'source_file':logical,'source_sha256':src['source_sha256'],**h})
            if fmt=='CFB_WORD_WPS':
                native=collections.Counter(h['matched_token'].upper() for h in local_hits if h['method']=='bounded CFB main story')
                derived=collections.Counter(h['matched_token'].upper() for h in local_hits if h['method']=='LibreOffice DOCX all text stories')
                assert native==derived,(logical,native,derived)
                pair_checks.append({'source_file':logical,'native_keyword_multiset':json.dumps(native,sort_keys=True),'derived_keyword_multiset':json.dumps(derived,sort_keys=True),'multiset_equal':'1','native_auxiliary_story_hits':sum(h['method']=='bounded CFB auxiliary story' for h in local_hits)})
                assert proof['native_story_counts_utf16']['footnotes']==0 and proof['native_story_counts_utf16']['endnotes']==0
        closed=0;file_model_matches=[]
        for r in bysource[logical]:
            key=norm(r['model_key']);locations=[];contexts=[];found_cycles=[];found_stds=[]
            if ispdf:
                engines=set()
                for u in units:
                    if key in norm(u['text']):locations.append(u['method']+':'+u['location']);engines.add(u['method'])
                assert engines,r
                match_kind='PDF_both_readers_model_located' if len(engines)==2 else 'PDF_one_reader_model_located'
                # Full-page hits do not imply a specific model or table row.
                # The only PDF hit page in this 71-file set is batch 1 page 6,
                # explicitly headed plug-in hybrid passenger cars. Source row
                # positions remain recorded separately for every BEV target.
                assert all(h['source_file'].endswith('mf_batch01.pdf') and h['location']=='page_6' and h['matched_token']=='工况' for h in local_hits)
            else:
                for loc,(cells,scope) in location_data.items():
                    if key in {norm(c) for c in cells}:
                        locations.append(loc);contexts.append(scope)
                        found_cycles.extend(m.group() for m in CYCLE.finditer(scope))
                        # A substring of a vehicle model beginning GB is not a standard citation.
                        found_stds.extend(m.group() for c in cells if norm(c)!=key for m in STD.finditer(c))
                if locations:match_kind='Word_exact_model_cell_located'
                else:
                    paras=[u for u in units if 'DOCX' in u['method'] and key in norm(u['text'])]
                    assert paras and r['model_key']=='SGM6500BEBEV',r
                    locations=[u['location'] for u in paras];contexts=[u['text'] for u in paras];match_kind='explicit_same_entry_correction_body'
                    found_cycles=[m.group() for u in paras for m in CYCLE.finditer(u['text'])]
                    found_stds=[m.group() for u in paras for m in STD.finditer(u['text'])]
                assert not found_cycles,(logical,r['model_key'],found_cycles)
                assert not found_stds,(logical,r['model_key'],found_stds)
            assert r['source_public_date_upper']<='2023-12-10'
            method_counts[match_kind]+=1;file_model_matches.append(r['model_key'])
            model_rows.append({'model_key':r['model_key'],'effective_record_id':r['effective_record_id'],'original_source_record_id':r['original_source_record_id'],'source_file':logical,'source_sha256':src['source_sha256'],'original_source_location':r['source_location'],'whole_source_model_locations':'|'.join(locations),'model_location_method':match_kind,'range_raw':r['source_field_raw'],'source_public_date_upper':r['source_public_date_upper'],'explicit_cycle_newly_obtained':'','test_standard_revision_newly_obtained':'','new_cycle_label_closed':'0','same_cycle_comparability_certified':'0','matching_original_test_report_received':'0','can_use_future_parameter_backfill':'0','result':'retained_backlog_no_explicit_cycle_in_applicable_row_or_general_header_note','scope_note':'完整来源正文、表头及附加故事已复扫；其他型号或其他车辆章节标签不适用；一般制度标准不得推定原试验工况。'})
            model_rows[-1]['applicable_word_row_or_correction_body_text']=' || '.join(contexts)
        assert len(file_model_matches)==int(src['range_source_models'])
        source_rows.append({'source_file':logical,'source_sha256':src['source_sha256'],'detected_format':fmt,'source_bytes':src['bytes'],'backlog_range_models':len(file_model_matches),'whole_source_text_coverage':proof['coverage'],'pages':proof.get('pages',''),'tables':wordmeta['tables'],'all_physical_table_rows':wordmeta['physical_rows'],'word_text_parts':'|'.join(wordmeta['text_parts']),'native_story_counts_utf16':json.dumps(proof.get('native_story_counts_utf16',{}),ensure_ascii=False,sort_keys=True),'blank_pdf_text_pages':len(proof.get('blank_text_pages',[])),'embedded_image_count':len(wordmeta['media_files']) if not ispdf else len(proof.get('pages_with_images',[])),'candidate_keyword_occurrences':len(local_hits),'applicable_new_explicit_cycle_count':closed,'explicit_standard_revision_count':0,'result':'no_keyword_hits' if not local_hits else 'hits_reviewed_none_apply_to_backlog_effective_range','exclusion_reason':'候选词按行/章节判断；CLTC/WLTC仅适用对应已标型号；等速及部分工况在客货车/PHEV章节；标准续航为商品名；GB开头车型代码不是标准。'})
    for h in hits:
        rowcells=h['row_scope_text'].split(' | ');matching=sorted({backlog[norm(c)] for c in rowcells if norm(c) in backlog})
        token=h['matched_token']
        if token=='标准':reason='product_name_standard_range_not_test_standard_or_cycle'
        elif token.startswith('GB'):reason='vehicle_model_GB_prefix_not_standard_citation'
        elif h['source_file'].endswith('mf_batch01.pdf'):reason='batch1_page6_PHEV_passenger_section_generic_cycle_not_BEV_target'
        elif h['method']=='bounded CFB main story':reason='native_keyword_corroboration_exact_scope_assessed_in_corresponding_DOCX_row'
        else:reason='explicit_keyword_in_other_model_row_no_backlog_effective_record_match'
        if CYCLE.search(token) and 'DOCX' in h['method']:assert not matching,h
        classification.append({**h,'matched_backlog_model_cells':'|'.join(matching),'evidence_admitted_for_backlog':'0','exclusion_reason':reason})
    assert len(model_rows)==2208 and len({r['model_key'] for r in model_rows})==2208
    assert len(source_rows)==71 and sum(int(r['backlog_range_models']) for r in source_rows)==2208
    assert detected_counts=={'PDF':15,'CFB_WORD_WPS':52,'ZIP_DOCX':4}
    assert image_count==0
    assert len(pair_checks)==52
    # Recheck exact source fingerprints and read-only requirements inputs.
    assert all(sha(s['physical_path'])==s['source_sha256'] for s in sources)
    assert all(sha(r['input'])==r['sha256'] for r in readcsv(ROOT/'只读输入_SHA256.csv'))
    dump(ROOT/'2208型号_整篇工况补证结果_只读旁表.csv',sorted(model_rows,key=lambda r:r['model_key']))
    dump(ROOT/'71份整篇来源_逐文件纳排与覆盖.csv',source_rows)
    dump(ROOT/'Word_所有表头与表外说明.csv',header_rows)
    dump(ROOT/'关键词命中_逐条纳排理由.csv',classification)
    dump(ROOT/'52份CFB与新转DOCX_关键词多重集对账.csv',pair_checks)
    summary={'as_of_shanghai':datetime.now(timezone.utc).astimezone().isoformat(),'audit_scope':'2208 frozen numeric-ready BEV passenger model records without explicit cycle label; inspect entire 71 exact-SHA sources used by their five scientific fields','backlog_models_before':2208,'field_lineage_rows':11040,'range_lineage_rows':2208,'source_files_requested':71,'source_files_same_sha_obtained':71,'source_files_fully_scanned':71,'detected_source_formats':dict(detected_counts),'pdf_pages_each_reader':page_count,'pdf_pages_without_text':0,'pdf_and_word_embedded_images':0,'native_CFB_all_auxiliary_stories_scanned':52,'native_CFB_nonzero_footnote_or_endnote_counts':0,'CFB_DOCX_keyword_multiset_comparisons_passed':52,'candidate_keyword_occurrences_including_reader_duplicates':len(hits),'sources_with_candidate_keywords':len({h['source_file'] for h in hits}),'source_model_location_methods':dict(method_counts),'new_explicit_cycle_labels_obtained':0,'new_original_test_standard_revisions_obtained':0,'matching_original_test_reports_obtained':0,'same_cycle_comparability_certified':0,'backlog_models_after':2208,'scientific_primary_files_modified':0,'any_year_or_general_standard_cycle_inference':False,'any_future_backfill':False,'conclusion':'The applicable original rows, table headers, general/body notes and all auxiliary text stories provide no additional explicit cycle or matching test-standard revision. Keep all 2208 in the conditional original-test-report backlog. This source-bounded negative result does not assert that such evidence does not exist elsewhere.'}
    summary['delivery_excluded_scratch']=[{'directory':'conversion_inputs','purpose':'temporary same-SHA CFB input copies for LibreOffice; originals available in the existing full-source ZIP and 71-source SHA location table','files':52},{'directory':'__pycache__','purpose':'Python bytecode cache'},{'directory':'proof/profile_*','purpose':'temporary LibreOffice profiles, removed after conversion'}]
    # User-facing timestamp is explicitly in Shanghai, not the host UTC offset.
    from zoneinfo import ZoneInfo
    summary['as_of_shanghai']=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    (ROOT/'public_cycle_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    readme=f'''# 2208 型号试验工况：本轮公开原件完整复扫

本轮已把这 2208 个型号对应的 **71 份同 SHA256 原目录** 全部复扫，未找到能新增适用工况标签或原试验标准版本的证据。**新增闭合 0，剩余仍为 2208 个型号**。这部分仅在要做同工况比较或完整试验口径认定时需要，不阻塞目录事件状态分析。

## 做完的范围

- 从 [2208 型号逐项旁表](2208型号_整篇工况补证结果_只读旁表.csv) 回溯 11,040 条逐字段来源，其中续航来源 2,208 条；71 份源文件均重新核对同字节 SHA256。
- 实际文件签名为 15 份 PDF、52 份 CFB Word/WPS、4 份原生 DOCX。不能仅按扩展名识别文件格式。
- PDF 共 {page_count} 页，PyMuPDF 与 pypdf 两引擎逐页读取，全部页面有文本且无嵌入图片。358 型号在两引擎均可定位，6 型号只在 pypdf 可完整定位，未把这 6 个报成双引擎逐型号一致。
- 52 份 CFB 用受界限检查的 CLX 读取正文及全部附加文本故事，并从同字节复制件新转 DOCX 检查所有表、表头、表外说明、页眉页脚、脚注/尾注与文本框。52 份原生 FIB 均无真实脚注/尾注故事；正文中的“注”仍逐项扫描。52 份关键词多重集与新转 DOCX 全部一致，附加故事无新增相关命中。所有 Word 文件均无嵌入图片。
- 1843 型号定位到 Word 精确型号单元格，另 1 个为 `SGM6500BEBEV` 第 64 批正文中的同条目续航勘误；其承接父项第 62 批也包含在 71 份整篇来源中。

## 命中为什么不能补值

共有 **{len(hits):,} 个候选关键词词次**，含多个读取引擎重复，并不等于独立证据条数。见 [逐条命中及纳排理由](关键词命中_逐条纳排理由.csv)。

- CLTC/WLTC、缩短法只出现在具体其他型号的参数行，不能传播给同表未标型号；这些不是 2208 待补型号的有效续航行。
- 等速及部分工况字样属于客货车、专用车或插混章节。第 1 批 PDF 第 6 页的“工况法”属于插混乘用车，既不属于待补纯电行，也不是具体 NEDC/CLTC 工况标签。
- “标准续航版”是商品名，不是试验标准版本。`GB6850…` 等是广州穗景车型代码，检索 GB 前缀误命中，不是国家标准编号。
- [所有 Word 表头及表外说明](Word_所有表头与表外说明.csv) 中没有适用于待补纯电续航行的具体工况/标准版本总说明。

因此不按年份、标准发布/实施日或一般“工况法”猜 NEDC/CLTC，不将未来参数回填公告前数据，不认证配置身份或试验合法性。

## 确实还需向持有人索取什么

若要继续同工况比较，向申报企业认证/合规部门、原检测机构或授权产品档案取得：公告前对应配置的原续航试验报告，包含具体工况、试验标准及版次、报告编号/日期、配置键和该报告与有效申报条目的对应依据。报告私下形成的日期不能自动充当此前已公开日期；若用于公告前公开信息冻结口径，还需要可验证的公开可得时间。

本次结论限定于这 71 份精确来源及 2208 个有效条目，不宣称全网或非公开档案没有这些报告。已收尾“是否漏读原目录表头、整篇脚注”的核查，不继续重复把已查无适用证据的表头当缺口。

## 核验与复跑

- [逐文件覆盖与纳排](71份整篇来源_逐文件纳排与覆盖.csv)、[精确源文件位置](71份工况来源原件_同字节定位.csv)、[读取证明](full_source_extraction_proof.json)、[结论 JSON](public_cycle_summary.json)。
- [52 份原生 CFB / 新转 DOCX 关键词对账](52份CFB与新转DOCX_关键词多重集对账.csv)、[只读输入指纹](只读输入_SHA256.csv)、[本目录 SHA256 清单](文件_SHA256.csv)。
- 在现有项目环境执行 `python extract_full_sources.py --convert-ole` 后执行 `python finalize_cycle_review.py`。换到新机器后，解压已有完整原件 ZIP，以其项目根目录传入 `--root /路径/购置税项目_原件补齐与修订_v1_5_20261009`，需要时以 `--requirements /路径/v1_5/requirements` 指定需求表目录；第二个脚本也支持 `--requirements`。源目录、需求表与科学主数据均只读；转换件与旁表只写入本目录。依赖 Python、PyMuPDF、pypdf 与 LibreOffice，原生受界限检查的 CFB/Word 读取器已随目录保留。
- `conversion_inputs/` 是复跑时从原件生成的临时同 SHA 转换缓存，不重复交付；原件仍从上述同 SHA 定位表及已发布完整原件 ZIP 取得。输入复制件的原 SHA 与相对缓存路径保留在读取证明中。交付 SHA 清单排除该目录、Python 缓存和临时 LibreOffice 配置目录；这不删除或改动任何科学原件。

本轮科学主表改动 0，未来回填 0，法律/配置认证新增 0。核查时点：{summary['as_of_shanghai']}。
'''
    (ROOT/'README.md').write_text(readme)
    files=[p for p in ROOT.rglob('*') if p.is_file() and p.name!='文件_SHA256.csv' and '__pycache__' not in p.parts and 'conversion_inputs' not in p.parts and not any(part.startswith('profile_') for part in p.parts)]
    dump(ROOT/'文件_SHA256.csv',[{'file':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(files)])
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
