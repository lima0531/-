#!/usr/bin/env python3
"""Group source-backed evidence requests without changing science or sending messages."""
import csv
import hashlib
import json
import unicodedata
from collections import defaultdict, Counter
from pathlib import Path

OUT=Path(__file__).resolve().parent
AUDIT=OUT.parents[1]
BASE=AUDIT/'round5/reconstruction/data_v1_5'
REQ=AUDIT/'round5/requirements'
FILES={
 'JX原空能量':'仅1型号_公告前真实原空字段待补.csv',
 '32联合跨界':'32型号_区间跨阈值优先配置材料清单.csv',
 '4单项细分':'4型号_单项跨阈值补充清单.csv',
 '285配置身份':'285配置版本_跨目录身份材料待补清单.csv',
 '19低温优先':'19配置版本_低温报告优先待补清单.csv',
 '92逐车资格':'92再申报型号_逐车材料待补清单.csv',
 '2208试验口径':'2208数值可用型号_公告前试验工况待核清单.csv',
}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(name,rows,columns=None):
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=columns or list(rows[0]));w.writeheader();w.writerows(rows)
def norm(s):return unicodedata.normalize('NFKC',s).strip()


def main():
 OUT.mkdir(parents=True,exist_ok=True)
 input_files=[REQ/f for f in FILES.values()]
 param_path=BASE/'研究数据/参数版本_字段勘误生效视图.csv'
 raw_path=BASE/'研究数据/参数版本_原值与计算代理.csv'
 link_path=BASE/'研究数据/资格事件_逐原件连接.csv'
 input_files += [param_path,raw_path,link_path]
 before={str(p):sha(p) for p in input_files}
 params={r['record_id']:r for r in read(param_path)}
 raw={r['record_id']:r for r in read(raw_path)}
 event_links=defaultdict(list)
 for r in read(link_path):event_links[r['event_id']].append(r)
 tasks=[]
 def route_record(p):
  target=p['target_record_id'] if p['composition_kind']=='explicit_same_entry_field_correction' else ''
  q=raw[target] if target else p
  name=q['firm_raw'] or q['firm_context_candidate']
  basis='原记录firm_raw' if q['firm_raw'] else '原件企业合并格/上下文候选；非登记实体认证'
  return norm(name),q,basis
 def task(scope,r,key,config='',records=None):
  if r.get('firm_raw'):
   routes=[(norm(r['firm_raw']),None,'推荐原文企业名')]
  else:
   routes=[]
   for p in records or []:
    name,q,basis=route_record(p)
    if name and name not in [x[0] for x in routes]:routes.append((name,q,basis))
  assert len(routes)==1, (scope,r['model_key'],routes)
  firm,q,basis=routes[0]
  date=r.get('source_public_date') or r.get('observed_date_upper') or r.get('first_reapplication_observed_date_upper') or (records[0]['public_date_upper_bound'] if records else '')
  source_file=r.get('source_file') or r.get('effective_source_files') or (records[0]['source_file'] if records else '')
  fingerprint=r.get('source_sha256') or r.get('effective_source_sha256s') or (records[0]['source_sha256'] if records else '')
  original_name=r.get('firm_raw') or (q['firm_raw'] or q['firm_context_candidate'] if q else '')
  tasks.append({'firm_routing_name':firm,'firm_original_text':original_name,'firm_literal_cell_text':r.get('firm_raw') or (q['firm_raw'] if q else ''),'firm_route_basis':basis,'firm_route_source_record_id':q['record_id'] if q else '', 'firm_route_source_sha256':q['source_sha256'] if q else fingerprint,'purpose_scope':scope,'request_key':key,'model_key':r['model_key'],'recommendation_config_id':config,'source_observation_date_upper':date,'source_file':source_file,'source_sha256':fingerprint,'source_record_ids':';'.join(p['record_id'] for p in records or []),'source_location':r.get('source_location') or (records[0]['source_location'] if records else ''),'required_materials':r.get('required_materials') or r.get('needed_materials') or r.get('needed_material') or r.get('needed_fields') or scope,'current_configuration_identity_certified':'0','entity_register_identity_certified':'0','source_routing_is_not_configuration_bridge':'1'})
 for scope,file in FILES.items():
  rs=read(REQ/file)
  for r in rs:
   if scope in ['285配置身份','19低温优先']:
    task(scope,r,r['observation_version_key'],r.get('config_id') or r.get('recommendation_config_id'))
   elif scope=='92逐车资格':
    records=[]
    for event in r['reapplication_event_ids'].split(';'):
     records += [params[l['source_record_id']] for l in event_links[event] if l['source_record_id'] in params]
    assert records
    task(scope,r,'vehicle|'+r['model_key'],records=records)
   else:
    ids=r.get('effective_record_ids') or r['record_id']
    task(scope,r,scope+'|'+r['model_key'],records=[params[rid] for rid in ids.split(';')])
 assert Counter(t['purpose_scope'] for t in tasks)=={'JX原空能量':1,'32联合跨界':32,'4单项细分':4,'285配置身份':285,'19低温优先':19,'92逐车资格':92,'2208试验口径':2208}
 write('原始询证任务_逐用途来源与企业路由.csv',tasks)
 grouped=defaultdict(list)
 for t in tasks:grouped[t['firm_routing_name']].append(t)
 enterprises=[]
 for firm,ts in sorted(grouped.items()):
  row={'firm_routing_name':firm,'route_is_registered_entity_certification':'0','different_names_not_automatically_merged':'1','distinct_models_in_this_company_packet':str(len({t['model_key'] for t in ts}))}
  for scope in FILES:
   selected=[t for t in ts if t['purpose_scope']==scope]
   row[scope+'_requests']=str(len(selected))
   row[scope+'_models']=str(len({t['model_key'] for t in selected}))
  row.update({'purpose_scopes':';'.join(scope for scope in FILES if any(t['purpose_scope']==scope for t in ts)), 'recommendation_config_ids':';'.join(sorted({t['recommendation_config_id'] for t in ts if t['recommendation_config_id']})), 'source_date_min':min(t['source_observation_date_upper'] for t in ts),'source_date_max':max(t['source_observation_date_upper'] for t in ts),'send_rule':'一家原文/路由企业一份附件，选取本研究要完成的用途；身份与低温同配置版本合并，不逐285条发信','holder_to_route_to':'产品技术/认证、原申报材料保管部门或原检测机构；若主体更名请说明保管/承接依据','verified_contact_lookup':'见优先9家企业_公开询证入口.csv；其余企业入口未知留空，未发送消息'})
  enterprises.append(row)
 write('企业合并_询证总表.csv',enterprises)

 versions={}
 for t in tasks:
  if t['purpose_scope'] not in ['285配置身份','19低温优先']:continue
  k=t['request_key']
  if k not in versions:versions[k]={**t,'needs_cross_catalogue_identity':'0','low_temperature_report_priority':'0'}
  if t['purpose_scope']=='285配置身份':versions[k]['needs_cross_catalogue_identity']='1'
  if t['purpose_scope']=='19低温优先':versions[k]['low_temperature_report_priority']='1'
 assert len(versions)==285 and sum(v['low_temperature_report_priority']=='1' for v in versions.values())==19
 write('企业合并_285配置版本_身份与低温一次询证.csv',list(versions.values()))
 model_groups=defaultdict(list)
 for t in tasks:
  if t['purpose_scope'] not in ['285配置身份','19低温优先']:model_groups[(t['firm_routing_name'],t['model_key'])].append(t)
 models=[]
 for (firm,model),ts in sorted(model_groups.items()):
  row={'firm_routing_name':firm,'model_key':model}
  for scope in ['JX原空能量','32联合跨界','4单项细分','92逐车资格','2208试验口径']:
   row[scope]='1' if any(t['purpose_scope']==scope for t in ts) else '0'
  row.update({'purpose_scopes':';'.join(t['purpose_scope'] for t in ts),'source_versions_json':json.dumps([{k:t[k] for k in ['purpose_scope','source_record_ids','source_observation_date_upper','source_file','source_sha256','firm_route_basis']} for t in ts],ensure_ascii=False,separators=(',',':')),'same_model_is_same_configuration':'0','reply_rule':'按来源/日期/配置版本分别答复；同型号合并附件不等于同配置或逐车资格认证'})
  models.append(row)
 write('企业合并_车型材料用途与来源.csv',models)
 write('输入文件_SHA256.csv',[{'file':str(p.relative_to(AUDIT)),'sha256':sha(p)} for p in input_files])
 assert all(sha(Path(p))==fp for p,fp in before.items())
 assert len({t['firm_routing_name'] for t in tasks if t['purpose_scope'] in ['32联合跨界','4单项细分']})==19
 summary={'initial_scientific_version':'v1.5','source_task_rows':len(tasks),'enterprise_routing_groups':len(enterprises),'company_groups_by_scope':{scope:len({t['firm_routing_name'] for t in tasks if t['purpose_scope']==scope}) for scope in FILES},'original_scope_counts':dict(Counter(t['purpose_scope'] for t in tasks)),'identity_request_rows_after_lowtemp_dedup':len(versions),'lowtemp_flags_inside_285':19,'company_model_packet_rows':len(models),'unresolved_firm_route_rows':0,'entity_register_identity_certified':False,'historical_company_names_not_entity_merged':True,'routing_name_normalization':'NFKC and outer whitespace trim only; original literal and contextual text retained; display normalization is not corporate entity certification','scientific_inputs_mutated':False,'messages_emails_or_forms_sent':0,'final_public_probe_closure_counts_status':'grouping_ready; closure receipt frozen separately in handoff_summary.json','validation':'all 2641 scope rows preserve a source-backed routing name; 92 actual reapplication source records used; SGM routes through explicitly referenced62 target; 19 lowtemp flags are inside285 versions; input hashes unchanged'}
 summary['zero_unresolved_firm_route_interpretation']='All rows have a nonempty source literal/context routing text; it does not certify the original declaring entity or any current legal entity.'
 (OUT/'enterprise_grouping_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
