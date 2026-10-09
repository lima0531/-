from pathlib import Path
import json,re,html,csv,hashlib,datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).parent

def clean(s):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]*>',' ',s))).strip()
def filemeta(name):
 p=ROOT/name;r=json.loads(p.with_name(p.stem+'.receipt.json').read_text())
 assert hashlib.sha256(p.read_bytes()).hexdigest()==r['sha256']
 return {'file':str(p),'sha256':r['sha256'],'source_url':r['request_url'],'retrieved_at_utc':r['retrieved_at_utc'],'retrieved_at_shanghai':datetime.datetime.fromisoformat(r['retrieved_at_utc']).astimezone(ZoneInfo('Asia/Shanghai')).isoformat(),'http_status':r['http_status']}

taxraw=json.loads((ROOT/'tax_first_final_query.html').read_text())
records=taxraw['searchResultAll']['searchTotal'];assert len(records)==1
first=records[0]
assert first['govDoc']['docYear']=='2014' and first['govDoc']['docNo']=='54'
assert re.sub(r'\s+','',clean(first['title']))=='免征车辆购置税的新能源汽车车型目录（第一批）'
assert first['pubDate']=='2014-08-27 00:00:00' and first['cwrq']=='2014-08-27 00:00:00'
page=(ROOT/'first_batch_primary_registered_page.html').read_text()
assert '成文日期：2014-08-27' in page and '2014年第54号' in page and '自2014年9月1日起开始实施' in page
page_meta=re.search(r'<meta\s+name="PubDate"\s+content="([^"]+)"',page)[1]
first_metadata={
 'document_number':first['govDoc']['docNum'],'title':re.sub(r'\s+','',clean(first['title'])),'raw_index_title':first['title'],
 'registered_public_date_in_official_index':'2014-08-27',
 'registered_public_date_definition':'国家税务总局政策法规库官方查询记录中名为pubDate的登记字段；不认证历史实际首次公开时间',
 'raw_official_index_fields':{k:first.get(k) for k in ['pubDate','cwrq','fwrq','pubName','siteName','url','snapshotUrl']},
 'raw_official_index_document_number':first['govDoc'],
 'raw_official_index_field_locator':'$.searchResultAll.searchTotal[0].pubDate（登记字段），cwrq为另一个成文日期字段',
 'page_visible_signed_date':'2014-08-27','page_visible_signed_date_locator':'HTML line 294，标签成文日期；不是可见发布日期',
 'page_visible_implementation_date':'2014-09-01','page_visible_implementation_date_locator':'HTML line 330，正文自2014年9月1日起开始实施',
 'page_html_metadata_PubDate':page_meta,'page_html_metadata_locator':'HTML line 19，meta name=PubDate',
 'page_index_pubdate_difference_retained':True,
 'page_visible_historical_publication_label_found':bool(re.search(r'发布日期|发布时间',page)),
 'registered_layer_evidence_obtained':True,'historical_actual_first_publication_date':None,
 'full_historical_first_online_time_verified':False,
 'do_not_infer_first_release_from_signed_or_effective_or_pdf_creation_dates':True,
 'official_query_evidence':filemeta('tax_first_final_query.html'),
 'official_primary_page_evidence':filemeta('first_batch_primary_registered_page.html'),
 'actual_official_attachment_hrefs':first['appendix'],
 'scientific_dates_modified':False,
}
(ROOT/'first_batch_registered_metadata.json').write_text(json.dumps(first_metadata,ensure_ascii=False,indent=2))

q=json.loads((ROOT/'standard_registry_query.html').read_text());assert q['total']==1 and len(q['rows'])==1
qr=q['rows'][0]
assert clean(qr['C_STD_CODE'])=='GB / T 18386.1-2021' or re.sub(r'\s+','',clean(qr['C_STD_CODE']))=='GB/T18386.1-2021'
text=(ROOT/'standard_registry_detail.html').read_text();fields={}
for m in re.finditer(r'<dt\b[^>]*>(.*?)</dt>\s*<dd\b[^>]*>(.*?)</dd>',text,re.S):fields[clean(m[1])]=clean(m[2])
assert fields['标准号']=='GB/T 18386.1-2021' and fields['发布日期']==qr['ISSUE_DATE']=='2021-03-09' and fields['实施日期']==qr['ACT_DATE']=='2021-10-01'
assert qr['STATE']=='现行' and 'GB/T 18386-2017' in fields['部分代替标准']
state_start=text.index('标准状态');basic_start=text.index('基础信息');relations=clean(text[state_start:basic_start])
assert '部分代替' in relations and '现行' in relations
assert '被以下标准替代' not in relations
oldtext=(ROOT/'standard_replaced_2017_detail.html').read_text();reciprocal='GB/T 18386.1-2021' in oldtext and '（部分代替）' in oldtext
assert reciprocal
standard_metadata={
 'standard_number':'GB/T 18386.1-2021','standard_name':qr['C_C_NAME'],
 'official_registry_id':qr['id'],'official_registered_publication_date':qr['ISSUE_DATE'],
 'official_registered_implementation_date':qr['ACT_DATE'],'official_registered_current_status':qr['STATE'],
 'registered_current_status_observation_date_shanghai':filemeta('standard_registry_detail.html')['retrieved_at_shanghai'],
 'registered_replaces_standard':'GB/T 18386-2017','registered_replaces_relation':'部分代替',
 'registered_replaced_by_standards_displayed':[],
 'registered_replaced_by_observation':'本次完整标准详情页标准状态关系图未列出后继标准；当前登记状态为现行。仅认证本次登记观察，不声称未来不被替代或所有外部记录绝对不存在。',
 'registry_required_fields_obtained':['标准号','标准名称','发布日期','实施日期','查询时登记状态','直接部分替代关系'],
 'query_raw_row':qr,'detail_raw_fields':{k:fields[k] for k in ['标准号','发布日期','实施日期','部分代替标准']},
 'detail_standard_state_section_text':relations,
 'detail_field_line_locations':{'current_status':[956,1168],'publication_date':[1111,1191],'implementation_date':[1112,1198],'partial_replaces':[1127,1136,1141,1206,1208]},
 'query_evidence':filemeta('standard_registry_query.html'),'detail_evidence':filemeta('standard_registry_detail.html'),
 'predecessor_reciprocal_relation_verified':reciprocal,'predecessor_evidence':filemeta('standard_replaced_2017_detail.html'),
 'matches_prior_policy_implementation_date':True,
 'standard_fulltext_or_model_specific_low_temperature_reports_not_required_for_this_metadata_completion':True,
 'science_data_modified':False,
}
(ROOT/'standard_registered_metadata.json').write_text(json.dumps(standard_metadata,ensure_ascii=False,indent=2))

attempts=[]
for p in sorted(ROOT.glob('*.receipt.json')):
 r=json.loads(p.read_text());attempts.append({'receipt_file':str(p),'requested_url':r['request_url'],'retrieved_at_utc':r['retrieved_at_utc'],'status':r['status'],'http_status':r.get('http_status',''),'bytes':r.get('bytes',''),'sha256':r.get('sha256',''),'purpose':r['purpose'],'error':r.get('error','')})
cols=list(attempts[0])
with (ROOT/'尝试结果.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(attempts)
fields=[
 {'topic':'第一批2014年第54号','field':'主管法规库pubDate登记日期','value':'2014-08-27','status':'本轮已取得','evidence':'first_batch_registered_metadata.json','remaining_required':'0','nonblocking_for_2023_2024_analysis':'1','user_private_material_needed':'0','scope':'官方索引登记层；原页meta另为2026-06-02，不认证历史首次公开'},
 {'topic':'第一批2014年第54号','field':'历史实际首次公开日/时刻','value':'','status':'未认证；归档边界','evidence':'first_batch_registered_metadata.json','remaining_required':'0','nonblocking_for_2023_2024_analysis':'1','user_private_material_needed':'0','scope':'落款、实施日、PDF创建日及现存索引登记日均不能单独认证全球历史首次上线；本轮到此收敛'},
 {'topic':'GB/T18386.1-2021','field':'官方登记发布日期','value':'2021-03-09','status':'本轮已取得','evidence':'standard_registered_metadata.json','remaining_required':'0','nonblocking_for_2023_2024_analysis':'1','user_private_material_needed':'0','scope':'官方查询记录与完整标准详情页一致'},
 {'topic':'GB/T18386.1-2021','field':'官方登记实施日期','value':'2021-10-01','status':'与已核政策交叉闭合','evidence':'standard_registered_metadata.json','remaining_required':'0','nonblocking_for_2023_2024_analysis':'1','user_private_material_needed':'0','scope':'与2021年第13号公告正文一致'},
 {'topic':'GB/T18386.1-2021','field':'查询时官方登记状态','value':'现行','status':'本轮已取得','evidence':'standard_registered_metadata.json','remaining_required':'0','nonblocking_for_2023_2024_analysis':'1','user_private_material_needed':'0','scope':'2026-10-09上海时间本次查询观察，不外推未来状态'},
 {'topic':'GB/T18386.1-2021','field':'直接替代关系','value':'部分代替GB/T18386-2017','status':'双方登记页交叉验证','evidence':'standard_registered_metadata.json','remaining_required':'0','nonblocking_for_2023_2024_analysis':'1','user_private_material_needed':'0','scope':'不能改称完全代替，也不将18386.2-2022当成18386.1-2021后继'},
 {'topic':'GB/T18386.1-2021','field':'被代替/后继标准登记观察','value':'本次详情页未列出后继标准','status':'当前关系图观察已记录','evidence':'standard_registered_metadata.json','remaining_required':'0','nonblocking_for_2023_2024_analysis':'1','user_private_material_needed':'0','scope':'登记关系图无后继节点；不是对未来或一切外部记录的绝对不存在断言'},
]
with (ROOT/'剩余字段与本轮闭合.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(fields[0]));w.writeheader();w.writerows(fields)
summary={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'first_batch_registered_layer_evidence_obtained':True,'first_batch_registered_date_candidate':'2014-08-27','first_batch_original_historical_first_publication_verified':False,'standard_registry_core_fields_completed':True,'standard_partial_replaces':'GB/T18386-2017','standard_successor_relation_as_of_query':'not_listed_on_current_detail','new_attempts':len(attempts),'new_http_200_responses':sum(r['http_status']==200 for r in attempts),'full_first_online_unknown_is_not_a_current_analysis_blocker':True,'remaining_required_public_metadata_fields_for_current_analysis':0,'user_private_materials_requested_for_this_archive_task':False,'science_inputs_or_dates_modified':False,'preferred_definition':'Registered fields are current authoritative record observations, not a reconstruction of first historical online timestamps.'}
(ROOT/'final_public_archive_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
