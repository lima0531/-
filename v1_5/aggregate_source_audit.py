#!/usr/bin/env python3
"""Combine independent source enumerations, then compare scientific raw fields."""
from pathlib import Path
from collections import Counter
import csv,hashlib,json,re,unicodedata
ROOT=Path(__file__).resolve().parent
TASK=ROOT.parent
OUT=ROOT/'catalogues';OUT.mkdir(exist_ok=True)
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def norm(s):return re.sub(r'\s+','',unicodedata.normalize('NFKC',s or ''))
rows=read(TASK/'round4/catalogues/独立原件_纯电动乘用车逐表参数.csv')
assert len(rows)==7145
rows+=read(ROOT/'batch01/primary_全部17行_独立枚举.csv')
rows+=read(ROOT/'batch64/第64批_纯电动乘用车独立全表40行.csv')
correction=read(ROOT/'batch64/第64批_SGM6500BEBEV_原文限定字段勘误.csv')[0]
quote=correction['original_quote']
assert '第六十二批' in quote and '第6项' in quote and '纯电动续驶里程应为608km' in quote
rows.append(dict(source_file='mf_batch64.doc',source_sha256=correction['source_sha256'],kind='仅续航文字勘误',
    model_raw=correction['model_key'],model_key=correction['model_key'],range_raw=correction['corrected_value'],
    curb_mass_raw='',battery_mass_raw='',battery_energy_raw='',remarks_raw='',location='source_cell_0based=410',
    original_quote=quote))
assert len(rows)==7203 and len({r['source_file'] for r in rows})==97
fields=['source_file','source_sha256','kind','model_key','model_raw','range_raw','curb_mass_raw','battery_mass_raw','battery_energy_raw','remarks_raw','location','original_quote']
with (OUT/'97份目录_独立科学原值枚举7203行.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
params=read(TASK/'round4/data_v1_4/研究数据/参数版本_原值与计算代理.csv')
value_fields=['model_key','kind','range_raw','curb_mass_raw','battery_mass_raw','battery_energy_raw','remarks_raw']
expected=Counter((Path(r['source_file']).name,)+tuple(norm(r.get(k,'')) for k in value_fields) for r in [dict(r,kind=r['observation_kind']) for r in params])
actual=Counter((r['source_file'],)+tuple(norm(r.get(k,'')) for k in value_fields) for r in rows)
missing,extra=expected-actual,actual-expected
assert not missing and not extra,(missing,extra)
inventory={r['source_file']:r for r in read(ROOT/'source_recovery/106原件回收清单_v1_5.csv') if r['scope']=='目录'}
counts=Counter(r['source_file'] for r in rows)
for r in rows:assert r['source_sha256']==inventory[r['source_file']]['source_sha256']
checks=[dict(source_file=name,source_sha256=inventory[name]['source_sha256'],independent_parameter_rows=count,
    raw_parameter_rows=sum(Path(p['source_file']).name==name for p in params),scientific_multiset_equal='1') for name,count in sorted(counts.items())]
with (OUT/'97份目录_最终逐源参数覆盖.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(checks[0]));w.writeheader();w.writerows(checks)
summary=dict(catalogue_sources=97,historical_exact_catalogue_originals=97,independent_parameter_rows=7203,
    prior_round_independent_rows=7145,new_source_table_rows=57,new_narrative_partial_correction_rows=1,
    scientific_fields=value_fields,model_or_scientific_multiset_missing=0,model_or_scientific_multiset_extra=0,
    all_historic_originals_verified=106,normalization='NFKC and whitespace removal only; slash choices and tolerances preserved',
    scope='All retained BEV passenger parameter rows in 97 historical catalogue sources; not legal/configuration identity or global catalogue exhaustiveness',
    partial_correction_raw_blanks_preserved=True,first_batch_primary_first_online_date_still_unverified=True)
(OUT/'all_catalogues_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
