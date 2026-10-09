#!/usr/bin/env python3
"""Classify preserved public candidates without inventing missing energy."""
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import html
import json
import re
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def csv_write(name, rows, fields=None):
    with (ROOT/name).open('w', encoding='utf-8-sig', newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)

def text(name):
    source=(ROOT/'raw'/name).read_text(errors='replace')
    source=re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>','',source,flags=re.S|re.I)
    return re.sub(r'\n\s*\n','\n',html.unescape(re.sub('<[^>]+>','\n',source)))

receipts=[]
for path in sorted((ROOT/'raw').glob('*.receipt.json')):
    row=json.loads(path.read_text())
    if row.get('local_file'):
        content=ROOT/row['local_file']
        assert content.stat().st_size==row['bytes'] and sha(content)==row['sha256']
    receipts.append(row)
assert len(receipts)==15
reprints=text('cdqc_JX.html'),text('sohu_reprint.html')
assert all('JX6550T-M5BEV' in x for x in reprints)
assert re.search(r'动力蓄电池组总能量\(kWh\)\s*燃料消耗量',reprints[0])
for name,content in zip(['cdqc_JX','sohu_reprint'],reprints):
    (ROOT/'raw'/(name+'.txt')).write_text(content)
api=json.loads((ROOT/'raw/jmc_current_parameter_api.html').read_text())
serialized=json.dumps(api,ensure_ascii=False)
assert api['code']==1 and 'E全顺' in serialized and 'JX6550T-M5BEV' not in serialized
assert all(k not in serialized for k in ['NC010086','L173C01','L173G01'])
assert '77.28kWh' in serialized and '100.96kWh' in serialized
byname={r['name']:r for r in receipts}
analysis={
    'bing_exact':'响应结果内容无关，不支持目标未检出的阴性结论',
    'bing_config':'响应结果内容无关，不支持目标未检出的阴性结论',
    'bing_storage':'响应结果内容无关，不支持目标未检出的阴性结论',
    'baidu_exact':'脚本或跳转页面，没有可核查参数结果，不据此认证无数据',
    'google_exact':'JavaScript验证响应，没有可核查参数结果，不据此认证无数据',
    'duck_exact':'相关结果指向协会税48转载及Sohu整表转载，均未补出能量',
    'duck_energy':'含近似型号JX6550TA、JX6556、JX6570及当前E全顺；不混作JX6550T-M5BEV',
    'duck_config':'本次结果页显示No results，仅为本次公共索引观察',
    'duck_storage':'中车其他型号与2025/2026材料，不证明江铃历史配置',
    'cdqc_JX':'协会转载税48，能量字段同为空；辅助复述，不代替官方原件',
    'sohu_reprint':'税48整表转载同未提供JX能量；辅助复述，不代替官方原件',
    'jmc_current_config':'官网当前E全顺产品页面，未提供目标型号或历史版本身份',
    'jmc_config_js':'官网前端提供参数查询路径；本文件不是参数或检测证据',
    'jmc_common_js':'官网前端给出GET /parameter/getconfigurelist，已按其公开参数查询',
    'jmc_current_parameter_api':'原生GET成功，E全顺77.28/100.96等当前产品；无目标型号/推荐ID/储能版本/历史日期桥',
}
rows=[]
for name,reason in analysis.items():
    r=byname[name]
    rows.append({'candidate':name,'source_url':r['requested_url'],'observed_utc':r['retrieved_at_utc'],
                 'http_status':r.get('http_status',''),'file':r.get('local_file',''),'sha256':r.get('sha256',''),
                 'effective_original_energy_evidence':'0','disposition':reason})
csv_write('候选与排除理由.csv',rows)
summary={'generated_utc':datetime.now(timezone.utc).isoformat(),'model_key':'JX6550T-M5BEV',
         'target_tax_batch':48,'freeze_date':'2023-12-10','actual_distinct_requests':len(receipts),
         'new_energy_field_closed':0,'new_tax_configuration_bridge_closed':0,
         'association_reproduction_energy_blank':True,'current_official_product_api_readable':True,
         'current_official_product_api_does_not_identify_target_historical_configuration':True,
         'search_responses_with_irrelevant_or_challenge_content_not_negative_evidence':True,
         'frozen_scientific_data_changed':False,
         'handoff_holder':'江铃汽车股份有限公司技术/认证/申报部门或该配置原检测机构',
         'needed':'税48历史配置总能量、配对电池质量和版本；若用NC010086则两储能版本分别对应及正式身份桥；来源历史日期与当时信息可得性分别核实'}
(ROOT/'jx_extended_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
(ROOT/'network_receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
(ROOT/'README.md').write_text('''# JX扩展公开渠道：仍需历史能量原件

2026-10-09继续查了公共外部索引、两份相关转载及江铃真实官网当前参数接口。**本轮新增有效原能量字段0、税配置身份桥0，JX6550T-M5BEV第48批能量原空仍保留。**

相关公共索引确实找到[成都市汽车行业协会税48条目](https://www.cdqc.org.cn/2747/15877/643981)和[Sohu税48整表转载](https://www.sohu.com/a/499829552_118021)，JX能量也空。这只能辅助复述，不能代替主管原件。组合能量检索的85.89、77.28、100.96或65.17等结果涉及JX6550TA、JX6556、JX6570或当前E全顺，型号/日期/配置不匹配，未借用。

进一步读了[江铃官网当前E全顺配置页](https://www.jmc.com.cn/config.html?car_type=0&brand_id=1092&configure_id=1007&car_category=2)及其真实前端脚本，按公开前端参数GET取到完整配置JSON。接口成功有数据，列E全顺77.28/100.96等容量，但未标JX6550T-M5BEV、NC010086、L173C01/L173G01或对应历史日期，不能用来关闭目标。

15个不同URL的响应全部保留；这不是15次有效阴性证据。Bing三响应虽200但内容无关，Google/Baidu是脚本或验证响应，不解释成资料不存在；DuckDuckGo具体ID的No results仅说明此次索引观察。未绕登录/验证、未提交业务申请或联系企业。

仍应向江铃技术/认证/申报部门或原检测机构索取税48历史配置的总能量、配对电池质量和版本。若使用NC010086推荐材料，需L173C01/L173G01分版本参数及正式税配置对应证据；历史技术事实的日期与公告前公开信息可得性分别核实。来源收到后再核验，不用现在的近似车型替代。

逐项结果见[候选与排除理由](候选与排除理由.csv)、[机器可读结论](jx_extended_summary.json)和[实际网络回执](network_receipts.json)。原推荐NC010086及税48同源核查仍以已发布round8证据为准。复查用本目录collect_extended.py，按缓存保留原观察日期；finalize_extended.py只读证据、更新伴随记录，不修改科学主数据。
''')
manifest=[]
for p in sorted(ROOT.rglob('*')):
    if p.is_file() and '__pycache__' not in p.parts and p.name!='文件_SHA256.csv':
        manifest.append({'file':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
csv_write('文件_SHA256.csv',manifest)
print(json.dumps(summary,ensure_ascii=False))
