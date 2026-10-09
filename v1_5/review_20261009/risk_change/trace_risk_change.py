#!/usr/bin/env python3
"""Read-only reconstruction provenance audit for the 2877 -> 2805 risk change.

Writes only companion CSV/JSON/Markdown in this directory. Frozen 1991,
cohort 3328, original inputs and every historical data version remain intact.
"""
import argparse,collections,csv,hashlib,json
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
COMPACT=ROOT/'compact_input_20261008/购置税项目_必要数据精简包_20261008'
V12=ROOT/'round3/versioning/data_v1_2'
V13=ROOT/'round3/reconstruction/data_v1_3'
V14=ROOT/'round4/data_v1_4'
V15=ROOT/'round5/reconstruction/data_v1_5'
COV=ROOT/'round3/coverage';CUT='2023-12-10'
RISK='研究数据/公告前风险集_连续处理强度输入.csv'
EVENTS='研究数据/资格事件_重建去重表.csv'
LINKS='研究数据/资格事件_逐原件连接.csv'
MEMBERS='研究数据/样本成员重建.csv'
TRACK={}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):
    TRACK[str(path)]=sha(path)
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def group(rows,key):
    result=collections.defaultdict(list)
    for r in rows:result[r[key]].append(r)
    return result
def serialized(value):return json.dumps(value,ensure_ascii=False,sort_keys=True)
def declared_risk(rows):return {r['model_key'] for r in rows if r['membership_announcement_cohort']=='1' and r['announcement_active_observed']=='1'}

def event_state(events):
    # An event can be latest only if no certainly observed event has a lower
    # date bound strictly later than its greatest admissible date at cutoff.
    eligible=[e for e in events if not e['public_date_lower_bound'] or e['public_date_lower_bound']<=CUT]
    certain=[e for e in eligible if e['public_date_upper_bound']<=CUT]
    latest=[e for e in eligible if not any(f['public_date_lower_bound']>min(e['public_date_upper_bound'],CUT) for f in certain)]
    actions={e['action'] for e in latest}
    if not certain:actions.add('未观察到列入')
    state={'列入':'在册（区间口径下的已收集事件）','撤销':'已撤销（区间口径下的已收集事件）','未观察到列入':'未列入（已收集记录范围）'}.get(next(iter(actions)) if len(actions)==1 else '','日期区间导致状态不确定')
    return {'state':state,'active':'1' if actions=={'列入'} else '0' if len(actions)==1 else '',
            'latest_event_ids':'|'.join(sorted(e['event_id'] for e in latest)),
            'latest_actions':'|'.join(sorted(actions))}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    datasets={name:{'risk':read(base/RISK),'events':read(base/EVENTS),'links':read(base/LINKS),'members':read(base/MEMBERS)} for name,base in [('compact',COMPACT),('v1_2',V12),('v1_3_final',V13),('v1_4',V14),('v1_5',V15)]}
    risks={name:declared_risk(d['risk']) for name,d in datasets.items()}
    members={r['model_key']:r for r in datasets['compact']['members']};keys=set(members)
    newevents=read(COV/'new_withdrawal_events.csv');newlinks=read(COV/'new_withdrawal_source_links.csv');fullenum=read(COV/'new_withdrawal_full_enumeration_2020_rows.csv')
    registry_path=ROOT/'round5/source_recovery/106原件回收清单_v1_5.csv'
    if not registry_path.exists():registry_path=V15/'原件回收登记/106原件回收清单_v1_5.csv'
    registry={r['source_sha256']:r for r in read(registry_path)}
    page_urls_by_sha=collections.defaultdict(list)
    attachment_manifest=ROOT/'round3/archive/attachment_manifest.json'
    date_evidence=ROOT/'round3/dates/registered_date_evidence.json'
    if attachment_manifest.exists():
        TRACK[str(attachment_manifest)]=sha(attachment_manifest)
        date_file_urls={}
        if date_evidence.exists():
            TRACK[str(date_evidence)]=sha(date_evidence)
            date_file_urls={r['evidence_file']:r['source_url'] for r in json.loads(date_evidence.read_text())}
        for item in json.loads(attachment_manifest.read_text()):
            if item.get('status')!='ok':continue
            for link in item.get('links',[]):
                url=link.get('page_url') or date_file_urls.get(link.get('page_file'))
                if url:page_urls_by_sha[item['sha256']].append(url)
    def source_reference(fingerprint):
        record=registry.get(fingerprint,{});urls=sorted(set(page_urls_by_sha.get(fingerprint,[])),key=lambda u:(urlparse(u).hostname!='www.miit.gov.cn',u))
        return record.get('download_url',''),urls[0] if urls else ''
    corrections=read(COV/'batch27_corrected_events_47.csv')
    old_events=datasets['v1_2']['events'];old_eventmap={e['event_id']:e for e in old_events};correctionmap={e['event_id']:e for e in corrections}
    stages={'uploaded':datasets['compact']['events'],'date_only_v1_2':old_events,'new_73_only':old_events+newevents,
            'correct_47_only':[correctionmap.get(e['event_id'],e) for e in old_events],
            'both_repairs':[correctionmap.get(e['event_id'],e) for e in old_events]+newevents}
    states={};stage_risks={}
    for name,events in stages.items():
        bymodel=group(events,'model_key');states[name]={k:event_state(bymodel[k]) for k in keys}
        stage_risks[name]={k for k in keys if members[k]['membership_announcement_cohort']=='1' and states[name][k]['active']=='1'}
    assert stage_risks['uploaded']==risks['compact']
    assert stage_risks['date_only_v1_2']==risks['v1_2']==risks['compact']
    assert stage_risks['both_repairs']==risks['v1_3_final']==risks['v1_4']==risks['v1_5']
    removed=risks['compact']-risks['v1_3_final'];restored=risks['v1_3_final']-risks['compact']
    assert len(removed)==73 and len(restored)==1 and restored=={'CSA6461FBEV3'}
    assert removed=={e['model_key'] for e in newevents} and not removed&{e['model_key'] for e in corrections}
    assert [len(stage_risks[s]) for s in ['uploaded','date_only_v1_2','new_73_only','both_repairs']]==[2877,2877,2804,2805]
    oldrisk={r['model_key']:r for r in datasets['compact']['risk']};finalrisk={r['model_key']:r for r in datasets['v1_3_final']['risk']};risk15={r['model_key']:r for r in datasets['v1_5']['risk']}
    new_by_model=group(newevents,'model_key');newlink_by_model=group(newlinks,'model_key');enum_by_id={r['source_record_id']:r for r in fullenum}
    final_by_model=group(datasets['v1_3_final']['events'],'model_key');old_by_model=group(datasets['compact']['events'],'model_key');all_final_links=group(datasets['v1_3_final']['links'],'event_id')
    proofrows=[];modelrows=[]
    correction_evidence=json.loads((COV/'batch27_32_source_date_conclusion.json').read_text())
    for key in sorted(removed|restored):
        kind='新增历史撤销使风险移出' if key in removed else '第27批错日期修复使风险恢复'
        if key in removed:
            triggers=new_by_model[key];links=newlink_by_model[key]
            # Every removed model had exactly one previously retained listing,
            # certainly before the newly recovered withdrawal observation.
            assert len(old_by_model[key])==1 and old_by_model[key][0]['action']=='列入'
            assert old_by_model[key][0]['public_date_upper_bound']<triggers[0]['public_date_lower_bound']
            event=triggers[0];link=links[0];origin=enum_by_id[link['source_record_id']]
            source_url=origin['source_url'];announcement_url=origin['announcement_url'];evidence_path=str(COV/'new_withdrawal_full_enumeration_2020_rows.csv')
        else:
            event=next(e for e in corrections if e['model_key']==key);link=next(l for l in all_final_links[event['event_id']] if l['source_sha256']==correction_evidence['earlier_source_sha256'])
            source_url='https://www.miit.gov.cn/cms_files/filemanager/oldfile/miit/n1146285/n1146352/n3054355/n3057585/n3057589/c7485448/part/7485456.doc'
            announcement_url='https://www.miit.gov.cn/jgsj/zbys/gzdt/art/2020/art_9f09e324e0064eb6ac473ff2949f699c.html';evidence_path=str(COV/'batch27_32_source_date_conclusion.json')
        modelrows.append({'model_key':key,'change_reason':kind,'in_original_frozen_1991':members[key]['in_frozen_1991'],'membership_announcement_cohort':members[key]['membership_announcement_cohort'],'old_risk_2877':str(int(key in risks['compact'])),'intermediate_risk_2804':str(int(key in stage_risks['new_73_only'])),'final_v1_3_risk_2805':str(int(key in risks['v1_3_final'])),'current_v1_5_risk_2805':str(int(key in risks['v1_5'])),'old_cutoff_state':oldrisk[key]['announcement_state'],'intermediate_cutoff_state':states['new_73_only'][key]['state'],'new_cutoff_state':finalrisk[key]['announcement_state'],'old_numeric_ready':oldrisk[key]['descriptive_continuous_did_input_ready'],'final_v1_3_numeric_ready':finalrisk[key]['descriptive_continuous_did_input_ready'],'current_v1_5_numeric_ready':risk15[key]['descriptive_continuous_did_input_ready'],'trigger_event_id':event['event_id'],'trigger_event_batch':event['event_batch'],'trigger_observed_date':event['publish_date_exact'],'trigger_source_record_id':link['source_record_id'],'trigger_source_sha256':link['source_sha256'],'trigger_source_location':link['source_location'],'trigger_source_url':source_url,'trigger_announcement_url':announcement_url,'trigger_evidence_file':evidence_path,'old_latest_event_ids':states['uploaded'][key]['latest_event_ids'],'new_latest_event_ids':states['both_repairs'][key]['latest_event_ids']})
        for stage_name,dataset_name in [('old_uploaded','compact'),('final_v1_3','v1_3_final')]:
            dataset=datasets[dataset_name];link_by_event=group(dataset['links'],'event_id')
            for e in sorted((x for x in dataset['events'] if x['model_key']==key),key=lambda x:(x['public_date_upper_bound'],x['event_id'])):
                for l in link_by_event[e['event_id']]:
                    src=enum_by_id.get(l['source_record_id']);registry_url,registry_page=source_reference(l['source_sha256'])
                    proofrows.append({'model_key':key,'risk_change_reason':kind,'data_stage':stage_name,'event_id':e['event_id'],'action':e['action'],'system':e['system'],'event_batch':e['event_batch'],'publish_date_exact':e['publish_date_exact'],'public_date_lower_bound':e['public_date_lower_bound'],'public_date_upper_bound':e['public_date_upper_bound'],'event_date_basis':e['event_date_basis'],'source_record_id':l['source_record_id'],'source_file':l['source_file'],'source_sha256':l['source_sha256'],'source_location':l['source_location'],'source_url':src['source_url'] if src else source_url if l['source_sha256']==link['source_sha256'] else registry_url, 'announcement_url':src['announcement_url'] if src else announcement_url if l['source_sha256']==link['source_sha256'] else registry_page, 'legal_effective_date_verified':'0','historical_first_online_verified':'0'})
    write('风险集变动_74型号逐源对照.csv',modelrows);write('风险集变动_旧新事件链与原件出处.csv',proofrows)
    sourcegroups=[]
    for h,links in group(newlinks,'source_sha256').items():
        source=json.loads((COV/'new_withdrawal_sources.json').read_text());s=next(x for x in source if x['source_sha256']==h);physical=Path(s['source_file'])
        if not physical.is_file():physical=COV/'raw'/physical.name
        actual=sha(physical)
        assert actual==h and physical.stat().st_size==s['source_bytes']
        sourcegroups.append({'source_tag':s['tag'],'new_events':len(links),'unique_models':len({l['model_key'] for l in links}),'full_official_rows':s['full_table_rows'],'signed_date':s['signed_date'],'registered_public_observation_date':s['published_date'],'source_sha256':h,'source_file':str(physical),'source_url':s['source_url'],'announcement_url':s['announcement_url'],'physical_sha256_verified':True})
    write('新增撤销_逐来源数量及证据.csv',sourcegroups)
    versionchecks=[]
    for name,d in datasets.items():
        keyset={r['model_key'] for r in d['members']};assert keyset==keys
        versionchecks.append({'stage':name,'cohort_members':len(keyset),'frozen_members':sum(r['in_frozen_1991']=='1' for r in d['members']),'risk_models':len(risks[name]),'numeric_ready_models':sum(r['descriptive_continuous_did_input_ready']=='1' for r in d['risk']),'event_rows':len(d['events']),'source_link_rows':len(d['links']),'risk_flag_member_state_sha256':hashlib.sha256(serialized(sorted((r['model_key'],r['membership_announcement_cohort'],r['announcement_active_observed'],r['announcement_state']) for r in d['risk'])).encode()).hexdigest()})
    write('版本阶段_实际人数与风险标记指纹.csv',versionchecks)
    changed15=[k for k in keys if finalrisk[k]['descriptive_continuous_did_input_ready']!=risk15[k]['descriptive_continuous_did_input_ready']]
    assert changed15==['SGM6500BEBEV']
    assert all(oldrisk[k][c]==finalrisk[k][c] for k in keys for c in ['continuous_exposure_range','continuous_exposure_density_proxy','continuous_exposure_joint_max'])
    # Original event/source/state files stayed byte-identical in the v1.5
    # field-correction work. Risk CSV changes ready/parameter fields only.
    v15_equal={rel:sha(V14/rel)==sha(V15/rel) for rel in [EVENTS,LINKS,'研究数据/重建样本_三截点状态.csv',MEMBERS]}
    assert all(v15_equal.values())
    input_unchanged=all(sha(path)==fingerprint for path,fingerprint in TRACK.items());assert input_unchanged
    fingerprints=[{'path':path,'sha256':fingerprint,'still_unchanged':sha(path)==fingerprint} for path,fingerprint in sorted(TRACK.items())]
    write('只读追溯输入_SHA256.csv',fingerprints)
    summary={'cutoff':CUT,'definition':'membership_announcement_cohort=1 AND announcement_active_observed=1; observed catalogue states, not VIN-level legal certification','equation':'2877 − 73 + 1 = 2805','baseline_risk_count':2877,'added_historical_withdrawal_events':73,'removed_models_count':len(removed),'restored_models_count':len(restored),'final_risk_count':2805,'removed_models':sorted(removed),'restored_models':sorted(restored),'stage_risk_counts':{name:len(value) for name,value in stage_risks.items()},'new_source_groups':sourcegroups,'corrected_existing_events':47,'corrected_source_sha256':correction_evidence['earlier_source_sha256'],'restored_model':'CSA6461FBEV3','restored_model_old_withdrawal_date':'2020-06-02','restored_model_corrected_withdrawal_date':'2019-10-25','restored_model_relisting_date':'2019-12-10','unchanged_analytic_cohort':3328,'unchanged_original_frozen_members':1991,'v1_5_risk_set_changed':False,'v1_5_qualification_files_byte_unchanged_from_v1_4':v15_equal,'v1_5_ready_only_changed_models':changed15,'v1_5_ready_change':'2424 -> 2425; SGM6500BEBEV explicit field correction, not risk membership change','v1_3_frozen_exposure_strings_unchanged':True,'risk_csv_rows':len(modelrows),'old_new_source_event_rows':len(proofrows),'all_tracked_inputs_unchanged':input_unchanged,'read_only_output_dir':str(OUT)}
    (OUT/'risk_change_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in summary.items() if not isinstance(v,(dict,list))},ensure_ascii=False,indent=2))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT,help='Audit project root containing compact_input_20261008 and rounds 3/4/5')
    parser.add_argument('--output',type=Path,help='Companion output directory; default ROOT/round6/risk_change')
    args=parser.parse_args();ROOT=args.root.resolve();OUT=(args.output or ROOT/'round6/risk_change').resolve()
    COMPACT=ROOT/'compact_input_20261008/购置税项目_必要数据精简包_20261008'
    V12=ROOT/'round3/versioning/data_v1_2';V13=ROOT/'round3/reconstruction/data_v1_3';V14=ROOT/'round4/data_v1_4';V15=ROOT/'round5/reconstruction/data_v1_5';COV=ROOT/'round3/coverage'
    if any(OUT==base or base in OUT.parents for base in [COMPACT,V12,V13,V14,V15,COV]):raise ValueError('Output must be outside read-only evidence and data versions')
    main()
