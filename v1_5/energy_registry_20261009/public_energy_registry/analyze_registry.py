#!/usr/bin/env python3
"""Verify complete saved registry views and join exact models into read-only evidence."""
import csv
import hashlib
import json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
AUDIT=ROOT.parents[1]
CYCLE=AUDIT/'round9/public_cycle/2208型号_整篇工况补证结果_只读旁表.csv'
SCOPES=AUDIT/'round8/final_gap_status/条件需求_型号级交叉台账.csv'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def csv_read(path):return list(csv.DictReader(path.open(encoding='utf-8-sig')))
def csv_write(name,rows,fields):
 with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def js(value):return json.dumps(value,ensure_ascii=False,sort_keys=True)

def main():
 assert sha(CYCLE)=='a438f95dd4e0f3cf1ada1d27bf53716896d13fceaad2b0e6f424750a84c20d21'
 core_rows=csv_read(CYCLE);core={x['model_key'] for x in core_rows}
 assert len(core_rows)==len(core)==2208 and 'JX6550T-M5BEV' not in core
 scopes=csv_read(SCOPES);targets={x['model_key'] for x in scopes}|core|{'JX6550T-M5BEV','GTM6470BFEBEV','CC7000CG00FBEV'}
 by_model=defaultdict(lambda:defaultdict(list));duplicate_rows=[];trim_candidates=[];library_summary={};target_records=[];category_conflicts=[]
 for lib in ['new','old']:
  cp=json.loads((ROOT/(lib+'_checkpoint.json')).read_text())
  if cp['completed']:assert cp['rows']==cp['reported_total'] and cp['pages_validated']==cp['reported_pages']
  assert cp['pages_validated']==len(cp['source_page_files']) and cp['rows']<=cp['reported_total']
  all_ids=defaultdict(list);full_rows=Counter();pages=[];row_count=0
  for page_number,rel in enumerate(cp['source_page_files'],1):
   path=ROOT/rel;rp=path.with_name(path.name.replace('_response.json','_receipt.json'))
   receipt=json.loads(rp.read_text());assert receipt['http_status']==200 and receipt['tls_verified']
   assert receipt['file']==rel and receipt['bytes']==path.stat().st_size and receipt['sha256']==sha(path)
   assert receipt['request_json']['currentPage']==page_number
   d=json.loads(path.read_bytes());assert d['result']==(200 if lib=='new' else 1)
   info=d['info'];assert info['currentPage']==page_number and info['totalSize']==cp['reported_total'] and info['pages']==cp['reported_pages']
   pages.append({'page':page_number,'file':rel,'receipt':rp.relative_to(ROOT).as_posix(),'sha256':sha(path),'rows':len(info['list']),'observed_utc':receipt['observed_utc']})
   for index,item in enumerate(info['list']):
    if item.get('reportType')!='3' or (lib=='new' and item.get('energyType')!='8'):
     category_conflicts.append({'library':lib,'model_raw':item.get('vehicleModel') or item.get('vehicleNumber'),'report_type_raw':item.get('reportType'),'energy_type_raw':item.get('energyType'),'source_file':rel,'json_pointer':f'/info/list/{index}','not_interpreted_as_certified_BEV':True})
    model=item.get('vehicleModel') if lib=='new' else item.get('vehicleNumber')
    identity=item.get('uuid') if lib=='new' else item.get('applyId')
    assert identity
    row_hash=hashlib.sha256(js(item).encode()).hexdigest();full_rows[row_hash]+=1;all_ids[identity].append((row_hash,item))
    if model not in targets:
     if isinstance(model,str) and model.strip() in core:trim_candidates.append({'library':lib,'raw_model':model,'candidate_target':model.strip(),'source_file':rel,'json_pointer':f'/info/list/{index}','not_counted_as_exact_match':True})
     continue
    row={'library':lib,'record_key':lib+':'+identity+':'+row_hash,'source_occurrence':f'{lib}:{page_number}:{index}','model_key':model,'in_core_2208':model in core,'stable_id_raw':identity,'record_number_raw':item.get('recordNumber') if lib=='new' else item.get('uniqId'),'raw_full_row_sha256':row_hash,'source_file':rel,'json_pointer':f'/info/list/{index}','source_sha256':sha(path),'raw_record':item}
    target_records.append(row);by_model[model][lib].append(row)
   row_count+=len(info['list'])
  assert row_count==cp['rows']
  for identity,values in all_ids.items():
   if len(values)>1:
    items=[x[1] for x in values];keys=set().union(*(set(x) for x in items));different=[k for k in sorted(keys) if len({js(x.get(k)) for x in items})>1]
    duplicate_rows.append({'library':lib,'stable_id_raw':identity,'raw_occurrences':len(values),'distinct_full_rows':len({x[0] for x in values}),'model_keys_json':js(sorted({str(x.get('vehicleModel') or x.get('vehicleNumber')) for x in items})),'different_fields_json':js(different),'abandon_times_raw_json':js(sorted({str(x.get('abandonTime')) for x in items}))})
  library_summary[lib]={'completed':cp['completed'],'stop_reason':cp['stop_reason'],'reported_total':cp['reported_total'],'reported_pages':cp['reported_pages'],'raw_rows_observed':row_count,'distinct_stable_ids':len(all_ids),'distinct_full_rows':len(full_rows),'repeated_stable_id_occurrences':row_count-len(all_ids),'identical_full_row_repeat_occurrences':sum(n-1 for n in full_rows.values()),'pages_validated':len(pages),'all_pages_total_and_row_count_reconciled':cp['completed'],'observed_pages_count_and_hash_verified':True,'earliest_page_observed_utc':min(x['observed_utc'] for x in pages),'latest_page_observed_utc':max(x['observed_utc'] for x in pages),'normal_public_filter':cp['filters'],'atomic_snapshot':False,'pages':pages}
 with (ROOT/'精确目标_全字段记录_只读旁表.jsonl').open('w') as f:
  for row in target_records:f.write(js(row)+'\n')
 def model_row(model):
  libs=by_model[model];new=[x['raw_record'] for x in libs['new']];old=[x['raw_record'] for x in libs['old']]
  codes=sorted({str(c.get('workConditionType')) for x in old for c in (x.get('workConditionVos') or []) if c.get('workConditionType') is not None})
  return {'model_key':model,'in_core_2208':model in core,'new_source_view_complete':library_summary['new']['completed'],'old_source_view_complete':library_summary['old']['completed'],'new_raw_rows':len(new),'new_distinct_stable_ids':len({x.get('uuid') for x in new}),'old_raw_rows':len(old),'old_distinct_stable_ids':len({x.get('applyId') for x in old}),'visible_match_state':'both_observed' if new and old else 'new_observed' if new else 'old_observed' if old else 'no_match_in_pages_observed','new_standard_codes_raw_json':js(sorted({str(x.get('testBasisStandard')) for x in new if x.get('testBasisStandard') is not None})),'old_cycle_codes_raw_json':js(codes),'old_public_times_raw_json':js(sorted({str(x.get('publicTime')) for x in old if x.get('publicTime')})),'new_issue_dates_raw_json':js(sorted({str(x.get('issueDate')) for x in new if x.get('issueDate')})),'new_migration_notes_raw_json':js(sorted({str(x.get('overtimeCause')) for x in new if x.get('overtimeCause')})),'new_abandon_times_raw_json':js(sorted({str(x.get('abandonTime')) for x in new if x.get('abandonTime')})),'historical_public_availability_certified':False,'same_tax_configuration_identity_certified':False,'can_replace_frozen_scientific_input':False,'scope_note':'指定公开energyType8/fuelType8筛选视图的已取得页精确匹配；不认证全行纯电。完整标志false时未命中未知，不得称零命中；旧工况仅原代码，不映射。'}
 core_table=[model_row(x['model_key']) for x in core_rows]
 extra_table=[model_row(m) for m in sorted(targets-core)]
 fields=list(core_table[0]);csv_write('2208型号_两库完整视图精确匹配.csv',core_table,fields);csv_write('非2208_其他用途与正对照精确匹配.csv',extra_table,fields)
 csv_write('重复标识_状态版本差异_不得删除.csv',duplicate_rows,['library','stable_id_raw','raw_occurrences','distinct_full_rows','model_keys_json','different_fields_json','abandon_times_raw_json'])
 csv_write('首尾空白差异候选_不计精确命中.csv',trim_candidates,['library','raw_model','candidate_target','source_file','json_pointer','not_counted_as_exact_match'])
 csv_write('筛选视图_响应分类冲突_原行保留.csv',category_conflicts,['library','model_raw','report_type_raw','energy_type_raw','source_file','json_pointer','not_interpreted_as_certified_BEV'])
 state_counts=Counter(x['visible_match_state'] for x in core_table)
 catc={x['model_key'] for x in core_table if 'CATC' in json.loads(x['old_cycle_codes_raw_json'])}
 nedc={x['model_key'] for x in core_table if 'NEDC' in json.loads(x['old_cycle_codes_raw_json'])}
 lowtemps=[]
 target_new=[x for x in target_records if x['library']=='new']
 for row in target_new:
  r=row['raw_record'];report_fields={k:v for k,v in r.items() if ('reportnum' in k.lower() or 'specialscene' in k.lower() or 'thermy' in k.lower() or 'thermia' in k.lower()) and v is not None}
  if any(v for k,v in report_fields.items() if 'reportnum' in k.lower()):lowtemps.append({'model_key':row['model_key'],'record_number_raw':row['record_number_raw'],'report_fields_json':js(report_fields),'source_file':row['source_file'],'json_pointer':row['json_pointer'],'model_specific_low_temperature_report_certified':False})
 csv_write('非空报告引用线索_尚未认证.csv',lowtemps,['model_key','record_number_raw','report_fields_json','source_file','json_pointer','model_specific_low_temperature_report_certified'])
 summary={'generated_utc':datetime.now(timezone.utc).isoformat(),'scientific_version':'v1.5','libraries':library_summary,'core_2208_models':2208,'core_match_states':dict(state_counts),'core_models_with_any_visible_exact_record':sum(x['new_raw_rows']>0 or x['old_raw_rows']>0 for x in core_table),'core_models_with_old_cycle_code_observed':sum(x['old_cycle_codes_raw_json']!='[]' for x in core_table),'core_new_raw_rows_matched':sum(x['new_raw_rows'] for x in core_table),'core_old_raw_rows_matched':sum(x['old_raw_rows'] for x in core_table),'all_target_model_universe':len(targets),'non_core_models_in_separate_table':len(extra_table),'all_target_raw_rows_preserved':len(target_records),'whitespace_only_candidate_rows_not_counted':len(trim_candidates),'new_nonempty_report_reference_candidate_rows':len(lowtemps),'response_category_conflict_rows':len(category_conflicts),'jx_in_core_2208':False,'numeric_ready_delta':0,'unmarked_frozen_cycle_list_closed':0,'battery_energy_gap_closed':0,'issue_date_semantics_not_assumed':True,'raw_cycle_codes_not_mapped':True,'metadata_hits_do_not_imply_frozen_comparability':True,'unmatched_only_describes_observed_public_filtered_views':True,'cycle_input_sha256':sha(CYCLE),'purpose_scopes_sha256':sha(SCOPES)}
 summary['old_cycle_code_model_sets']={'CATC':len(catc),'NEDC':len(nedc),'both_CATC_and_NEDC':len(catc&nedc),'any_CATC_or_NEDC':len(catc|nedc),'codes_are_raw_and_not_standard_mappings':True}
 (ROOT/'registry_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(js({k:summary[k] for k in ['core_2208_models','core_match_states','core_models_with_any_visible_exact_record','core_models_with_old_cycle_code_observed','all_target_raw_rows_preserved','new_nonempty_report_reference_candidate_rows']}))
if __name__=='__main__':main()
