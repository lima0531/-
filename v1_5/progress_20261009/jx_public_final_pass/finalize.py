from pathlib import Path
from urllib.parse import urljoin
import re,html,json,csv,hashlib,datetime
ROOT=Path(__file__).parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
primary=ROOT/'primary2021_10_announcement.html'
s=primary.read_text()
dated=[]
for i,line in enumerate(s.splitlines(),1):
    if any(x in line for x in ['发布日期：','成文日期：','id="con_time"','name="PubDate"']):
        dated.append({'line_1based':i,'html_original':line.strip()})
assert any('发布日期' in x['html_original'] and '2021-11-05' in x['html_original'] for x in dated)
links=[]
base='https://www.miit.gov.cn/zwgk/zcwj/wjfb/gg/art/2021/art_1b29d7093e9c45a6ab41fee28f16df0e.html'
for href,label in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',s,re.S|re.I):
    if any(x in href.lower() for x in ['.pdf','.doc']):
        links.append({'href_original':href,'label_original':html.unescape(re.sub('<[^>]+>','',label)).strip(),'url':urljoin(base,href)})
(ROOT/'recommendation_primary_date_and_link_evidence.json').write_text(json.dumps({'primary_url':base,'primary_sha256':digest(primary),'registered_public_date':'2021-11-05','signed_date':'2021-11-05','html_date_lines':dated,'meta_pubdate_conflict_kept':True,'global_first_online_timestamp_verified':False,'real_attachment_anchors':links},ensure_ascii=False,indent=2)+'\n')
independent=json.loads((ROOT/'local_review/recommend2021_10_JX_independent_result.json').read_text())
rows=[{'source':'mf_batch48.doc','public_date':'2021-11-05','model_key':'JX6550T-M5BEV','configuration_id':'','observed_battery_total_energy_kWh':'','source_sha256':'ee5aa19736215cfcb3b76ffff90bcd0d9108c61758ccb756f7d4ad17e75a835c','acceptance':'原单元格真实空；未闭合','configuration_bridge_to_tax48_certified':'0'},
{'source':'recommend2021_10_parameters.pdf page73 entry14','public_date':'2021-11-05','model_key':'JX6550T-M5BEV','configuration_id':'NC010086','observed_battery_total_energy_kWh':'','source_sha256':'1bb5883093d638c255f798fb3e2a462f6f027ce241d64721aa575d9dd6cb28b7','acceptance':'公告前精确型号候选，但仅声明两电池密度，无总能量/质量/正式配置桥，不能代填','configuration_bridge_to_tax48_certified':'0'},
{'source':'cat_batch1.doc','public_date':'2023-12-26','model_key':'JX6550T-M5BEV','configuration_id':'','observed_battery_total_energy_kWh':'65.17','source_sha256':'2497c1bf3f3ffb02166f358621f18fa2288e6c5b8a2d36177483ffd5bb1cf655','acceptance':'晚于冻结日2023-12-10；不能回填','configuration_bridge_to_tax48_certified':'0'},
{'source':'第40批更正（独立本地复核排除）','public_date':'','model_key':'JX6570T-M5BEV','configuration_id':'','observed_battery_total_energy_kWh':'65.17','source_sha256':'','acceptance':'型号不同；不能移用','configuration_bridge_to_tax48_certified':'0'}]
with (ROOT/'候选证据与不能关闭字段的原因.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
enterprise=[]
for n in ['exact_model','trade_name','energy_candidate_text']:
    p=ROOT/'enterprise'/f'{n}.json';rec=json.loads(Path(str(p)+'.receipt.json').read_text());j=json.loads(p.read_text()) if p.exists() else {}
    enterprise.append({'query_record':n,'request_receipt':str(Path(str(p)+'.receipt.json').relative_to(ROOT)),'api_result_code':j.get('code'),'result_totals':{k:v.get('total') for k,v in j.get('data',{}).items() if isinstance(v,dict)},'total':j.get('data',{}).get('total'),'result':j,'accepted_configuration_energy_evidence':False})
(ROOT/'enterprise_native_search_review.json').write_text(json.dumps({'homepage_sha256':digest(ROOT/'enterprise_home.html'),'search_page_sha256':digest(ROOT/'enterprise_search.html'),'frontend_base_url_source':'raw/jmc_common.js literal https://sale-api.jmc.com.cn/api','frontend_endpoint_source':'raw/jmc_common.js literal /keywords/search','frontend_query_parameter_source':'raw/jmc_search.js getList -> keywords:this.searchvalue','queries':enterprise,'boundary':'公开官网原生检索可运行；0结果和2017特顺上市历史条目不证明企业档案不存在，也不提供精确配置能量。'},ensure_ascii=False,indent=2)+'\n')
receipts=[]
for p in sorted(ROOT.rglob('*.receipt.json')):
    rec=json.loads(p.read_text());rec['receipt_relative_path']=str(p.relative_to(ROOT));receipts.append(rec)
(ROOT/'network_receipts_manifest.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
summary={'model_key':'JX6550T-M5BEV','field_requested':'battery_energy_raw','unit':'kWh','cutoff':'2023-12-10','field_closed':False,'validated_before_cutoff_battery_energy_candidate_count':0,'official_new_candidate':{k:independent[k] for k in ['source_pdf','source_sha256','page_1based','entry_number_on_page','configuration_id','range_km_raw','curb_mass_raw','declared_battery_system_energy_density_Wh_per_kg','battery_total_energy_kWh','battery_mass_kg','tax_48_vs_rec_configuration_bridge_certified']},'new_candidate_primary_public_date':'2021-11-05','scientific_data_modified':False,'native_miit_queries':5,'native_enterprise_queries':3,'new_recommendation_originals_downloaded':2,'next_step_holder':'江铃汽车股份有限公司技术/认证或申报部门、原检测机构','needed_material':'第48批申报配置对应的原始申报或检测报告，总能量(kWh)、电池型号/供应商与版本、车辆/申报配置标识、报告/申报日期；如联系推荐配置NC010086，须说明L173C01与L173G01并提供与购置税第48批对应关系','time_requirement':'能证明2023-12-10以前已有效/公开的对应历史配置材料；新报告不得无证据倒推历史','excluded_substitutes':['2023-12-26减免首批65.17kWh','JX6570T-M5BEV第40批更正65.17kWh','相邻车型17.520kWh','416kg乘推荐目录两种密度倒算容量','仅型号、续航及整备相同的跨目录近似连接'],'scope_boundary':'有界复查官方原生检索、同次推荐目录及参数原件、企业官网原生检索、既有97份目录和勘误缓存；不声称穷尽互联网所有公开页面。','completed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(ROOT/'jx_public_final_pass_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
