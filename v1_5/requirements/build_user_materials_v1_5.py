#!/usr/bin/env python3
"""Update collection requests from the effective v1.5 view without mutating data."""
import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
R5 = OUT.parent
AUDIT = R5.parent
OLD = AUDIT / 'round4/requirements'
BASE = R5 / 'reconstruction/data_v1_5'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(name, rows, fields=None):
    with (OUT/name).open('w', encoding='utf-8-sig', newline='') as f:
        w=csv.DictWriter(f, fieldnames=fields or list(rows[0])); w.writeheader(); w.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    provenance=[]
    copy_names=['285配置版本_跨目录身份材料待补清单.csv', '19配置版本_低温报告优先待补清单.csv', '92再申报型号_逐车材料待补清单.csv', '配置技术资格与M1_所需证明字段规范.csv', '32型号_区间跨阈值优先配置材料清单.csv', '4型号_单项跨阈值补充清单.csv']
    for name in copy_names:
        shutil.copyfile(OLD/name, OUT/name)
        assert sha(OLD/name)==sha(OUT/name)
        provenance.append({'output':name,'input':str((OLD/name).relative_to(AUDIT)),'input_sha256':sha(OLD/name),'method':'byte_copy_unchanged_scope'})
    configurations=read(OUT/'285配置版本_跨目录身份材料待补清单.csv')
    lowtemp=read(OUT/'19配置版本_低温报告优先待补清单.csv')
    assert (len(configurations),len({r['config_id'] for r in configurations}),len({r['model_key'] for r in configurations}))==(285,278,170)
    assert (len(lowtemp),len({r['model_key'] for r in lowtemp}))==(19,12)
    assert len(read(OUT/'92再申报型号_逐车材料待补清单.csv'))==92
    assert len(read(OUT/'32型号_区间跨阈值优先配置材料清单.csv'))==32
    assert len(read(OUT/'4型号_单项跨阈值补充清单.csv'))==4
    standard_source=AUDIT/'round4/public_gaps/standard/标准登记_待人工补字段.csv'
    shutil.copyfile(standard_source,OUT/'公开标准登记_可选待补字段.csv')
    provenance.append({'output':'公开标准登记_可选待补字段.csv','input':str(standard_source.relative_to(AUDIT)),'input_sha256':sha(standard_source),'method':'byte_copy_optional_public_metadata_request'})
    raw_path=BASE/'研究数据/参数版本_原值与计算代理.csv'
    view_path=BASE/'研究数据/参数版本_字段勘误生效视图.csv'
    risk_path=BASE/'研究数据/公告前风险集_连续处理强度输入.csv'
    snap_path=BASE/'研究数据/重建样本_两截点参数与暴露.csv'
    before={str(p):sha(p) for p in [raw_path,view_path,risk_path,snap_path]}
    raw={r['record_id']:r for r in read(raw_path)}
    view={r['record_id']:r for r in read(view_path)}
    risk=read(risk_path)
    snap={r['model_key']:r for r in read(snap_path) if r['cutoff']=='2023-12-10'}
    assert len(raw)==len(view)==7203 and len(risk)==len(snap)==3328
    assert sha(raw_path)==sha(AUDIT/'round4/data_v1_4/研究数据/参数版本_原值与计算代理.csv')
    active=[r for r in risk if r['announcement_active_observed']=='1']
    ready=[r for r in risk if r['descriptive_continuous_did_input_ready']=='1']
    unmarked=[r for r in ready if not r['range_cycle_explicit']]
    assert len(active)==2805 and len(ready)==2425 and len(unmarked)==2208
    assert sum(r['range_cycle_explicit']=='CLTC' for r in ready)==217
    previous=read(OLD/'2207数值可用型号_公告前试验工况待核清单.csv')
    new_keys={r['model_key'] for r in unmarked}; old_keys={r['model_key'] for r in previous}
    assert new_keys-old_keys=={'SGM6500BEBEV'} and old_keys-new_keys==set()
    cycle_rows=[]; links=[]
    fields=['range','curb_mass','battery_mass','battery_energy','density_proxy']
    for r in sorted(unmarked,key=lambda x:x['model_key']):
        ids=r['exposure_record_ids'].split(';')
        assert ids==snap[r['model_key']]['possible_latest_record_ids'].split(';')
        observations=[view[rid] for rid in ids]
        assert all(o['model_key']==r['model_key'] for o in observations)
        source_maps=[]
        for o in observations:
            source_ids=json.loads(o['field_source_record_ids_json'])
            source_sha=json.loads(o['field_source_sha256_json'])
            source_dates=json.loads(o['field_observation_upper_bounds_json'])
            source_maps.append({'effective_record_id':o['record_id'],'composition_kind':o['composition_kind'],'target_record_id':o['target_record_id'],'field_source_record_ids':source_ids,'field_source_sha256':source_sha,'field_observation_upper_bounds':source_dates})
            for field in fields:
                assert len(source_ids[field])==len(source_sha[field])==len(source_dates[field])
                for rid, fingerprint, date in zip(source_ids[field],source_sha[field],source_dates[field]):
                    origin=raw[rid]
                    assert origin['source_sha256']==fingerprint and origin['public_date_upper_bound']==date and date<='2023-12-10'
                    value=origin.get(field+'_raw','') if field!='density_proxy' else '1000×'+origin['battery_energy_raw']+'/'+origin['battery_mass_raw']
                    links.append({'model_key':r['model_key'],'effective_record_id':o['record_id'],'field':field,'original_source_record_id':rid,'source_file':origin['source_file'],'source_sha256':fingerprint,'source_location':origin['source_location'],'source_public_date_upper':date,'source_field_raw':value,'effective_point':o[field+'_point'],'composition_kind':o['composition_kind'],'correction_scope_verified':o['correction_scope_verified'],'cross_configuration_identity_certified':'0'})
        cycle_rows.append({'model_key':r['model_key'],'freeze_cutoff':'2023-12-10','numeric_ready_v1_5':'1','range_cycle_label_in_effective_source':'','effective_record_ids':r['exposure_record_ids'],'effective_source_files':';'.join(o['source_file'] for o in observations),'effective_source_sha256s':';'.join(o['source_sha256'] for o in observations),'field_source_maps_json':json.dumps(source_maps,ensure_ascii=False,separators=(',',':')),'frozen_range_effective_point':snap[r['model_key']]['range_point'],'density_proxy_effective_point':snap[r['model_key']]['density_proxy_point'],'observed_date_upper':r['exposure_max_observation_upper'],'needed_materials':'要做同工况可比分析时：公告前对应配置原试验报告、标准/工况、报告编号日期版本及配置对应依据','holder_or_channel':'申报企业认证部门、检测机构、授权产品档案','use_condition':'仅同工况可比暴露或完整试验口径认定；不阻塞目录事件状态分析','report_id_received':'','test_standard_revision_received':'','test_cycle_received':'','test_configuration_key_received':'','material_received':'','material_sha256_received':'','same_cycle_comparability_verified':'0','can_use_future_parameter_backfill':'0'})
    write('2208数值可用型号_公告前试验工况待核清单.csv',cycle_rows)
    write('2208型号_工况清单字段来源长表.csv',links)
    assert len(cycle_rows)==2208 and len(links)==11040
    sgmlinks=[l for l in links if l['model_key']=='SGM6500BEBEV']
    assert {l['original_source_record_id'] for l in sgmlinks if l['field'] in ['battery_mass','battery_energy','density_proxy','curb_mass']}=={'old-62-Word97--0-7'}
    assert {l['original_source_record_id'] for l in sgmlinks if l['field']=='range'}=={'old-text-correction-64-SGM6500BEBEV'}
    for p in [raw_path,view_path,risk_path,snap_path]:
        provenance.append({'output':'2208工况清单及字段来源长表','input':str(p.relative_to(AUDIT)),'input_sha256':sha(p),'method':'recompute_ready_cycle_blank_then_join_effective_record_and_field_origins'})
    jx=raw['old-48-Word97--0-20']; assert not jx['battery_energy_raw']
    write('仅1型号_公告前真实原空字段待补.csv',[{'model_key':'JX6550T-M5BEV','record_id':jx['record_id'],'source_batch':jx['source_batch'],'source_file':jx['source_file'],'source_sha256':jx['source_sha256'],'source_location':jx['source_location'],'source_public_date_upper':jx['public_date_upper_bound'],'field':'battery_energy_raw','unit':'kWh','available_battery_mass_kg':'416','needed_material':'第48批公告前对应申报配置总能量的原始申报页/检测报告，或2023-12-10以前已公开的官方更正','holder_or_channel':'申报企业技术/认证部门、检测机构、既有产品档案','cannot_substitute':'2023-12-26减免目录65.17kWh不能直接回填公告前冻结值','received_material':'','received_sha256':''}])
    proof=json.loads((R5/'methodology/partial_correction_review.json').read_text())
    recovery=json.loads((R5/'source_recovery/source_recovery_summary.json').read_text())
    assert recovery['exact_bytes_verified']==106 and recovery['all_archive_identity_gaps_closed']
    closed=[]
    for file,fp,size in [('mf_batch01.pdf','eac13628c37f01c4da157a2d1916d97acc81fdc295f18e1783549075ce7e5aa7',442883),('mf_batch64.doc','c4e238989e7e40ec2c3a6a899ead170b4a745bc72546ba6fd4a5731d8890c6cb',597504)]:
        original=R5/'originals'/file
        assert sha(original)==fp and original.stat().st_size==size
        closed.append({'previous_request':file,'status':'已由用户提供，历史同字节指纹通过','source_sha256':fp,'closure_evidence':str(original.relative_to(AUDIT)),'source_bound_scope':'原件档案身份与逐表核查；不新增配置或法律资格认证','request_still_needed':'0'})
    closed.append({'previous_request':'SGM6500BEBEV 第64批勘误范围及未更正电池字段承接','status':'已取得原文限定更正证据，effective视图已生效','source_sha256':sha(R5/'methodology/partial_correction_review.json'),'closure_evidence':'round5/methodology/partial_correction_review.json；round5/batch64/第64批_SGM6500BEBEV_原文限定字段勘误.csv','source_bound_scope':proof['correction_quote']+'；仅续航502→608，同条目整备2620kg/电池620kg/95.7kWh保留；不是跨配置匹配','request_still_needed':'0'})
    write('已补证关闭_原件与SGM字段请求.csv',closed)
    tasks=[
        ('P1','公告前真实原空字段','1型号','JX6550T-M5BEV电池总能量kWh及对应公告前配置来源','进一步处理公告前缺单值暴露时','仅1型号_公告前真实原空字段待补.csv','SGM请求已闭合；不再索取两份历史原件'),
        ('P1条件配置判定','32型号联合跨界及4型号单项跨界','32+4型号','具体配置版本、选项/公差含义、电池能量与质量对应证据','要缩小保守外包络以确定具体配置时','32型号_区间跨阈值优先配置材料清单.csv；4型号_单项跨阈值补充清单.csv','不需要为所有380型号任意选取点值'),
        ('P2','推荐与减免配置身份桥','285版本/278配置ID/170型号','减免申报配置ID/版本、部件身份、有效时间、与推荐配置的对应依据','要把推荐参数连接至减免配置时','285配置版本_跨目录身份材料待补清单.csv','公开推荐原值已核，不重复索取数字'),
        ('P2优先','低温例外报告','19版本/12型号','匹配配置附录A报告、编号日期机构、常温低温里程和衰减率、配置桥','要认定低温例外时','19配置版本_低温报告优先待补清单.csv','19为候选，尚未认证；不能放宽速度和能耗'),
        ('P2','再申报逐车资格','92型号；车辆数量未知','匿名车辆键、配置、真实制造日期、开票日期、重新列入事件及校验减免标识','要判断具体车辆享受减免税时','92再申报型号_逐车材料待补清单.csv','目录月份不能代替制造日期'),
        ('P2条件法律/技术认定','车辆类别/M1及同配置四条件证据','具体配置，类别范围按结论目的','类别证书；30分钟车速、续航、声明系统密度、能耗/整备质量及报告标准版本','要认定法定类别或完整技术资格时','配置技术资格与M1_所需证明字段规范.csv','来源乘用车分组不等于M1认证'),
        ('条件同工况比较','公告前试验工况和标准版本','2208数值可用未标工况型号','同配置原试验报告、工况、标准/报告版本与日期、配置对应依据','同工况可比暴露或完整试验口径认定时','2208数值可用型号_公告前试验工况待核清单.csv','2425数值可用=217明确CLTC+2208未标；SGM新增且工况仍未标'),
        ('可选公开补证','首批精确公开日及标准登记余项','首批1项；标准登记余项','主管部门原登记公开日；标准发布日/现行状态/替代链','完整日期/标准登记档案审计时','需要用户亲自提供的数据.md','PDF创建2014-08-29不是首发；实施2021-10-01已有；不阻塞2023–24状态分析'),
        ('仅市场政策效应研究','真实结果和观察分母','型号/配置×月份','所研究销量/生产/登记/价格结果、分母覆盖、0与未覆盖、配置桥和时间范围','研究销量停产市场退出价格效应时','需要用户亲自提供的数据.md','现有目录状态面板不含真实市场结果'),
    ]
    write('需要用户亲自提供_按用途与优先级.csv',[dict(zip(['priority','material','scope','needed_fields','needed_when','row_checklist','boundary'],t)) for t in tasks])
    for p in [R5/'source_recovery/source_recovery_summary.json',R5/'methodology/partial_correction_review.json',R5/'batch01/proof.json',R5/'batch64/verification_summary.json']:
        provenance.append({'output':'已关闭材料请求与MD证据说明','input':str(p.relative_to(AUDIT)),'input_sha256':sha(p),'method':'accept_verified_uploaded_original_and_explicit_partial_correction_scope'})
    write('输入来源与SHA256.csv',provenance)
    assert all(sha(Path(p))==fp for p,fp in before.items())
    assert not any(t['material'] in ['2份历史原件','SGM电池字段待补'] for t in read(OUT/'需要用户亲自提供_按用途与优先级.csv'))
    summary={'base_version':'v1.5','generated_utc':datetime.now(timezone.utc).isoformat(),'cohort_models':3328,'risk_models':2805,'numeric_ready_models':2425,'single_point_insufficient_models':380,'explicit_cltc_ready_models':217,'ready_cycle_blank_models':2208,'added_ready_cycle_blank_models':['SGM6500BEBEV'],'removed_cycle_blank_models':[],'field_origin_links':11040,'historic_originals_verified':106,'historical_originals_pending':0,'true_original_blank_field_models':['JX6550T-M5BEV'],'closed_requests':3,'frozen_scientific_delta':'SGM density and joint exposure blank→0; all other models preserved by reconstruction','raw_parameter_rows':7203,'raw_parameter_table_same_bytes_as_v1_4':True,'scientific_parameters_read_from':'研究数据/参数版本_字段勘误生效视图.csv','canonical_data_mutated':False,'copied_scope_models_unchanged':{'priority_crossing':32,'additional_crossing':4,'recommendation_versions':285,'lowtemp_versions':19,'reapplication_models':92},'validation':'counts, set delta, exact record joins, field-origin SHA/date joins, SGM62/64 source separation, 106 recovery and raw-table identity assertions passed'}
    (OUT/'requirements_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write('文件_SHA256.csv',[{'file':p.name,'bytes':str(p.stat().st_size),'sha256':sha(p)} for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='文件_SHA256.csv'])
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
