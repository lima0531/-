"""Read documentary version evidence; never rebuild or mutate previous data."""
from pathlib import Path
import csv, datetime, hashlib, json
ROOT=Path('/workspace/purchase_tax_audit')
OUT=ROOT/'round6/risk_change'
paths={
 'compact_readme':ROOT/'compact_input_20261008/购置税项目_必要数据精简包_20261008/README.md',
 'intermediate_summary':ROOT/'round3/reconstruction/intermediate_2804/reconstruction_summary.json',
 'intermediate_manifest':ROOT/'round3/reconstruction/intermediate_2804/data_v1_3_manifest.csv',
 'final_summary':ROOT/'round3/reconstruction/reconstruction_summary.json',
 'final_manifest':ROOT/'round3/reconstruction/data_v1_3_manifest.csv',
 'rebuild_script':ROOT/'round3/reconstruction/rebuild_with_new_withdrawals.py',
 'v1_3_readme':ROOT/'round3/reconstruction/data_v1_3/README_版本v1_3.md',
 'v1_4_readme_copy':ROOT/'round4/data_v1_4/README_版本v1_3.md',
 'v1_4_copy_script':ROOT/'round4/build_final_version.py',
 'v1_5_readme_copy':ROOT/'round5/reconstruction/data_v1_5/README_版本v1_3.md',
 'v1_5_current_boundaries':ROOT/'round5/reconstruction/data_v1_5/字段说明_版本边界.md',
 'v1_5_copy_script':ROOT/'round5/reconstruction/build_effective_correction_version.py',
 'v1_5_finalizer_script':ROOT/'round5/finalize_data_v1_5.py',
}
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
before={k:digest(p) for k,p in paths.items()}
source_metadata={k:{'path':str(p),'bytes':p.stat().st_size,'sha256':before[k]} for k,p in paths.items()}
def quote(source,needle):
 lines=paths[source].read_text(encoding='utf-8-sig').splitlines()
 hits=[{'line_1based':i,'text':s} for i,s in enumerate(lines,1) if needle in s]
 assert hits,(source,needle)
 return {'source_id':source,'path':str(paths[source]),'matches':hits}
stages=[]
for source,stage_name in [('intermediate_summary','local_intermediate_2804'),('final_summary','local_final_2805')]:
 data=json.loads(paths[source].read_text())
 keys=['generated_at_utc','baseline_root','output_root','cohort_models','new_cohort_withdrawal_events','preannouncement_risk_models','numeric_input_ready']
 vals={k:data[k] for k in keys}
 vals['source_correction_base_used']=data.get('source_correction_base_used')
 stages.append({'stage_id':stage_name,'summary_source_id':source,'recorded_values':vals,'counts_are_read_from_summary_not_recomputed':True})
assert stages[0]['recorded_values']['preannouncement_risk_models']==2804
assert stages[1]['recorded_values']['preannouncement_risk_models']==2805
assert stages[0]['recorded_values']['output_root']==stages[1]['recorded_values']['output_root']==str(ROOT/'round3/reconstruction/data_v1_3')
manifest_readmes={}
for source in ['intermediate_manifest','final_manifest']:
 with paths[source].open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
 target=[r for r in rows if r['path']=='README_版本v1_3.md'];assert len(target)==1
 manifest_readmes[source]=target[0]
assert manifest_readmes['intermediate_manifest']['sha256']!=manifest_readmes['final_manifest']['sha256']
assert manifest_readmes['final_manifest']['sha256']==before['v1_3_readme']
assert before['v1_3_readme']==before['v1_4_readme_copy']==before['v1_5_readme_copy']
claims=[
 {'claim_id':'F01','status':'documented_local_fact','claim':'精简包 README 自称从2026-10-08完整包v1.1提取，研究边界文本记录风险集2877；这只界定该指定精简包自身的声明。','evidence':[quote('compact_readme','完整包v1.1提取'),quote('compact_readme','2877公告前在册风险型号')]},
 {'claim_id':'F02','status':'documented_local_fact','claim':'本地保存的2804中间摘要与2805最终摘要是两个不同阶段记录，生成时间、baseline_root和风险数均不同，但output_root相同且均为data_v1_3。','evidence_source_ids':['intermediate_summary','final_summary'],'stage_ids':['local_intermediate_2804','local_final_2805']},
 {'claim_id':'F03','status':'documented_local_fact','claim':'构建脚本把输出数据目录固定命名为data_v1_3并生成README_版本v1_3.md；仅这一目录名不会自动区分中间和最终构建阶段。','evidence':[quote('rebuild_script',"data=out/'data_v1_3'"),quote('rebuild_script',"(data/'README_版本v1_3.md').write_text")]},
 {'claim_id':'F04','status':'documented_local_fact','claim':'中间与最终清单都记录README_版本v1_3.md，但清单中的字节数和SHA不同。当前最终README字节与最终清单匹配；中间目录现仅保存摘要、清单和差异记录，不能据此称其完整2804数据快照仍在该目录中。','evidence_source_ids':['intermediate_manifest','final_manifest','v1_3_readme'],'manifest_readme_entries':manifest_readmes},
 {'claim_id':'F05','status':'documented_local_fact','claim':'round3最终v1.3 README明确写2805，且其2088字节SHA与round4及round5同名README完全一致；此比较仅认证该README文件的字节继承，未比较全部科学数据。','evidence':[quote('v1_3_readme','公告前风险集现为2805')],'compared_source_ids':['v1_3_readme','v1_4_readme_copy','v1_5_readme_copy'],'identical_sha256':before['v1_3_readme']},
 {'claim_id':'F06','status':'documented_local_fact','claim':'round4脚本复制round3/data_v1_3为data_v1_4；round5脚本默认复制round4/data_v1_4为data_v1_5。round5当前字段说明明确同名v1.3 README为历史记录，故位于v1.5目录中不表示当前数据的版本标签仍为v1.3。','evidence':[quote('v1_4_copy_script',"BASE=ROOT.parent/'round3/reconstruction/data_v1_3'"),quote('v1_4_copy_script','shutil.copytree(BASE,OUT)'),quote('v1_5_copy_script',"'round4/data_v1_4'"),quote('v1_5_copy_script',"data = out / 'data_v1_5'"),quote('v1_5_copy_script','shutil.copytree(base, data)'),quote('v1_5_current_boundaries','`README_版本v1_3.md`、`README_版本v1_4.md`')]},
]
not_established=[
 {'claim_id':'U01','status':'not_established_by_reviewed_materials','claim':'用户所称另一份“v1.3”与本地2804中间阶段、2805最终阶段或指定compact_input之间的唯一对应关系，本次指定材料尚不能证明。','reason':'未将该另一份具体产物的包SHA、确定归档成员或关键文件指纹与上述阶段记录建立可核查映射；相同版本字符串或同名README不足以唯一定位。'},
 {'claim_id':'U02','status':'inference_not_authorized_by_evidence','claim':'不能因为compact README自称v1.1，或v1.5中保留v1.3同名README，就断言用户另一份v1.3只补日期、未补历史撤销、风险集必为2877或必为2805。','reason':'这些证据界定的是已定位本地文件的声明和继承，不能跨产物推断另一包的范围。'},
 {'claim_id':'U03','status':'outside_this_audit_scope','claim':'2877、2804、2805之间逐型号变动及具体来源因果，本任务未复算或认证。','reason':'本任务只核命名与阶段记录；逐型号源追溯由风险变化主核查执行。'},
]
intermediate_files=sorted(p.name for p in (ROOT/'round3/reconstruction/intermediate_2804').iterdir() if p.is_file())
report={
 'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'scope':'指定本地文件的版本命名、阶段摘要和同名README继承事实核查；不重建风险模型集合',
 'resolved_path_note':'请求中的round5/data_v1_5实际本地目录为round5/reconstruction/data_v1_5。',
 'source_files':source_metadata,
 'local_stage_records':stages,
 'intermediate_directory_actual_file_names':intermediate_files,
 'same_version_label_has_multiple_local_build_stages':True,
 'same_output_root_recorded_for_intermediate_and_final':True,
 'claims':claims,
 'not_established':not_established,
 'naming_for_followup':'引用本地v1.3时同时注明阶段、摘要SHA和生成时间；用户另一份v1.3保持“未对应”，待其具体产物指纹可比后再对应。',
 'risk_model_sets_recomputed':False,
 'old_scientific_data_written':False,
}
after={k:digest(p) for k,p in paths.items()}
assert before==after
report['reviewed_source_file_hashes_unchanged']=True
report['reviewed_source_file_count']=len(paths)
(OUT/'version_label_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
md='''# 版本命名事实核查

本地“v1.3”有两个可追溯构建阶段：`intermediate_2804/reconstruction_summary.json`记录风险集2804，生成于2026-10-08 14:13:51 UTC，基于`data_v1_2`；最终`reconstruction_summary.json`记录2805，生成于14:45:42 UTC，基于`corrected_source_base`。两份摘要均记录输出目录为`round3/reconstruction/data_v1_3`，构建脚本第76行也固定使用这个目录名。这是本地阶段产物事实，不应把标签“v1.3”当作阶段唯一标识。

中间目录现在保存摘要、清单和差异记录，未保存完整2804数据快照。两阶段清单都记录`README_版本v1_3.md`，但中间记录1763字节、SHA `5b251b827b6854119effc0f86cbb84fe0c5bd4777f747410e18c5a808ac4b0ac`；最终为2088字节、SHA `5b6b85efc0a4a021e301c4d62e28c55b915b20c64c9cf9c4ca5f3744a33e73fe`。当前最终README与最终清单一致，正文第7行写2805。

`round5/reconstruction/data_v1_5/README_版本v1_3.md`与round3最终README逐字节相同；v1.5当前字段说明第19行明确它是历史记录。构建脚本的copytree路径支持其经v1.4保留至v1.5的继承关系。这仅认证README文件，不表示v1.5全部科学数据与v1.3相同。

指定compact_input的README第3行自称从完整包v1.1提取，其研究边界记录2877。这只能说明该已定位精简包的声明。用户所称另一份“v1.3”尚未由包SHA、归档成员或关键文件指纹对应到上述本地阶段；不能只凭旧compact或同名README断定另一包的范围、风险数或是否包含撤销补采。

本核查未复算风险型号集合，也未修改旧数据。13份读取文件的SHA在核查前后保持一致；完整文件指纹、证据行号和可证/未对应分界见`version_label_audit.json`。
'''
(OUT/'版本命名核查.md').write_text(md,encoding='utf-8')
print(json.dumps({'output':str(OUT/'version_label_audit.json'),'source_files_checked':len(paths),'source_hashes_unchanged':True,'risk_sets_recomputed':False,'local_stage_counts_reported':[2804,2805],'same_final_readme_sha256':before['v1_3_readme'],'external_other_v1_3_correspondence':'not_established'},ensure_ascii=False,indent=2))
