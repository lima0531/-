#!/usr/bin/env python3
"""Independent source-lineage and temporal delta audit; no rebuild imports."""
from pathlib import Path
from fractions import Fraction
from collections import Counter
import csv,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'reconstruction/data_v1_5'
BASE=ROOT.parent/'round4/data_v1_4'
sys.path.insert(0,str(ROOT.parent/'round3/archive'))
from word_piece_text import extract

def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks=[]
def check(name,ok,detail=None):
    checks.append(dict(check=name,passed=bool(ok),detail=detail));assert ok,(name,detail)

rawfile=Path('研究数据/参数版本_原值与计算代理.csv')
check('原7203参数源表逐字节不变',sha(DATA/rawfile)==sha(BASE/rawfile))
raw={r['record_id']:r for r in rows(DATA/rawfile)}
effective={r['record_id']:r for r in rows(DATA/'研究数据/参数版本_字段勘误生效视图.csv')}
check('源表与生效视图同7203唯一逻辑记录',len(raw)==len(effective)==7203 and raw.keys()==effective.keys())
corr='old-text-correction-64-SGM6500BEBEV';parent='old-62-Word97--0-7';model='SGM6500BEBEV'
t,proof=extract(ROOT/'originals/mf_batch64.doc')
check('64原件精确限定更正62第6项续航',proof['source_sha256']==raw[corr]['source_sha256'] and
      '第六十二批' in t and '纯电动乘用车部分第6项' in t and '纯电动续驶里程应为608km' in t)
parent_path=ROOT.parent/'round3/archive/recovered/免征目录/mf_batch62.doc'
pt,pp=extract(parent_path)
check('父原件指纹且原行四数值存在',pp['source_sha256']==raw[parent]['source_sha256'] and
      '\tSGM6500BEBEV\tLYRIQ\t502\t2620\t620\t95.7\t' in pt)
allowed={p+'_'+s for p in ['curb_mass','battery_mass','battery_energy'] for s in ['point','lower','upper','values_new','parse_status_new']}
allowed|={'density_proxy_'+s for s in ['point','lower','upper']}
for rid,r in raw.items():
    e=effective[rid]
    changed={k for k,v in r.items() if v!=e[k]}
    check('生效改动范围:'+rid,changed==allowed if rid==corr else not changed)
    sources=json.loads(e['field_source_record_ids_json'])
    hashes=json.loads(e['field_source_sha256_json'])
    dates=json.loads(e['field_observation_upper_bounds_json'])
    for field,ids in sources.items():
        expected=[parent] if rid==corr and field!='range' else [rid]
        assert ids==expected and hashes[field]==[raw[x]['source_sha256'] for x in ids] and dates[field]==[raw[x]['public_date_upper_bound'] for x in ids]
check('全部7203逐字段来源ID_SHA_日期闭合',True)
check('更正原记录未声明字段仍为空',all(raw[corr][p+'_raw']==effective[corr][p+'_raw']=='' for p in ['curb_mass','battery_mass','battery_energy']))
check('原空白解析状态明确保留',all(json.loads(effective[corr]['original_field_parse_status_json'])[p]=='missing' for p in ['curb_mass','battery_mass','battery_energy']))
check('继承字段精确等于目标原数值',all(effective[corr][p+'_'+s]==raw[parent][p+'_'+s] for p in ['curb_mass','battery_mass','battery_energy'] for s in ['point','lower','upper','values_new']))
expected=Fraction('95.7')*1000/Fraction(620)
check('密度代理精确有理数复核',abs(Fraction(effective[corr]['density_proxy_point'])-expected)<Fraction(1,10**24))
check('冻结全部字段证据早于截点',all(d<='2023-12-10' for ds in json.loads(effective[corr]['field_observation_upper_bounds_json']).values() for d in ds))

panel=rows(DATA/'研究数据/车型月度面板_2022至2024.csv');oldpanel=rows(BASE/'研究数据/车型月度面板_2022至2024.csv')
changed_rows=[(a,b) for a,b in zip(oldpanel,panel) if a!=b]
check('仅SGM36行月度记录改变',len(changed_rows)==36 and all(a['model_key']==b['model_key']==model for a,b in changed_rows))
density_changed=[b['month'] for a,b in zip(oldpanel,panel) if a['density_proxy_record_point']!=b['density_proxy_record_point']]
check('仅2023April_November8当期密度改变',density_changed==[f'2023-{m:02}' for m in range(4,12)],density_changed)
for r in panel:
    if r['model_key']==model and r['month'] in ['2023-02','2023-03']:assert r['range_record_point']=='502'
check('更正608不回填2023Feb_March信息集',True)
protected=['研究数据/样本成员重建.csv','研究数据/原件列入_成员来源长表.csv',
 '研究数据/资格事件_重建去重表.csv','研究数据/资格事件_逐原件连接.csv',
 '研究数据/重建样本_三截点状态.csv','研究数据/政策后资格轨迹与重申报标签.csv',
 '官方技术清单/2024撤销观察_分母与集合对账.csv','1991基线/1991_独立重建名单.csv']
for rel in protected:check('不改变成员_资格_状态:'+rel,sha(DATA/rel)==sha(BASE/rel))
risk=rows(DATA/'研究数据/公告前风险集_连续处理强度输入.csv')
check('2425单值准备_2805风险集',sum(x['descriptive_continuous_did_input_ready']=='1' for x in risk)==2425 and sum(x['membership_announcement_cohort']=='1' and x['announcement_active_observed']=='1' for x in risk)==2805)
layers=rows(DATA/'官方技术清单/五档数值层_逐型号归属与判据.csv');counts=Counter(x['numeric_layer'] for x in layers)
check('380不足_1822两项达到',counts['单值不足']==380 and counts['两项数值均达到常规阈值']==1822,dict(counts))
for x in rows(ROOT/'source_recovery/106原件回收清单_v1_5.csv'):
    check('原件106指纹:'+x['source_file'],sha(Path(x['recovered_path']))==x['source_sha256'] and Path(x['recovered_path']).stat().st_size==int(x['source_bytes']))
input_root=ROOT.parent/'compact_input_20261008/购置税项目_必要数据精简包_20261008'
entries=(input_root/'文件清单_SHA256.txt').read_text(encoding='utf-8-sig').splitlines()
for line in entries:
    h,name=line.split('  ',1);assert sha(input_root/name)==h
check('原始精简输入63文件未改',len(entries)==63)
result=dict(checks=len(checks),pass_count=sum(x['passed'] for x in checks),fail_count=sum(not x['passed'] for x in checks),
    raw_source_unchanged=True,all_field_lineage_closed=True,no_future_information=True,details=checks)
(ROOT/'validation/lineage_and_delta_results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=False))
