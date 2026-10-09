"""Read-only targeted review of already obtained JX6550 sources; no network."""
from pathlib import Path
import csv,json,sys,hashlib,zipfile,xml.etree.ElementTree as ET
ROOT=Path('/workspace/purchase_tax_audit');OUT=Path(__file__).parent
TARGET='JX6550T-M5BEV';SIBLING='JX6570T-M5BEV';CUTOFF='2023-12-10'
sys.path.insert(0,str(ROOT/'round3/archive'))
from word_piece_text import extract
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
enumerated=rows(ROOT/'round5/catalogues/97份目录_独立科学原值枚举7203行.csv')
target=[r for r in enumerated if r['model_key']==TARGET]
assert len(target)==2
byname={r['source_file']:r for r in target}
assert byname['mf_batch48.doc']['battery_energy_raw']==''
assert byname['cat_batch1.doc']['battery_energy_raw']=='65.17'
proofs=[]
for sub in ['免征目录/mf_batch48.doc','减免目录/cat_batch1.doc']:
 p=ROOT/'round3/archive/recovered'/sub;t,proof=extract(p)
 assert t.count(TARGET)==1
 assert sha(p)==byname[p.name]['source_sha256']
 pos=t.find(TARGET)
 proofs.append({'source':str(p),'source_sha256':sha(p),'model_occurrences_in_bounded_main_story':1,'main_story_quote':t[max(0,pos-25):pos+len(TARGET)+100],'main_story_reader_proof':proof})
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
converted=OUT/'mf_batch48.docx'
with zipfile.ZipFile(converted) as z:d=ET.fromstring(z.read('word/document.xml'))
xmlproof=[]
for ti,table in enumerate(d.findall('.//w:tbl',ns)):
 header=[''.join(x.text or '' for x in c.findall('.//w:t',ns)) for c in table.findall('w:tr',ns)[0].findall('w:tc',ns)]
 for ri,tr in enumerate(table.findall('w:tr',ns)):
  cells=[''.join(x.text or '' for x in c.findall('.//w:t',ns)) for c in tr.findall('w:tc',ns)]
  if TARGET in cells:xmlproof.append({'table_0based':ti,'row_0based_including_header':ri,'header':header,'row_cells':cells,'battery_energy_col_0based':7,'battery_energy_raw':cells[7]})
assert len(xmlproof)==1 and len(xmlproof[0]['row_cells'])==9
assert '总能量' in xmlproof[0]['header'][7] and xmlproof[0]['battery_energy_raw']==''
corrections=rows(ROOT/'round4/catalogues/目录内全部勘误_公开原文扫描.csv')
target_corrections=[r for r in corrections if TARGET in r['correction_text_raw']]
sibling_corrections=[r for r in corrections if SIBLING in r['correction_text_raw']]
assert not target_corrections and len(sibling_corrections)==1
snapshots=[r for r in rows(ROOT/'round5/reconstruction/data_v1_5/研究数据/重建样本_两截点参数与暴露.csv') if r['model_key']==TARGET]
frozen=next(r for r in snapshots if r['cutoff']==CUTOFF)
later=next(r for r in snapshots if r['cutoff']=='2023-12-31')
assert frozen['battery_energy_point']==frozen['density_proxy_point']==''
assert frozen['possible_latest_record_ids']=='old-48-Word97--0-20'
assert later['battery_energy_point']=='65.17' and later['possible_date_upper_max']=='2023-12-26'
assert frozen['configuration_identity_certified']=='0' and later['configuration_identity_certified']=='0'
recommended=[r for r in rows(ROOT/'round5/reconstruction/data_v1_5/推荐参数/推荐参数_配置版本长表.csv') if r.get('model_key')==TARGET]
result={
 'model_key':TARGET,'cutoff':CUTOFF,'network_requests':0,'scientific_data_modified':False,
 'local_review_scope':'已有97份目录的7203行完整参数枚举、上轮全部勘误扫描、两份真实原DOC、v1.5原值与冻结截点及285条推荐配置版本；不声称遍历互联网上全部公开记录。',
 'original_batch48_energy_cell_is_empty':True,
 'independent_layout_check':{'method':'原始DOC用LibreOffice重新转成OOXML后直接读取真实w:tbl/w:tr/w:tc单元格，独立于原CLX文本分列规则','derived_docx':str(converted),'derived_docx_sha256':sha(converted),'converted_docx_is_official_original':False,'tables':xmlproof},
 'raw_story_source_checks':proofs,
 'complete_catalogue_exact_model_hits':target,
 'frozen_snapshot':frozen,'late_snapshot':later,
 'observed_public_date_of_first_nonempty_energy_in_retained_exact_model_catalogues':'2023-12-26',
 'observed_nonempty_battery_energy_kWh':'65.17',
 'target_model_corrections_in_cached_scan':target_corrections,
 'non_target_sibling_correction':sibling_corrections,
 'sibling_transfer_allowed':False,
 'target_model_recommendation_rows_in_retained_285_versions':recommended,
 'configuration_identity_declaration_obtained':False,
 'explicit_pre_cutoff_correction_obtained':False,
 'conclusion':'截至2023-12-10冻结信息集，现有已取回官方原件没有可回填的JX6550T-M5BEV明确总能量值。原48批真实单元格为空；2023-12-26的65.17为公告后观察，字段相似不足以认证同配置；JX6570T-M5BEV的更正不可移用。保留公告前能量和密度为空。',
 'minimum_user_material':'第48批所对应申报配置的电池总能量原始申报页或检测报告，含可核验形成/申报日期（不晚于2023-12-10）、型号、配置/电池系统身份与总能量单位；或该截止日前公开的正式针对本型号的官方更正。若提供较晚材料，须有正式同配置与历史适用范围声明，仍需单独审定其是否满足冻结信息集。',
 'checks_passed':['old_original_sha_matches_index','late_original_sha_matches_index','exact_model_one_occurrence_in_each_original','direct_OOXML_energy_column_empty','complete97_catalogue_exact_model_hits_only_two','target_absent_from_cached_corrections','sibling_correction_not_target','frozen_snapshot_not_future_filled','cross_period_configuration_identity_uncertified'],
}
(OUT/'jx6550_local_review_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
with (OUT/'精确型号_两份原件字段.csv').open('w',encoding='utf-8-sig',newline='') as f:
 fields=list(target[0]);w=csv.DictWriter(f,fields);w.writeheader();w.writerows(target)
print(json.dumps({'model':TARGET,'checks_passed':len(result['checks_passed']),'old_energy':'','late_energy':'65.17','late_date':'2023-12-26','target_correction_found':False,'scientific_data_modified':False},ensure_ascii=False))
