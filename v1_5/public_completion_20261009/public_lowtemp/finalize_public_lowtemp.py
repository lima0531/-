from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import Counter
from urllib.parse import urljoin
import csv, json, hashlib, re, html, shutil

ROOT=Path(__file__).parent
ORIGINAL_SCOPE=Path('/workspace/file_export_proposal/v1_5/requirements/19配置版本_低温报告优先待补清单.csv')
SCOPE=ROOT/'19配置版本_输入范围.csv'
if not SCOPE.exists():shutil.copyfile(ORIGINAL_SCOPE,SCOPE)
ROWS=list(csv.DictReader(SCOPE.open(encoding='utf-8-sig')))

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(name,data):(ROOT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def writecsv(name,rows):
    if not rows:return
    with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def text(s):
    s=re.sub(r'<!--.*?-->|<script\b.*?</script>|<style\b.*?</style>',' ',s,flags=re.S|re.I)
    return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]*>',' ',s))).strip()

def run():
    assert len(ROWS)==19 and len({r['model_key'] for r in ROWS})==12 and len({r['firm_raw'] for r in ROWS})==8
    assert len({r['recommendation_config_id'] for r in ROWS})==19
    inputs=[{'file':str(SCOPE),'bytes':SCOPE.stat().st_size,'sha256':sha(SCOPE),'role':'本轮19配置版本范围副本'}]
    scanfile=ROOT/'推荐原件_19配置定位与报告字段扫描.json'
    if not scanfile.exists():
        import fitz
        src=Path('/workspace/purchase_tax_audit/round3/technical')
        scans=[]
        for sid in sorted({r['source_id'] for r in ROWS}):
            path=src/(sid+'_original.pdf')
            if not path.exists():continue
            digest=sha(path);expected={r['source_sha256'] for r in ROWS if r['source_id']==sid};assert expected=={digest}
            inputs.append({'file':str(path),'bytes':path.stat().st_size,'sha256':digest,'role':'已核官方推荐原件只读；本轮不重下'})
            doc=fitz.open(path);pages=[p.get_text() for p in doc]
            terms=['低温','附录A','附录 A','检测报告','18386']
            hits=[{'page_1based':i+1,'term':term} for i,t in enumerate(pages) for term in terms if term in t]
            configurations=[]
            for r in ROWS:
                if r['source_id']!=sid:continue
                cfg=r['recommendation_config_id'];found=[i+1 for i,t in enumerate(pages) if cfg in t]
                assert found, cfg
                configurations.append({'model_key':r['model_key'],'config_id':cfg,'pages_with_config_id':found,'low_temperature_report_id_obtained':False})
            scans.append({'source_id':sid,'source_sha256':digest,'page_count':len(pages),'text_layer_search_terms':terms,'text_layer_term_hits':hits,'configuration_locations':configurations,
                          'scope':'可提取文字层及19配置ID所在页面；不是对扫描图像的OCR证明，不从推荐参数生成附录A测试观察'})
        dump(scanfile.name,scans)
    else:
        scans=json.loads(scanfile.read_text())
        sourceinputs=ROOT/'核查输入_SHA256.csv'
        if sourceinputs.exists():inputs=list(csv.DictReader(sourceinputs.open(encoding='utf-8-sig')))
    writecsv('核查输入_SHA256.csv',inputs)

    receipts=[]
    for path in sorted(ROOT.rglob('*.receipt.json')):
        rec=json.loads(path.read_text());rec['receipt_file']=str(path.relative_to(ROOT));receipts.append(rec)
    requests=[]
    for rec in receipts:
        name=rec.get('local_file','');validity='原始HTTP观察；未据状态推断完整报告取得'
        if name.startswith('search/'):
            validity='初版简化selectFields接口阳性对照失败，不用于任何阴性结论'
        elif name.startswith('search_validated/'):
            validity='完整接口参数已用有结果的政策查询/特顺EV阳性对照验证；仅覆盖公开全文索引'
        elif rec.get('bytes')==0 and rec.get('status')=='ok':
            validity='HTTP200但正文为空；未取得可核内容'
        requests.append({'request_file':name,'receipt_file':rec['receipt_file'],'retrieved_utc':rec.get('retrieved_utc',''),'url':rec['requested_url'],
                         'final_url':rec.get('final_url',''),'purpose':rec.get('purpose',''),'query':rec.get('query',''),'target_models':'|'.join(rec.get('target_models',[])),
                         'status':rec['status'],'http_status':rec.get('http_status',''),'bytes':rec.get('bytes',''),'response_sha256':rec.get('sha256',''),
                         'evidence_scope':validity,'error':rec.get('error','')})
    writecsv('实际网络请求_逐次状态与SHA256.csv',requests)

    queries=json.loads((ROOT/'miit_search_results_validated.json').read_text())
    byquery={r['query']:r for r in queries}
    queryfindings=[]
    for rec in json.loads((ROOT/'institution_query_receipts.json').read_text()):
        observed='请求失败，未取得页面内容';candidates=[]
        if rec['status']=='ok':
            raw=(ROOT/rec['local_file']).read_text(errors='replace');visible=text(raw)
            for href,inner in re.findall(r'<a\b[^>]*href=[\"\']([^\"\']*)[\"\'][^>]*>(.*?)</a>',re.sub(r'<!--.*?-->',' ',raw,flags=re.S),re.S|re.I):
                title=text(inner)
                if '/indexnews/' in href or (rec['query']=='低温' and any(x in title for x in ['极寒','能耗','试验研究'])):
                    candidates.append({'title':title,'url':urljoin(rec['final_url'],html.unescape(href))})
            if '未查询到相关记录' in visible:
                observed='页面明示未查询到相关记录；仅是站内文章搜索结果'
            elif rec['query']=='18386.1' and candidates:
                observed='命中标准/修改单条目，不能当配置低温报告；修改单正文需登录'
            elif candidates:
                observed='命中测试服务/标准相关新闻，未获目标配置报告正文'
            else:
                observed='公开页面未见对应报告链接；不能排除委托系统或未索引附件'
        queryfindings.append({'query':rec['query'],'institution':'广州检验中心' if '/gatc_' in rec['local_file'] else 'SMVIC公开认证平台',
                              'request_file':rec['local_file'],'http_status':rec.get('http_status',''),'status':rec['status'],
                              'observed_result':observed,'candidates_json':json.dumps(candidates,ensure_ascii=False),'matching_full_report_obtained':0})
    writecsv('检测机构站内查询_命中与排除理由.csv',queryfindings)

    matrix=[]
    for row in ROWS:
        model=row['model_key'];cfg=row['recommendation_config_id']
        modelquery=byquery[model];cfgquery=byquery[cfg]
        assert modelquery['receipt']['status']=='ok' and cfgquery['receipt']['status']=='ok'
        related=[x for x in queryfindings if x['query']==model]
        assert len(related)==2
        matrix.append({'observation_version_key':row['observation_version_key'],'firm_raw':row['firm_raw'],'model_key':model,'recommendation_config_id':cfg,
                       'recommendation_source_id':row['source_id'],'recommendation_public_date':row['source_public_date'],'recommendation_sha256':row['source_sha256'],
                       'miit_model_query_file':modelquery['receipt']['local_file'],'miit_model_returned_hits':modelquery['returned_hits'],
                       'miit_config_query_file':cfgquery['receipt']['local_file'],'miit_config_returned_hits':cfgquery['returned_hits'],
                       'institution_search_receipts':'|'.join(x['request_file']+'.receipt.json' for x in related),
                       'full_report_obtained':0,'report_id_obtained':0,'test_institution_of_original_report_known':0,'same_configuration_identity_verified':0,
                       'remaining_action':'向申报企业索取原附录A低温报告及配置对应证据，由企业确认原检测机构；机构需授权后提供或核验',
                       'acceptance_fields':'报告编号/机构/日期/GB/T18386.1-2021及修改版本/附录A方法/常温与低温里程/衰减率/电池电机具体规格/试验配置与推荐及减免申报配置桥接',
                       'date_scope':'推荐观察为2022年；低温报告用于2024政策条件核验，按报告日期和申报生效月审查；后出材料不回填2023-12-10冻结数值',
                       'closure_status':'未闭合；公开接口本次范围未取得，不等于报告不存在'})
    writecsv('19配置版本_实际公开检索与剩余报告.csv',matrix)

    institutions=[
        {'institution':'中汽研汽车检验中心（天津）有限公司','entry_url':'https://www.tatc.com.cn/','evidence_file':'test_portals/tatc.html','public_contact_source':'test_portals/tatc_public_contact.json','public_contact_observed':'022-84379666；tatc@catarc.ac.cn（官网页脚公共接口）','role':'企业确认原报告机构后，转相应档案/业务部门核验','not_established':'未证明该机构出具这19版本任何原报告'},
        {'institution':'中汽研汽车检验中心（广州）有限公司','entry_url':'https://www.gatc.ac.cn/','evidence_file':'test_portals/gatc_https.html','public_contact_source':'test_portals/gatc_https.html','public_contact_observed':'020-32663310；catarcgz@catarc.ac.cn（公开首页正文）','role':'公开排放节能/新能源测试业务询证入口','not_established':'服务能力和极寒文章不是目标配置报告'},
        {'institution':'中汽研汽车检验中心（宁波）有限公司','entry_url':'http://www.catarc-nb.cn/p/contact','evidence_file':'test_portals/nb_contact.html','public_contact_source':'test_portals/nb_contact.html','public_contact_observed':'0086-574 23726625（当前正文；旧电话在注释中不引用）','role':'企业确认原机构后询证','not_established':'没有目标报告机构身份或编号'},
        {'institution':'上海机动车检测认证技术研究中心/SMVIC公开认证平台','entry_url':'https://hss.smvic.com.cn/','evidence_file':'test_portals/smvic_cert.html','public_contact_source':'test_portals/smvic_contacts.html.receipt.json','public_contact_observed':'公开业务联系页本次HTTP503；未取到联系人，不猜电话','role':'公开信息/标准条目检索及后续按合法授权查看','not_established':'标准修改单正文需登录；CCC认证不等于附录A报告'},
    ]
    writecsv('公开检测机构询证入口_不认定原报告归属.csv',institutions)
    now=datetime.now(timezone.utc)
    counts=Counter(x['status'] for x in receipts)
    summary={'as_of_shanghai':now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(),'scope':{'configuration_versions':19,'distinct_configuration_ids':19,'models':12,'firms':8,
             'unit_note':'19是待验证的配置版本数，不保证恰好19份独立报告；单报告能否覆盖多个配置需机构确认'},
             'newly_obtained_matching_full_reports':0,'newly_obtained_original_report_ids':0,'remaining_configuration_versions':19,
             'matching_low_temperature_evidence_obtained_flags_changed':0,'scientific_data_written':False,
             'actual_request_count':len(receipts),'actual_request_status_counts':dict(counts),
             'validated_miit_exact_model_queries':12,'validated_miit_exact_configuration_queries':19,
             'institution_get_search_requests':28,'public_pdf_text_layer_scanned_pages':sum(x['page_count'] for x in scans),
             'search_semantics':'初版简化selectFields接口阳性对照失败，初版零结果排除；完整参数重跑31目标请求及政策查询有阳性结果。所有精确搜索仅是当前官方公开索引观察，不是全网无资料证明。',
             'annex_a_requirement':'需同配置附录A检测与不超过35%低温里程衰减证据，才可讨论95Wh/kg与120km；常规速度及电耗要求继续核验。',
             'handoff_owner':'8家申报企业技术认证/准入部门；由企业确认原检测机构并授权索取原报告及配置桥接。未替用户发送任何对外信息。',
             'standard_amendment_clue':{'title':'E7-GB/T18386.1-2021 …《第1号修改单》','institution_list_date':'2026-07-09','url':'https://hss.smvic.com.cn/indexnews/1384','body_status':'HTTP200但正文标需登录，未取得全文','official_release_and_effective_dates_confirmed':False,'can_backfill_historical_frozen_input':False},
             'completion_criteria':['原报告正文可验机构、编号与版本/附录A方法','常温、低温里程和衰减率可复算，或原报告声明采用合规值并有相应依据','试验车辆/电池/电机与指定推荐配置、减免申报配置身份桥接','按报告日期、历史适用版本和实际申报生效期检查，不用2026网页时点替代历史证据'],
             'limitations':['未索引的企业/检测委托报告、登录平台材料本轮无法取得','403/503/超时仅记访问结果，不能当报告不存在','营销冬测、第三方媒体续航、政策条文、CCC证书及其他型号报告不用于闭合19版本','2022推荐原件没有报告字段，不证明之后从未检测']}
    dump('public_lowtemp_summary.json',summary)
    readme='''# 19低温配置版本：公开补证结果与交接

本轮按清单覆盖 **19配置版本、12型号、8家申报企业**。新取得匹配附录A完整报告 **0**，原报告编号 **0**，仍待验证 **19版本**。这是配置版本计数，实际独立报告份数尚未知；不能要求企业机械提供19份，也不能把一个报告未经确认复制给多个配置。

已完成12型号与19配置ID的工信部公开全文索引检索，并对12型号分别尝试广州检验中心、SMVIC公开GET搜索表单。原2022年两份推荐参数PDF共193页的可提取文字层也复核了：目标配置ID均可定位，未提供低温报告字段。本轮实际请求及每次HTTP状态、时间、URL、响应字节SHA在[请求台账](实际网络请求_逐次状态与SHA256.csv)，目标逐项对账见[19配置版本清单](19配置版本_实际公开检索与剩余报告.csv)。

接口有一处已主动纠正：初版缩短selectFields时，连已知有结果的阳性查询也返回0；初版响应予以保留并标记为不可支持阴性结论。随后使用此前有效的完整参数重跑全部31项，政策解读查询出现实际命中，精确型号及ID查询仍为0。这只表明本次当前公开索引没有返回这些精确词，不证明报告不存在或任何公开PDF均已穷尽。

检测机构公开入口已取到天津、广州、武汉、宁波及SMVIC页面。企业应先确认原机构再询证；不能凭现有入口认定任何一家实际出过目标报告。可直接使用[公开机构入口](公开检测机构询证入口_不认定原报告归属.csv)；天津公开[委托单](test_portals/tatc_commission_form.docx)只是业务表单。403、503、超时及空正文在台账中分别保留，未绕过登录。机构站内命中及排除理由在[逐查询表](检测机构站内查询_命中与排除理由.csv)。

向8家申报企业技术认证/准入部门索取：指定型号和配置ID的原GB/T18386.1-2021附录A低温报告；编号、机构、日期、采用版本与修改单；常温/低温续驶里程、衰减率；试验车辆、动力电池及电机的具体规格；与推荐配置及减免申报配置的对应证据。原机构未确定前，可让企业先给报告编号/机构确认页，再取得合法授权核验正文。完成的判据见[JSON摘要](public_lowtemp_summary.json)。

报告用于2024政策条件核验，应记录其实际报告日期和申报生效月。推荐资料观察日为2022年；后出试验材料不能自动回填2023-12-10公告前冻结数值。仍需同配置身份确认，才可判断低温衰减率不超过35%时95Wh/kg和120km的例外；速度与电耗要求继续核验。工信部[官方解读网页缓存](test_portals/miit_lowtemp_policy_interpretation.html)仅确认政策条件，没有提供这19版本的检测结果。

本轮还发现SMVIC公开搜索列表上的“GB/T18386.1-2021第1号修改单”条目，机构列表日期为2026-07-09；[条目正文](test_portals/smvic_standard_amendment_clue.html)明确需登录，未取得修改单全文，也未确认官方发布/实施日。这是当前标准版本的可选核验线索，不能据机构条目日期认定官方日期，更不能用于历史冻结数值。

目前没有继续随机扩散搜索即可保证取到的报告。剩余19版本需企业或原机构材料；营销冬测、政策门槛、CCC证书、其他型号报告都不能替代。没有改变科学CSV、身份确认或低温证据标志，也没有向企业发送任何消息。

复跑公开请求：同目录运行 `python collect_public_lowtemp.py`、`python inspect_test_portals.py`、`python query_institution_sites.py`；脚本复用保存的请求回执，便于离线审阅原时点。重新核验需要先另存新目录/旧回执，不覆盖历史观察。`finalize_public_lowtemp.py`整理本地已缓存证据；如要重新扫描原PDF，需提供现有核查输入所列原件路径，首次结果已在[原件扫描记录](推荐原件_19配置定位与报告字段扫描.json)中保存。所有字节见[SHA清单](文件_SHA256.csv)。
'''
    (ROOT/'README.md').write_text(readme)
    entries=[]
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts and p.name!='文件_SHA256.csv':
            entries.append({'file':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)})
    writecsv('文件_SHA256.csv',entries)
    print(json.dumps({'configuration_versions':19,'models':12,'firms':8,'requests':len(receipts),'full_reports':0,'manifest_files':len(entries),'bytes':sum(x['bytes'] for x in entries)},ensure_ascii=False))

if __name__=='__main__':run()
