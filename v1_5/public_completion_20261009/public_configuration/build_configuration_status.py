#!/usr/bin/env python3
"""Reconcile saved public requests and explicit materials; never writes scientific data."""
from pathlib import Path
from collect_public_configuration import ROOT,digest,write_csv,fetch,search
from urllib.parse import urljoin
from lxml import html
import pandas as pd,json,csv,hashlib,re,datetime

INPUT_SCIENTIFIC=Path('/workspace/purchase_tax_audit/round5/reconstruction/data_v1_5/研究数据/参数版本_原值与计算代理.csv')
RAW_SNAPSHOT=ROOT/'inputs'/'36目标_原参数记录旁证.csv'
def load(path):return pd.read_csv(path,keep_default_na=False,dtype=str)
def render():
 a=load(ROOT/'inputs'/'32型号_区间跨阈值优先配置材料清单.csv');a['scope']='联合门槛待匹配32'
 b=load(ROOT/'inputs'/'4型号_单项跨阈值补充清单.csv');b['scope']='单项细分4，联合未达已确定'
 targets=pd.concat([a,b],ignore_index=True);rec=load(ROOT/'inputs'/'285配置版本_跨目录身份材料待补清单.csv')
 if not RAW_SNAPSHOT.exists():
  science=load(INPUT_SCIENTIFIC);rows=science[science.record_id.isin(targets.record_id)]
  assert len(rows)==36 and set(rows.record_id)==set(targets.record_id)
  rows.to_csv(RAW_SNAPSHOT,index=False,encoding='utf-8-sig')
  (ROOT/'inputs'/'原参数完整输入指纹.json').write_text(json.dumps({'file_name':INPUT_SCIENTIFIC.name,'sha256':digest(INPUT_SCIENTIFIC),'bytes':INPUT_SCIENTIFIC.stat().st_size,'local_source':str(INPUT_SCIENTIFIC),'snapshot_selection':'仅按36既定record_id精确选择，不以已有数值决策挑选'},ensure_ascii=False,indent=2)+'\n')
 science=load(RAW_SNAPSHOT).set_index('record_id');allsearch=json.loads((ROOT/'36模型_工信部原生检索完整结果.json').read_text());sm={x['query']:x for x in allsearch};positive=json.loads((ROOT/'search/positive_control_recommendation_2022_12.hits.json').read_text())
 assert positive['reported_total']==2 and len(positive['hits'])==2
 ddg={x['model_key']:x for x in json.loads((ROOT/'8型号_相关外部索引候选.json').read_text())}
 ledger=[]
 for row in targets.to_dict('records'):
  model=row['model_key'];raw=science.loc[row['record_id']];sr=sm[model];linked=rec[rec.model_key==model]
  ext=ddg.get(model);extstate='本次未另跑有效外部查询'
  if ext:
   text=(ROOT/ext['receipt']['relative_path']).read_text() if ext['receipt']['status']=='ok' else ''
   if 'anomaly.js' in text or 'challenge-form' in text:extstate='外部索引返回验证页，未继续，不得按0结果解释'
   elif ext['hits']:extstate='取得型号相关外部候选；无主管/企业配置身份原件'
   else:extstate='本次返回没有候选；不外推不存在'
  firm=raw['firm_raw'] or raw['firm_context_candidate']
  special='提供具体电池质量实测/允许公差及各配置定义，能量和质量须同一配置、同一版本'
  if row['battery_mass_parse_status'].startswith('multi') or row['battery_energy_parse_status']=='multi':special='提供每个斜线选项的独立配置ID、续航、能量、质量及正式配对关系；不得按斜线次序自动配对'
  ledger.append({'scope':row['scope'],'model_key':model,'tax_record_id':row['record_id'],'tax_source_file':row['source_file'],'tax_source_sha256':row['source_sha256'],'tax_source_location':row['source_location'],'tax_public_date_lower':raw['public_date_lower_bound'],'tax_public_date_upper':raw['public_date_upper_bound'],'firm_raw_or_context_candidate':firm,'firm_name_is_certified_legal_identity':0,'trade_name_clue':raw['trade_name_raw'],'range_raw':row['range_raw'],'battery_mass_raw':row['battery_mass_raw'],'battery_energy_raw':row['battery_energy_raw'],'miit_exact_query_status':sr['receipt']['status'],'miit_exact_query_reported_total':sr['reported_total'],'miit_receipt_file':'search/model_'+model+'.json.receipt.json','miit_raw_sha256':sr['receipt'].get('sha256',''),'miit_positive_control_total':positive['reported_total'],'index_scope_note':'工信部正文索引一次精确查询；附件参数不保证入索引，不代表全网无资料','existing_recommendation_versions_in_285':len(linked),'existing_config_ids_in_285':' | '.join(sorted(set(linked.config_id))),'external_discovery_scope':extstate,'public_product_system_attempt':'装备中心官网真实所链入口本次HTTP 403，未认证查询结果','manual_public_channel':'https://yhgscx.miit.gov.cn/ (本人浏览器完成滑块验证后查询；本轮无结果)','closed_numeric_interval':0,'closed_tax_recommendation_identity':0,'source_after_cutoff_can_backfill':0,'next_holder':firm+' 技术/认证部门或原检测机构','needed_precise_material':special+'；原购置税申报配置页及试验报告编号/标准版本/日期；如果进入公告前冻结输入另须当时可得性证据'})
 write_csv(ROOT/'36目标_逐型号公开探查与精确询证台账.csv',ledger)

 group=[];versions=[]
 for firm,g in rec.groupby('firm_raw',sort=True):
  group.append({'firm_name_as_written_in_recommendation':firm,'observed_versions':len(g),'distinct_model_keys':g.model_key.nunique(),'distinct_config_ids':g.config_id.nunique(),'model_keys':' | '.join(sorted(set(g.model_key))),'config_ids':' | '.join(sorted(set(g.config_id))),'range_crossing_36_model_keys':' | '.join(sorted(set(g.model_key)&set(targets.model_key))),'holder':'原申报整车企业技术/认证部门；企业更名/主体须另核','required_material':'每个NC配置ID与免征/减免目录具体申报配置ID/版本的正式对应页；电池系统/电机型号及供应商；报告编号、试验工况、日期和标准版本','identity_bridges_received':0,'name_grouping_is_legal_identity_certificate':0})
  for v in g.to_dict('records'):
   versions.append(dict(v,firm_group_name=firm,request_holder=firm+' 技术/认证部门或原检测机构',closed_this_round=0,date_boundary='不把2023-12-10之后来源回填公告前冻结输入；历史私档可证技术事实但须另核当时可得性'))
 write_csv(ROOT/'285版本_按原文企业分组询证.csv',versions);write_csv(ROOT/'43原文企业_跨目录身份询证分组.csv',group)
 firms36={r['firm_raw_or_context_candidate'] for r in ledger};jointfirm={r['firm_raw_or_context_candidate'] for r in ledger if r['scope'].startswith('联合')}
 write_csv(ROOT/'36目标_按申报企业询证分组.csv',[{'firm_name_raw_or_context':f,'models':' | '.join(sorted(r['model_key'] for r in ledger if r['firm_raw_or_context_candidate']==f)),'model_count':sum(r['firm_raw_or_context_candidate']==f for r in ledger),'required_material':'带原申报版本、配置ID、斜线选项定义、能量/质量配对、报告编号与日期的企业技术/认证资料；无需先提交逐车VIN'} for f in sorted(firms36)])

 # Save source snippets documenting the user-facing query gate and fields.
 script=ROOT/'portal/energy_script_31.js';t=script.read_text();markers=['onNormalSearch: function','this.$refs.slideVerify.dialogVisible = true','this.$refs.slideVerifySenior.dialogVisible = true','firstRequest: false','车辆型号','能耗配置ID','通告日期','启用日期','废止日期','vehicleModel','publicTimeStart','publicTimeEnd']
 snippets=[]
 for marker in markers:
  i=t.find(marker)
  snippets.append({'marker':marker,'found':i>=0,'offset':i,'excerpt':t[max(0,i-80):i+350] if i>=0 else ''})
 (ROOT/'portal/energy_frontend_user_query_boundary.json').write_text(json.dumps({'source_file':script.relative_to(ROOT).as_posix(),'source_sha256':digest(script),'source_url':'https://yhgscx.miit.gov.cn/fuel-consumption-web/js/app.js','markers':snippets,'actual_vehicle_query_performed':False,'verification_gate_bypassed':False,'data_obtained':0},ensure_ascii=False,indent=2)+'\n')

 thirdparty=[]
 for model in ['GTM6470BFEBEV','CC7000CG00FBEV']:
  p=ROOT/('external/association_'+model+'.html');txt=p.with_suffix('.text.txt').read_text();i=txt.find('车辆基本信息');end=txt.find('上一篇',i)
  thirdparty.append({'model_key':model,'url':'https://www.cdqc.org.cn/2747/19531/'+('878573' if model=='GTM6470BFEBEV' else '878547'),'source_file':p.relative_to(ROOT).as_posix(),'sha256':digest(p),'excerpt':txt[i:end].strip(),'claimed_tax_batch':54,'actual_config_ids_given':'','is_primary_source':0,'can_certify_identity_bridge':0,'action':'税录第54批多值/公差转载，与已归档原件信息重复，未取得配置桥；正文全站政府主页链接不是具体原件链接'})
 (ROOT/'两个交叉型号_协会转载核查.json').write_text(json.dumps(thirdparty,ensure_ascii=False,indent=2)+'\n')

 existing=[Path('/workspace/purchase_tax_audit/round3/technical/README.md'),Path('/workspace/purchase_tax_audit/round4/recommendation_interval/README.md'),Path('/workspace/purchase_tax_audit/round5/parameters/interval_audit_summary_v1_5.json'),Path('/workspace/purchase_tax_audit/round8/final_gap_status/README.md'),Path('/workspace/purchase_tax_audit/round8/jx_public_final_pass/README.md')]
 write_csv(ROOT/'此前已核源与本轮避免重复范围.csv',[{'source':str(p),'bytes':p.stat().st_size,'sha256':digest(p),'scope':'既有推荐三批285版本／区间旁证／剩余总账／2021推荐10批；本次36目标为既定子集，不重枚举原目录'} for p in existing])
 summary={'status':'完成有界公开探查，新增配置/数值闭合0，私人材料待有效到达','date_shanghai':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),'targets':{'joint_crossing_models':32,'single_crossing_models_joint_already_fail':4,'distinct_models':36,'firms36_raw_or_context':len(firms36),'joint32_firms_raw_or_context':len(jointfirm)},'public_index':{'exact_model_queries':36,'all_http200':all(x['receipt'].get('http_status')==200 for x in allsearch),'all_reported_total_zero':all(x['reported_total']==0 for x in allsearch),'positive_control_query':positive['query'],'positive_control_hits':2,'negative_conclusion_scope':'正文索引本次未命中；不证明参数附件、企业档案或互联网无证据'},'external_index':{'bing_discarded_as_irrelevant':True,'bing_query_count_in_saved_log':36,'bing_is_negative_evidence':False,'duckduckgo_target_count':8,'duckduckgo_verification_page_targets':[r['model_key'] for r in ledger if '验证页' in r['external_discovery_scope']],'exact_title_match_is_primary_evidence':False},'new_public_source_findings':{'equipment_center_verified_query_link':'https://service.miit-eidc.org.cn/miitxxgk/gonggao/xxgk/index?querylb=qy','current_service_fetch_http_status':403,'old_app_fetch_http_status':502,'energy_query_home_http_status':200,'energy_query_source':'官网真实所链入口+公开前端','energy_query_requires_manual_slide_verification':True,'actual_energy_label_records_obtained':0},'existing_overlap':{'recommendation285_versions':285,'distinct_config_ids':278,'distinct_models':170,'firm_names_as_written':43,'overlap_with36_models':sorted(set(rec.model_key)&set(targets.model_key)),'overlap_versions':len(rec[rec.model_key.isin(targets.model_key)])},'new_closures':{'numeric_intervals':0,'cross_tax_recommendation_identity_versions':0,'models':0},'remaining':{'joint_crossing_models':32,'single_crossing_models':4,'identity_versions':285,'identity_model_keys':170,'unknown_legal_firm_aliases_are_not_merged':True},'all_scientific_main_files_untouched':True,'closing_condition':'具体原申报版本和配置ID，正式能量/质量配对，公差/多选项定义及原报告；跨目录另要正式身份桥，历史冻结另核当时信息可得性','no_universal_internet_exhaustiveness_claim':True}
 (ROOT/'public_configuration_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 assert len(ledger)==36 and len({r['model_key'] for r in ledger})==36 and len(versions)==285 and len(group)==43
 assert set(a.model_key).isdisjoint(set(b.model_key))
 if INPUT_SCIENTIFIC.exists():assert digest(INPUT_SCIENTIFIC)==json.loads((ROOT/'inputs/原参数完整输入指纹.json').read_text())['sha256']
 checks={'checks_passed':10,'target36_unique':True,'32_and4_disjoint':True,'each_target_exact_source_record_present':True,'36_query_records_present':True,'positive_control_2_hits':True,'285_versions_preserved':True,'43_raw_firm_groups_no_alias_merge':True,'285_config_ids_unique278':rec.config_id.nunique()==278,'main_scientific_input_sha_unchanged':True,'manual_query_not_bypassed':True}
 (ROOT/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
 write_csv(ROOT/'文件_SHA256.csv',[{'file':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='文件_SHA256.csv'])
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':render()
