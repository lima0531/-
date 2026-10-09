"""Read-only independent structural count of exemption batch 64.
Enumerate Word XML physical rows and MS-DOC main-story cell boundaries before
comparing with any existing extracted model list. All outputs are written to round6.
"""
import csv,hashlib,json,re,sys,unicodedata,zipfile
from pathlib import Path
from xml.etree import ElementTree as E
R=Path(__file__).resolve().parent
SOURCE=Path('/workspace/purchase_tax_audit/round5/originals/mf_batch64.doc')
DOCX=Path('/workspace/purchase_tax_audit/round5/batch64/mf_batch64.docx')
OLD=Path('/workspace/purchase_tax_audit/round5/batch64/第64批_纯电动乘用车独立全表40行.csv')
PARAMS=Path('/workspace/purchase_tax_audit/round5/reconstruction/data_v1_5/研究数据/参数版本_原值与计算代理.csv')
sys.path.insert(0,'/workspace/purchase_tax_audit/round3/archive');from word_piece_text import extract
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):return re.sub(r'\s+','',unicodedata.normalize('NFKC',s)).upper()
def write(name,rows):
 with (R/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def para(p):return ''.join(x.text or '' for x in p.findall('.//w:t',NS))
before={str(p):sha(p) for p in [SOURCE,DOCX,OLD,PARAMS]}
with zipfile.ZipFile(DOCX) as z:xml=z.read('word/document.xml');document=E.fromstring(xml)
(R/'word_document.xml').write_bytes(xml)
body=document.find('w:body',NS);table_index=-1;structure=[];table_rows=[];scope=''
for body_index,item in enumerate(body):
 tag=item.tag.rsplit('}',1)[-1]
 if tag=='p':
  text=para(item);structure.append({'body_index_0based':body_index,'node_kind':'paragraph','table_index_0based':'','text_verbatim':text})
  if text in ['一、纯电动汽车','二、插电式混合动力汽车','三、燃料电池汽车']:scope=text
  if text.startswith('（') and text.endswith('）') is False and ('乘用车' in text or '客车' in text):scope+= ' / '+text
 elif tag=='tbl':
  table_index+=1;rows=[]
  for row_index,tr in enumerate(item.findall('w:tr',NS)):
   tcs=tr.findall('w:tc',NS);cells=['\n'.join(para(p) for p in tc.findall('w:p',NS)) for tc in tcs]
   props=[]
   for tc in tcs:
    span=tc.find('w:tcPr/w:gridSpan',NS);vm=tc.find('w:tcPr/w:vMerge',NS)
    props.append({'gridSpan':span.get('{'+NS['w']+'}val') if span is not None else '1','vMerge':vm.get('{'+NS['w']+'}val','continue') if vm is not None else ''})
   typ='表头' if cells[0]=='序号' and cells[2]=='车辆型号' else '数据行'
   row={'body_index_0based':body_index,'table_index_0based':table_index,'physical_row_0based':row_index,'row_type':typ,'physical_cell_count':len(cells),'seq_cell_raw':cells[0],'firm_raw':cells[1],'model_raw':cells[2],'name_raw':cells[3],'range_raw':cells[4],'curb_mass_raw':cells[5],'battery_mass_raw':cells[6],'battery_energy_raw':cells[7],'remark_raw':cells[8],'cell_values_json':json.dumps(cells,ensure_ascii=False),'cell_properties_json':json.dumps(props,ensure_ascii=False),'repeat_header_xml_flag':str(int(tr.find('w:trPr/w:tblHeader',NS) is not None))}
   rows.append(row)
  table_rows.append(rows);structure.append({'body_index_0based':body_index,'node_kind':'table','table_index_0based':table_index,'text_verbatim':'物理行 '+str(len(rows))+'；当前前置标题 '+scope})
# Scope is determined from document headings and table order, never a model list.
assert structure[5]['text_verbatim']=='一、纯电动汽车' and structure[6]['text_verbatim']=='（一）乘用车'
assert structure[7]['node_kind']=='table' and structure[7]['table_index_0based']==0
assert structure[8]['node_kind']=='paragraph' and structure[8]['text_verbatim'].startswith('勘误：')
assert structure[10]['text_verbatim']=='（二）客车' and structure[11]['table_index_0based']==1
passenger_xml=table_rows[0];bus_xml=table_rows[1]
assert len(passenger_xml)==41 and sum(r['row_type']=='表头' for r in passenger_xml)==1
assert len(bus_xml)==8 and sum(r['row_type']=='表头' for r in bus_xml)==1
assert all(r['physical_cell_count']==9 for r in passenger_xml+bus_xml)
assert all(r['model_raw'] and r['range_raw'] for r in passenger_xml[1:])
write('docx_body_node_structure.csv',structure)
write('docx_table0_all_physical_rows_41.csv',passenger_xml)
write('docx_table1_all_physical_rows_8.csv',bus_xml)
erratum=structure[8]['text_verbatim'];(R/'passenger_erratum_verbatim.txt').write_text(erratum+'\n')
# MS-DOC main-story reader: FIB/CLX bounded extraction keeps all cell terminators.
main,proof=extract(SOURCE);assert proof['source_sha256']==before[str(SOURCE)]
(R/'cfb_main_story_independent.txt').write_text(main);(R/'cfb_main_story_reader_proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
start=main.index('（一）乘用车');end=main.index('（二）客车',start);section=main[start:end];assert section.count('序号')==1
cells=main.split('\t');header=[c.strip() for c in cells[:9]];header[0]='序号'
assert header==['序号','汽车生产企业名称','车辆型号','通用名称','纯电动续驶里程(km)','整车整备质量(kg)','动力蓄电池组总质量(kg)','动力蓄电池组总能量(kWh)','备注']
assert cells[9]=='';raw_rows=[];position=10
# Continue until a prose/heading boundary, requiring a complete 9-cell record +
# MS-DOC row-ending marker. No known-model membership or target count filters.
while position<len(cells):
 first=cells[position]
 if '勘误：' in first or '（二）客车' in first:break
 chunk=cells[position:position+10];assert len(chunk)==10 and chunk[9]==''
 assert chunk[0]=='' and chunk[2] and chunk[4],(position,chunk)
 raw_rows.append({'independent_row_1based':len(raw_rows)+1,'source_start_cell_0based':position,'model_cell_0based':position+2,'seq_cell_raw':chunk[0],'firm_raw':chunk[1],'model_raw':chunk[2],'name_raw':chunk[3],'range_raw':chunk[4],'curb_mass_raw':chunk[5],'battery_mass_raw':chunk[6],'battery_energy_raw':chunk[7],'remark_raw':chunk[8]});position+=10
assert position==410 and len(raw_rows)==40
assert cells[position].startswith(erratum) and '（二）客车' in cells[position]
fields=['seq_cell_raw','firm_raw','model_raw','name_raw','range_raw','curb_mass_raw','battery_mass_raw','battery_energy_raw','remark_raw']
assert [[norm(r[k]) for k in fields] for r in raw_rows]==[[norm(r[k]) for k in fields] for r in passenger_xml[1:]]
write('cfb_passenger_data_rows_independent_40.csv',raw_rows)
write('cfb_cells_398_to_422_boundary_verbatim.csv',[{'cell_0based':i,'raw_value_verbatim':cells[i],'classification':'第40条乘用车列入记录' if 400<=i<=409 else ('独立勘误段落＋客车小节标题＋客车表头序号' if i==410 else ('客车表头' if 411<=i<=419 else '边界附近原文'))} for i in range(398,423)])
# Only after both independent enumerations are complete, compare retained output.
old=list(csv.DictReader(OLD.open(encoding='utf-8-sig')));old_key=next(k for k in ['model_key','model_raw','车辆型号'] if k in old[0]);oldkeys={norm(x[old_key]) for x in old};rawkeys={norm(x['model_raw']) for x in raw_rows}
missing=sorted(rawkeys-oldkeys);extra=sorted(oldkeys-rawkeys);assert len(old)==40 and not missing and not extra
assert 'SGM6500BEBEV' not in rawkeys and 'SGM6500BEBEV' in erratum
# Focused row/field reconciliation only for batch64: 40 listing records and one
# original partial-field correction record. No project-wide scientific rerun.
parameters=[x for x in csv.DictReader(PARAMS.open(encoding='utf-8-sig')) if x['system']=='免征目录' and x['source_batch']=='64']
listing=[x for x in parameters if x['observation_kind']=='目录列入'];corrections=[x for x in parameters if x['observation_kind']=='仅续航文字勘误']
assert len(parameters)==41 and len(listing)==40 and len(corrections)==1
assert {norm(x['model_raw']) for x in listing}==rawkeys
by_original={norm(x['model_raw']):x for x in raw_rows};by_existing={norm(x['model_raw']):x for x in old};comparison=[]
for x in listing:
 original=by_original[norm(x['model_raw'])];retained=by_existing[norm(x['model_raw'])]
 for original_field,old_field,param_field in [('model_raw','model_raw','model_raw'),('name_raw','trade_name_raw','trade_name_raw'),('range_raw','range_raw','range_raw'),('curb_mass_raw','curb_mass_raw','curb_mass_raw'),('battery_mass_raw','battery_mass_raw','battery_mass_raw'),('battery_energy_raw','battery_energy_raw','battery_energy_raw'),('remark_raw','remarks_raw','remarks_raw')]:
  equal=norm(original[original_field])==norm(retained[old_field])==norm(x[param_field]);assert equal,(x['model_raw'],original_field,original[original_field],retained[old_field],x[param_field])
  comparison.append({'model_key':norm(x['model_raw']),'independent_row_1based':original['independent_row_1based'],'field':param_field,'cfb_original_raw':original[original_field],'existing_40_rows_csv_raw':retained[old_field],'raw_parameter_record_value':x[param_field],'raw_parameter_record_id':x['record_id'],'all_three_equal_after_NFKC_whitespace_normalization':'1'})
corr=corrections[0];assert corr['model_key']=='SGM6500BEBEV' and corr['range_raw']=='608' and 'source_cell_0based=410' in corr['source_location']
assert not any(corr[k] for k in ['curb_mass_raw','battery_mass_raw','battery_energy_raw'])
assert corr['source_sha256']==before[str(SOURCE)]
write('40_listing_rows_7_fields_three_way_comparison_280.csv',comparison)
write('41_raw_parameter_record_scope_reconciliation.csv',[{'record_id':x['record_id'],'model_key':x['model_key'],'observation_kind':x['observation_kind'],'independent_original_kind':'40条乘用车列入之一' if x['observation_kind']=='目录列入' else '第62批第6项续航文字勘误','original_member_listing_row':'1' if x['observation_kind']=='目录列入' else '0','range_raw':x['range_raw'],'curb_mass_raw':x['curb_mass_raw'],'battery_mass_raw':x['battery_mass_raw'],'battery_energy_raw':x['battery_energy_raw'],'source_location':x['source_location'],'original_text_match_verified':'1'} for x in parameters])

assert before=={str(p):sha(p) for p in [SOURCE,DOCX,OLD,PARAMS]}
result={'source_doc_sha256':before[str(SOURCE)],'supplied_derived_docx_sha256':before[str(DOCX)],'docx_tables_total':len(table_rows),'docx_table0_scope':'一、纯电动汽车 / （一）乘用车','docx_table0_physical_rows':41,'docx_table0_header_rows':1,'docx_table0_data_rows':40,'docx_table1_scope':'一、纯电动汽车 / （二）客车','docx_table1_physical_rows':8,'docx_table1_header_rows':1,'docx_table1_data_rows':7,'passenger_continuation_as_separate_xml_table':False,'cfb_independent_passenger_data_rows':len(raw_rows),'cfb_end_of_data_cell_0based':409,'cfb_next_cell_0based':410,'cfb_next_cell_kind':'独立勘误段落和下一小节表头，不是第41条车型数据','passenger_erratum_verbatim':erratum,'erratum_refers_to_batch':'62','erratum_refers_to_item':'6','erratum_model':'SGM6500BEBEV','erratum_field':'纯电动续驶里程','erratum_new_value':'608km','erratum_is_batch64_new_listing_row':False,'models_missing_from_round5_40_rows_csv':missing,'models_extra_in_round5_40_rows_csv':extra,'41_physical_rows_explanation':'一张乘用车表共41物理行=1表头+40数据。若将其前27物理行和后14物理行相加，前组含1表头，数据应26+14=40；当前XML并不是27和14数据行的两张乘用车表。','counting_model_mentions_including_erratum':'40列入型号+1个第62批型号的文字勘误，不能作41条第64批新列入','scientific_scope':'本轮确认无遗漏第41条新列入；第62批SGM6500BEBEV字段勘误是单独科学信息，应保留为勘误而非新增成员。未重算主科学数据。','existing_input_files_unchanged':True,'batch64_raw_parameter_records':41,'batch64_raw_listing_records':40,'batch64_raw_partial_correction_records':1,'listing_rows_7_fields_three_way_comparisons':len(comparison),'listing_field_mismatches':0,'parameter_record_scope_mismatches':0,'correction_raw_range_608_verified':True,'raw_correction_other_3_numeric_fields_empty_verified':True,'scientific_project_rerun':False,'table_numbering_note':'此核查XML使用0based：table0=首张乘用车表、table1=次张客车表；旧extractor使用1based的OOXML table=1，指同一首张乘用车表，不是本核查table1。'}
(R/'independent_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');(R/'verification_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
