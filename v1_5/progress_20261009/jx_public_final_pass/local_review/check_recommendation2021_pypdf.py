from pathlib import Path
from pypdf import PdfReader
from decimal import Decimal
import json,hashlib,re,unicodedata
OUT=Path(__file__).parent
SRC=OUT.parent/'raw/recommend2021_10_parameters.pdf'
assert hashlib.sha256(SRC.read_bytes()).hexdigest()=='1bb5883093d638c255f798fb3e2a462f6f027ce241d64721aa575d9dd6cb28b7'
reader=PdfReader(SRC);assert len(reader.pages)==146
def norm(x):return re.sub(r'\s+','',unicodedata.normalize('NFKC',x))
hits=[]
for i,page in enumerate(reader.pages):
 t=page.extract_text(extraction_mode='layout') or ''
 if 'JX6550T-M5BEV' in norm(t):hits.append(i+1)
assert hits==[73]
page=reader.pages[72].extract_text(extraction_mode='layout')
start=page.index('14、江铃汽车股份有限公司')
stop=page.index('15、山东汽车制造有限公司',start)
block=page[start:stop].strip();nb=norm(block)
assert 'JX6550T-M5BEV' in nb and '配置ID:NC010086' in nb
for expected in ['整备质量(kg):2295/2360','30分钟最高车速(km/h):120','续驶里程(km,工况法):293','电池系统能量密度(Wh/kg):L173C01:158.98;L173G01:157.18','22.80']:
 assert expected in nb,expected
assert '总储电量' not in nb and '总能量' not in nb and '动力蓄电池组总质量' not in nb
assert '17.520' not in nb and '17.520' in page[stop:]
row={
 'model_key':'JX6550T-M5BEV','engine':'pypdf layout extraction; independent of parent PyMuPDF',
 'source_pdf':str(SRC),'source_sha256':hashlib.sha256(SRC.read_bytes()).hexdigest(),'pages':146,
 'exact_model_pages_1based':hits,'entry_number_on_page':14,'page_1based':73,
 'entry_start_marker':'14、江铃汽车股份有限公司','entry_end_exclusive_marker':'15、山东汽车制造有限公司',
 'configuration_id':'NC010086','curb_mass_raw':'2295/2360','range_km_raw':'293','range_cycle_raw':'工况法','range_cycle_certified_CLTC':False,
 'max_speed_kmh':'120','30_min_max_speed_kmh':'120','energy_consumption_kWh_per_100km':'22.80',
 'declared_battery_system_energy_density_Wh_per_kg':{'L173C01':'158.98','L173G01':'157.18'},
 'storage_type':'磷酸铁锂电池','battery_total_energy_kWh':None,'battery_mass_kg':None,
 'density_is_recommendation_declaration_not_tax_ratio_proxy':True,
 'battery_energy_17_520_on_same_page_belongs_to_next_entry':'YTQ5043XLCKHPHEV332;配置ID NC009514;第15项',
 'quote':block,
 'tax_48_vs_rec_configuration_bridge_certified':False,
 'capacity_backcalculation_allowed':False,
 'capacity_backcalculation_rejection_reasons':['购置税目录416kg没有对应L173C01/L173G01的分配置质量或正式跨目录配置桥。','推荐目录声明能量密度的检测口径不应无证据当成税目录总能量除以总质量的同义字段。','推荐页对本条没有明确总能量；相邻条的17.520属于另一型号。','型号、整备、续航相同只形成匹配候选，不能认证两电池版本跨目录对应关系。'],
 'invalid_arithmetic_for_diagnostic_only':{
  'assumed_mass_kg':'416','not_valid_capacity_estimates':{
   'L173C01':str(Decimal('416')*Decimal('158.98')/1000),
   'L173G01':str(Decimal('416')*Decimal('157.18')/1000)},
  'late_observed_capacity_kWh':'65.17',
  'note':'只展示未经证明的相乘会产生66.13568或65.38688；这些不是可采用的容量值或容量边界，也不支持把后来的65.17回填。'},
 'science_values_modified':False,'network_requests':0,
 'checks_passed':['source_sha_matches_parent','all146_pages_exact_model_only73','entry14_exact_model_and_config','range_and_curb_match','two_density_types_confirmed','no_target_battery_energy_or_mass_field','adjacent_17_520_excluded'],
}
(OUT/'recommend2021_10_page73_pypdf.txt').write_text(page)
(OUT/'recommend2021_10_JX_entry14_pypdf.txt').write_text(block+'\n')
(OUT/'recommend2021_10_JX_independent_result.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'checks_passed':len(row['checks_passed']),'exact_model_pages':hits,'configuration_id':row['configuration_id'],'battery_energy':None,'battery_mass':None,'backcalculation_allowed':False},ensure_ascii=False))
