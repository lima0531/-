#!/usr/bin/env python3
"""Count remaining conditional evidence scopes; never add incompatible units."""
import csv
import hashlib
import itertools
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

OUT=Path(__file__).resolve().parent
AUDIT=OUT.parents[1]
REQ=AUDIT/'round5/requirements'
BASE=AUDIT/'round5/reconstruction/data_v1_5'
LISTS={
    'JX原空字段':'仅1型号_公告前真实原空字段待补.csv',
    '32联合跨界':'32型号_区间跨阈值优先配置材料清单.csv',
    '4单项跨界':'4型号_单项跨阈值补充清单.csv',
    '推荐配置身份':'285配置版本_跨目录身份材料待补清单.csv',
    '低温例外':'19配置版本_低温报告优先待补清单.csv',
    '再申报逐车':'92再申报型号_逐车材料待补清单.csv',
    '公告前工况':'2208数值可用型号_公告前试验工况待核清单.csv',
}


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(name,rows,columns=None):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns or list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    sources=[REQ/f for f in LISTS.values()]
    sources += [BASE/'研究数据/公告前风险集_连续处理强度输入.csv',BASE/'研究数据/重建样本_两截点参数与暴露.csv',BASE/'研究数据/参数版本_字段勘误生效视图.csv',BASE/'研究数据/参数版本_原值与计算代理.csv',BASE/'研究数据/车型月度面板_2022至2024.csv',AUDIT/'round5/parameters/380单值不足_原因与保守区间核查.csv',AUDIT/'round5/source_recovery/source_recovery_summary.json',REQ/'公开标准登记_可选待补字段.csv']
    before={str(p):sha(p) for p in sources}
    rows={label:read(REQ/f) for label,f in LISTS.items()}
    sets={label:{r['model_key'] for r in rs} for label,rs in rows.items()}
    expected={'JX原空字段':1,'32联合跨界':32,'4单项跨界':4,'推荐配置身份':170,'低温例外':12,'再申报逐车':92,'公告前工况':2208}
    assert {k:len(v) for k,v in sets.items()}==expected
    assert sets['32联合跨界'].isdisjoint(sets['4单项跨界'])
    assert sets['JX原空字段']=={'JX6550T-M5BEV'}
    assert sets['低温例外']<=sets['推荐配置身份']
    identity_versions={r['observation_version_key'] for r in rows['推荐配置身份']}
    lowtemp_versions={r['observation_version_key'] for r in rows['低温例外']}
    assert len(identity_versions)==285 and len(lowtemp_versions)==19 and lowtemp_versions<=identity_versions
    assert len({r['config_id'] for r in rows['推荐配置身份']})==278
    risk=read(BASE/'研究数据/公告前风险集_连续处理强度输入.csv')
    cohort={r['model_key'] for r in risk}
    ready={r['model_key'] for r in risk if r['descriptive_continuous_did_input_ready']=='1'}
    risk_active={r['model_key'] for r in risk if r['announcement_active_observed']=='1'}
    assert len(cohort)==3328 and len(ready)==2425 and len(risk_active)==2805
    assert sets['公告前工况']=={r['model_key'] for r in risk if r['descriptive_continuous_did_input_ready']=='1' and not r['range_cycle_explicit']}
    outside_cohort={k:sorted(s-cohort) for k,s in sets.items()}
    assert outside_cohort['推荐配置身份']==['BAW7000UL45BEV','JX6482UBEV']
    assert all(not s for k,s in outside_cohort.items() if k!='推荐配置身份')
    intervals=read(AUDIT/'round5/parameters/380单值不足_原因与保守区间核查.csv')
    ic=Counter(r['two_parameter_interval_screen'] for r in intervals)
    assert len(intervals)==380
    assert set(r['model_key'] for r in intervals if r['two_parameter_interval_screen']=='区间跨越阈值，具体配置仍待匹配')==sets['32联合跨界']
    assert set(r['model_key'] for r in intervals if r['two_parameter_interval_screen']=='缺少可用原始字段/更正范围证据')==sets['JX原空字段']
    assert set(r['model_key'] for r in intervals if r['two_parameter_interval_screen']=='至少一项数值在整个外包络低于常规阈值' and r['both_parameter_threshold_results_determined']=='0')==sets['4单项跨界']
    with (BASE/'研究数据/车型月度面板_2022至2024.csv').open(encoding='utf-8-sig',newline='') as f:
        panel_count=sum(1 for _ in csv.DictReader(f))
    assert panel_count==119808
    recovery=json.loads((AUDIT/'round5/source_recovery/source_recovery_summary.json').read_text())
    assert recovery['exact_bytes_verified']==106 and recovery['all_archive_identity_gaps_closed']
    cross=[]
    for a,b in itertools.combinations(sets,2):
        common=sorted(sets[a]&sets[b])
        cross.append({'left':a,'right':b,'grain':'型号字符串相同；不证明同配置/同车辆','left_models':len(sets[a]),'right_models':len(sets[b]),'intersection_models':len(common),'intersection_model_keys':common})
    union=set().union(*sets.values())
    membership=[]
    for model in sorted(union):
        applicable=[k for k,s in sets.items() if model in s]
        membership.append({'model_key':model,'in_research_cohort_3328':'1' if model in cohort else '0',**{k:'1' if model in s else '0' for k,s in sets.items()},'applicable_scope_count':str(len(applicable)),'scope_labels':';'.join(applicable),'count_boundary':'仅清单型号层交叉；条件用途不同；不等于实缺字段/报告数量或法律资格'})
    write('条件需求_型号级交叉台账.csv',membership)
    write('条件需求_两两交叉数量.csv',[{k:v for k,v in r.items() if k!='intersection_model_keys'} for r in cross])
    jx_pdf=AUDIT/'round8/jx_public_final_pass/raw/recommend2021_10_parameters.pdf'
    jx_evidence=AUDIT/'round8/jx_public_final_pass/local_review/jx6550_local_review_result.json'
    assert json.loads(jx_evidence.read_text())['original_batch48_energy_cell_is_empty']
    write('JX_最后所需材料_具体系统询证线索.csv',[{'model_key':'JX6550T-M5BEV','tax_source_batch':'48','tax_record_id':'old-48-Word97--0-20','recommendation_config_id':'NC010086','system_variant':variant,'declared_density_whkg_public':density,'public_source_file':str(jx_pdf.relative_to(AUDIT)),'public_source_sha256':sha(jx_pdf),'public_source_page_1based':'73','same_configuration_bridge_verified':'0','needed_material':'公告前申报端配置对应证据；该系统总能量kWh及质量kg原申报页/检测报告、形成/申报日期、系统版本；如不属于第48批该条目，须明确不适用','closure_boundary':'字段证据真实可追溯即可闭合原空；多配置时可保留多值，不保证numeric_ready增加','cannot_substitute':'不能用声明密度×416倒算raw总能量，不能借用近似JX6570型号或2023-12-26能量','received_material':'','received_sha256':''} for variant,density in [('L173C01','158.98'),('L173G01','157.18')]])
    sources += [jx_pdf,jx_evidence]

    ledger=[]
    def add(gap,status,scope,count,unit,essential,needed,holder,when,criterion,estimate,estimate_condition,checklist,overlap):
        ledger.append({'item_id':gap,'status':status,'scope':scope,'count':str(count) if count is not None else '', 'unit':unit,'needed_for_current_catalogue_analysis':essential,'precise_remaining_evidence':needed,'holder_or_channel':holder,'needed_when':when,'closure_criterion':criterion,'work_after_receipt_planning_estimate':estimate,'time_condition_and_limit':estimate_condition,'detailed_checklist':checklist,'overlap_and_count_boundary':overlap})
    add('CORE_ORIGINALS','已可使用','历史原件',0,'缺文件','否','106份历史原件全部已同字节校验；97目录+9历史撤销，另新增撤销原件分别有来源证据','已取得','目录事件分析','本定义档案106/106；原表覆盖与源SHA可复核','本轮最后一致性核查即可','不声称互联网全部公告已穷尽','round5/source_recovery/source_recovery_summary.json','0缺原件不是0缺私人检测报告')
    add('CORE_ANALYSIS','已可使用','v1.5现有科学数据',0,'阻塞项','否','3328型号、119808月度行、2805风险、2425单值ready；使用字段勘误生效视图','已取得','现有目录状态和数值代理分析','冻结时点、空值、来源、事件/状态/参数版本边界通过；结论限定现有口径','本轮可自主结项','不认证完整技术、逐车或因果效果','round5/reconstruction/data_v1_5','380不足不是380原表未取得')
    add('JX_ONE_FIELD','真实原空','JX6550T-M5BEV第48批',1,'型号/电池总能量字段','仅若要补齐此型号冻结密度','公告前对应申报配置电池总能量kWh，来源/日期/配置依据；本轮推荐NC010086的L173C01/L173G01系统变体为询证线索，需配置桥及各系统能量/质量依据','申报企业或原检测机构、既有申报档案','处理该型号真实原空字段；是否形成单值输入需另审','得到2023-12-10前同配置有效依据即闭合字段证据；多配置时保留多值/区间，不承诺ready+1；不可density×416倒算原能量','资料有效且单页时0.5–1工作日','是收到后核验参考；材料取得日期无可靠承诺；公开声明密度不是检测报告','round8/final_gap_status/JX_最后所需材料_具体系统询证线索.csv','不与32/4/170/12/92/2208交叉；NC010086为新公开旁证，不擅自改原285配置版本表')
    add('CROSS_JOINT','条件需求','联合两项门槛仍跨界',32,'不同型号','否','具体配置、选项/公差定义、能量质量配对及公告前来源','申报企业、检测机构','要判定具体配置而不是保守外包络时','仅按收到的同配置证据缩小区间，不任意选点','结构清楚的完整对照表到齐后1–3工作日','排期参考；补测/授权/扫描件另评估，获取时间不含',str((REQ/LISTS['32联合跨界']).relative_to(AUDIT)),'与4完全不交；与身份型号交2、再申报交4、低温交1；与2208不交')
    add('CROSS_SINGLE','条件需求/可选细分','联合结果已低于、单项仍跨界',4,'额外不同型号','否','对应配置区间/选项含义，仅为细分单项层','申报企业、检测机构','确实需要各单项门槛结果时','把尚跨阈值单项用有来源的配置证据限定','通常可与32项并批','无需为已经确定的联合低于结果补证',str((REQ/LISTS['4单项跨界']).relative_to(AUDIT)),'4不包含在32中；共36但用途不同，不能都叫联合未知')
    add('CONFIG_IDENTITY','条件需求','推荐↔减免配置身份',285,'版本；278配置ID；170型号','否','申报配置桥、部件身份、有效时间、申报/报告版本和对应依据','企业认证部门或授权申报系统','用推荐参数认定减免同配置时','285版本各对应或有来源地标记不适用/仍未知；匹配不能只凭型号','先验首批材料后按格式和页数排期','无完整材料清单/可机读性，不提供总天数保证',str((REQ/LISTS['推荐配置身份']).relative_to(AUDIT)),'包含全部19低温版本；170型号与2208交113、92交9，不可加总')
    add('LOW_TEMP','条件需求','低温例外优先候选',19,'配置版本；12型号','否','匹配配置附录A报告、日期机构编号、常温低温里程/衰减、配置桥','企业、原检测机构','要认定低温例外时','报告与申报配置匹配并按政策核算；速度/能耗不放宽','收到对应电子报告首批后评估','19是待核候选，公开声明值不是报告；报告取得或补测工期未知',str((REQ/LISTS['低温例外']).relative_to(AUDIT)),'19版本是285的子集，不能再加19；12型号与2208交9')
    add('VEHICLE','条件需求','92再申报型号对应车辆',92,'型号；实际车辆数未知','否','匿名车辆键、配置、制造日期、开票日、重新列入事件、校验减免标识','车辆电子信息、发票、企业/税务授权业务系统','回答具体车辆是否享受减免税时','真实逐车对应重新列入日和实施条件；列明车辆覆盖分母','车辆数/格式明确后排期','92不是92辆，未知车辆数不能推算总工作量',str((REQ/LISTS['再申报逐车']).relative_to(AUDIT)),'92型号与2208交49、170身份交9；不加为新型号总量')
    add('TEST_CYCLE','条件需求','数值ready但未标试验工况',2208,'不同型号；对应配置/报告数量未知','否','公告前对应配置原报告的工况、标准/报告版本及日期、配置桥','企业、检测机构、授权产品档案','同工况可比分析或完整试验口径认定时','原试验口径有来源；未来CLTC不得替代公告前报告','先取得同格式样本后分批排期','217有CLTC标签也不是完整试验认证；2208不能换算报告数量',str((REQ/LISTS['公告前工况']).relative_to(AUDIT)),'与170身份交113、92逐车交49、12低温交9；与32/4不交')
    add('M1_AND_FOUR_REPORTS','条件需求','法定类别/完整技术资格的具体产品配置',None,'配置/车辆范围随研究目标确定','否','M1等类别及适用标准；同配置30分钟车速、续航、系统密度、能耗/质量申报或报告依据','产品公告/合格证/认证系统、检测机构','结论要认证法定类别或四项技术资格时','类别和技术证据与具体配置及有效时间对应','先定义对象并取得材料后排期','不能把3328研究型号或285声明值版本直接当作检测报告数',str((REQ/'配置技术资格与M1_所需证明字段规范.csv').relative_to(AUDIT)),'属于同配置/逐车认证证据内容；不能当额外一批型号叠加')
    add('FIRST_PUB','公开访问补证/可选','第1批原始登记公开日',1,'日期字段','否','主管部门原公告首次/原登记公开日期证据','主管部门原公告档案','完整发布日期档案审计','原始登记字段证据；落款、实施日、PDF创建日不替代','有有效原页时0.5–1工作日','公开历史档案能否获得无准确到达日期','round5/batch01/proof.json','1项档案字段，不是1车型科学原空')
    historical_standard_requests=read(REQ/'公开标准登记_可选待补字段.csv')
    assert len(historical_standard_requests)==4 and all(not r['value'] for r in historical_standard_requests)
    public=AUDIT/'round8/public_archive_final_pass'
    standard_path=public/'standard_registry_detail.html'
    standard_html=standard_path.read_text()
    assert re.search(r'发布日期</dt>\s*<dd[^>]*>2021-03-09</dd>',standard_html)
    assert re.search(r'实施日期</dt>\s*<dd[^>]*>\s*2021-10-01\s*</dd>',standard_html)
    assert re.search(r'部分代替标准</dt>\s*<dd[^>]*>\s*GB/T 18386-2017',standard_html)
    assert 'GB/T 18386.1-2021' in standard_html and "var STATE='现行'" in standard_html
    standard_meta_path=public/'standard_registered_metadata.json'
    standard_meta=json.loads(standard_meta_path.read_text())
    assert standard_meta['standard_number']=='GB/T 18386.1-2021'
    assert standard_meta['official_registered_publication_date']=='2021-03-09'
    assert standard_meta['official_registered_current_status']=='现行'
    assert standard_meta['predecessor_reciprocal_relation_verified']
    assert standard_meta['detail_evidence']['sha256']==sha(standard_path)
    assert standard_meta['registered_replaced_by_standards_displayed']==[]
    public_closed=[{'item':'standard_release_date','observed_value':'2021-03-09','status':'本轮已取得','source':str(standard_path.relative_to(AUDIT)),'source_sha256':sha(standard_path),'boundary':'具体2021版登记页发布日期'},
        {'item':'standard_implementation_date','observed_value':'2021-10-01','status':'本轮登记页再次确认','source':str(standard_path.relative_to(AUDIT)),'source_sha256':sha(standard_path),'boundary':'此前公告证据已有，本轮同标准详情页确认'},
        {'item':'standard_current_status','observed_value':'现行（2026-10-09观察）','status':'本轮已取得','source':str(standard_path.relative_to(AUDIT)),'source_sha256':sha(standard_path),'boundary':'是观察时登记状态，不把现在状态回填历史状态'},
        {'item':'replaces_standard','observed_value':'部分代替GB/T18386-2017','status':'本轮已取得','source':str(standard_path.relative_to(AUDIT)),'source_sha256':sha(standard_path),'boundary':'部分代替不能写成全面代替'},
        {'item':'replaced_by_standard','observed_value':'本次登记关系图未列后继（2026-10-09观察）','status':'本轮登记观察已取得','source':str(standard_path.relative_to(AUDIT)),'source_sha256':sha(standard_path),'boundary':'仅本次页面未列，不声称全网/未来永无替代'}]
    for c in public_closed:
        add('STD_'+c['item'],'本轮已取得','GB/T18386.1—2021 '+c['item'],0,'剩余登记字段','否',c['observed_value'],'国家标准官方登记平台','完整标准登记档案审计','原登记页与回执有SHA，范围按所观察字段限定','已完成','不作为继续等待的材料缺口',c['source'],c['boundary'])
    first_api=public/'tax_first_final_query.html'
    first_page=public/'first_batch_primary_registered_page.html'
    query=first_api.read_text()
    assert '2014-08-27' in query and 'pubDate' in query and 'cwrq' in query
    assert '2026-06-02 15:18:48' in first_page.read_text()
    first_meta_path=public/'first_batch_registered_metadata.json'
    first_meta=json.loads(first_meta_path.read_text())
    assert first_meta['registered_public_date_in_official_index']=='2014-08-27'
    assert first_meta['official_query_evidence']['sha256']==sha(first_api)
    assert first_meta['official_primary_page_evidence']['sha256']==sha(first_page)
    assert not first_meta['full_historical_first_online_time_verified']
    public_closed.append({'item':'first_batch_registry_api_pubDate','observed_value':'接口pubDate及cwrq均2014-08-27；正文成文8/27；HTML meta PubDate=2026-06-02 15:18:48','status':'法规库接口字段本轮已取得','source':str(first_api.relative_to(AUDIT))+'；'+str(first_page.relative_to(AUDIT)),'source_sha256':sha(first_api)+'；'+sha(first_page),'boundary':'接口字段已取得，不等于真实2014历史首次公开日独立获证；科学原日期不改'})
    write('本轮公开登记_已取得字段与边界.csv',public_closed)
    sources += [standard_path,standard_meta_path,public/'standard_registry_detail.receipt.json',public/'standard_replaced_2017_detail.html',public/'standard_replaced_2017_detail.receipt.json',first_api,first_page,first_meta_path,public/'first_batch_primary_registered_page.receipt.json',AUDIT/'round8/jx_public_final_pass/jx_public_final_pass_summary.json']
    standard=[]
    add('MARKET_OUTCOME','另一个研究目标才需要','真实销量/生产/注册登记/价格',None,'型号配置×月份；覆盖范围待定义','否','要研究的真实结果、分母覆盖、零值与未覆盖区分、型号配置桥与时间','企业、行业统计或授权数据源','继续研究市场政策效果时','先定义结果和观察范围，取得可连接来源并检验识别条件','目标与数据覆盖确定后排期','目录状态不替代真实结果；当前不扩采此目标',str((REQ/'需要用户亲自提供的数据.md').relative_to(AUDIT)),'不是当前目录核查尚欠若干条数据')
    write('最终剩余数据台账.csv',ledger)
    optional_text='仅剩第1批真实历史首次公开日独立证据。法规库接口pubDate=cwrq=2014-08-27字段已取得，但正文是成文日、HTML meta日期为2026-06-02，不能由此断言历史首次公开或该meta日期的形成原因。标准发布2021-03-09、实施2021-10-01、观察时现行、部分代替2017版及本次未列后继已取得，不再作为登记待补。'
    readme=f'''# 还差什么、多久能结束

**现有目录项目已可按 v1.5 口径使用。106 份历史原件全部齐备；3328 型号、119808 行月度面板、2805 风险型号和2425 单值数值可用型号均可复核。真正仍空的公告前科学原字段是1型号的1字段：JX6550T-M5BEV 电池总能量。** 其余是取决于研究目标的配置、检测或逐车证据，不能加成一个“还缺几千条”的总数。

| 要进一步完成的目标 | 尚需材料范围 | 是否阻塞现有目录分析 |
|---|---|---|
| 补JX原空字段 | 1型号1字段，及对应公告前配置/日期来源 | 仅该型号密度仍空 |
| 判定具体配置两项门槛 | 32型号联合跨界；另4型号只需单项细分 | 可先使用保守区间 |
| 推荐参数对应减免配置 | 285版本、278配置ID、170型号的身份桥 | 否 |
| 核低温例外 | 上述285中的19版本、12型号的匹配附录A报告 | 否 |
| 认定再申报逐车资格 | 92型号的逐车日期/配置/税标；车辆数未知 | 否 |
| 做同工况可比分析 | 2208数值可用型号的公告前试验工况和报告版本 | 否 |
| 认定法定类别/完整技术资格 | 目标产品/配置的M1等类别及同配置四条件证据 | 否 |

32与4不重合，共36个不同型号，但4个的联合“不满足”已确定。380个单值不足中，300个联合达到、47个至少一项必低，剩32个联合跨界加JX共33个联合数值结果未确定。无需为所有380个任意找点值。M1类别及同配置四项完整技术依据，只在结论要认证法定类别/技术资格时补；公开声明值不等于实际检测报告。

这些用途范围有交叉：19低温版本属于285身份版本；170身份型号与2208工况重合113个，92逐车型号与2208重合49个。完整交叉在[计数JSON](计数与交叉核查.json)。并集2333型号只是条件需求涉及对象，其中2331在研究队列、2为推荐参数旁证对象；不是强制缺2333字段、报告或车辆。

JX已找到官方推荐NC010086及L173C01/L173G01两系统线索，仍缺48批申报身份桥和原总能量；见[公开核查结果](../jx_public_final_pass/README.md)、[精确询证表](JX_最后所需材料_具体系统询证线索.csv)及[向企业索取材料模板](../jx_public_final_pass/向企业索取材料_文本模板.md)。下一步是江铃技术/认证部门或原检测机构提供依据。不能把声明密度乘416倒算原能量。有效匹配材料可以补证历史技术事实；若要进入公告前公开信息的冻结输入，还须核实其当时的信息可得性。若为多配置，仍保留多值，不保证numeric_ready再加1。

**时间：公开及本地最后核查、交叉计数和交付整理本轮收尾。** 企业/检测机构材料的取得日期目前无法可靠承诺。有效JX材料到位后，计划1工作日核验；32+4完整配置对照到齐后，排期参考约1–3工作日。大批285/19/92/2208材料须先确认授权、实际配置/车辆/报告数量和格式再排期。这些是收到后的工作估算，不是材料几天能拿到的承诺；条件扩展不作为当前结项必需。

可选公开档案余项：{optional_text} [本轮登记证据](../public_archive_final_pass/final_public_archive_summary.json)保留观察边界，不阻塞2023–2024目录状态分析；落款、实施日和PDF创建日不得替代首发日。只有继续研究销量/生产/登记/价格效应时，才另取真实结果及覆盖分母。

**结项标准：**现有科学版本固定，来源与计数可重现，raw与字段生效视图边界明确，空值/多值保留，已有输出经一致性核查并交付；私人证据按用途登记为待补，不把未知写成认证通过。最后自主检查包括当前版本指纹、清单与canonical集合、32+4及19子集、字段来源/日期、交叉去重和交付文件指纹，均由脚本完成。后续只有有效新材料到达或研究目标扩展才再开补证轮次。

逐项材料、关闭条件与时间依据见[最终台账](最终剩余数据台账.csv)，输入指纹见[核查来源](核查输入_SHA256.csv)。本轮没有重写科学CSV。
'''
    (OUT/'README.md').write_text(readme,encoding='utf-8')
    write('核查输入_SHA256.csv',[{'file':str(p.relative_to(AUDIT)),'sha256':sha(p)} for p in sources])
    summary={'generated_utc':datetime.now(timezone.utc).isoformat(),'canonical_version':'v1.5; round6/7 only review and version-label corrections','core':{'historical_originals':106,'missing_originals':0,'cohort_models':3328,'monthly_rows':119808,'risk_models':2805,'numeric_ready_models':2425,'numeric_insufficient_models':380,'same_legal_or_configuration_certification_implied':False},'true_original_blank':{'models':['JX6550T-M5BEV'],'fields':['battery_energy_raw'],'model_count':1,'field_count':1,'new_public_config_lead':'NC010086; L173C01/L173G01; no same-configuration bridge or original energy acquired','field_evidence_closed_does_not_guarantee_numeric_ready_increment':True},'interval_outcomes':dict(ic),'scope_row_counts':{k:len(v) for k,v in rows.items()},'scope_model_counts':{k:len(v) for k,v in sets.items()},'scope_models_outside_research_cohort':outside_cohort,'configuration_identity_distinct_config_ids':278,'joint_and_single_crossing_intersection':0,'joint_and_single_crossing_union':36,'lowtemp_versions_subset_of_identity_versions':True,'lowtemp_versions':19,'lowtemp_models':12,'conditional_scope_model_union':len(union),'conditional_scope_model_union_in_cohort':len(union&cohort),'union_boundary':'2333 distinct model keys (2331 cohort and 2 supplementary recommendation models) appearing in purpose-dependent scopes; not mandatory missing data/report/vehicle count','sum_of_scope_model_counts':sum(len(s) for s in sets.values()),'why_not_sum':'overlapping purpose scopes and incompatible grains; model coincidence does not certify same configuration/vehicle','pairwise_model_intersections':cross,'optional_public_pending_fields':['first_batch_historical_first_publication_date'],'public_fields_closed_this_round':public_closed,'estimated_source_acquisition_finish_date':None,'timeline_basis':'public/local last checks finish this round; source acquisition has no reliable arrival date; valid JX materials review planned one working day after receipt, not promise of numeric-ready increase','canonical_scientific_csv_mutated':False,'validation':'input hashes stable; copied-list counts, canonical risk/ready/panel counts, 380 classification scopes, exact lowtemp-version subset, every pairwise set intersection and new specific standard page fields all asserted'}
    assert all(sha(Path(p))==v for p,v in before.items())
    (OUT/'计数与交叉核查.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write('文件_SHA256.csv',[{'file':p.name,'bytes':str(p.stat().st_size),'sha256':sha(p)} for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='文件_SHA256.csv'])
    print(json.dumps({k:summary[k] for k in ['core','scope_model_counts','conditional_scope_model_union','joint_and_single_crossing_intersection','optional_public_pending_fields','canonical_scientific_csv_mutated']},ensure_ascii=False))


if __name__=='__main__':main()
