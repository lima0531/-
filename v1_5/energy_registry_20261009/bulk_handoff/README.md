# 转给 DeepSeek：2208 型号官方能耗库批量核查

请按本包固定名单采集官方公开能耗记录，产出只读证据旁表。科学主表保持不变；先收齐证据，再由项目逐项决定能否使用。查询全部可见配置和日期，不先筛选“早于2023-12-10”的记录。

## 可直接复制的指令

1. **固定输入。**以 [2208精确请求型号名单.csv](2208精确请求型号名单.csv) 的 `model_key` 为唯一核心任务范围，恰好2208个不同型号；保留原始拼写，不删连字符或合并近似型号。原来源副本及SHA在 [inputs](inputs/2208型号_冻结来源旁表.csv)、[固定输入指纹](固定输入指纹.json)。`JX6550T-M5BEV` **不在这2208个数值齐备的型号里**：另做 [正对照](额外正对照_JX不计入2208.csv)，不将它计入工况缺口的关闭数量。
2. **先核对实际接口并复用快照。**正常入口为 `https://yhgscx.miit.gov.cn/`。新库 POST `https://yhgscx.miit.gov.cn/fuel-consumption-center/fuel-consumption-center/fcSearchCtr/queryNewList`、型号字段 `vehicleModel`；旧库同前缀 `/fcSearchCtr/queryList`、字段 `vehicleNumber`。本轮JX实测两库均HTTP200、`info.list/totalSize/pages/currentPage`，但**新库业务成功码为200，旧库为1**，不能统一按200判断失败。实测原响应在 [新库](inputs/schema_probe/JX_new_page1_response.json)、[旧库](inputs/schema_probe/JX_old_page1_response.json)。**分页必须用已验证的`currentPage`：原recipe的`pageNum=2`被忽略，仍回显第1页并重复原数据。**本轮 [新库第2页](inputs/schema_probe/new_current_page2_probe_response.json)、[旧库第2页](inputs/schema_probe/old_current_page2_probe_response.json) 用`currentPage=2`回显2且ID不同。示例新库首屏体 `{"currentPage":1,"pageSize":50,"vehicleModel":"JX6550T-M5BEV"}`；旧库改用`vehicleNumber`。**若项目已交付核验完整的指定公开`energyType=8/fuelType=8`筛选视图元数据，优先核对SHA/分页证明后本地匹配固定2208型号，避免再抓4416次同样数据；后续重点下载标签和旧详情。**没有可复用完整快照时才逐型号采集。保存实际默认状态/日期筛选；值8取前端及 [官方动态字典](inputs/schema_probe/official_fuel_type_dictionary_response.json) 所示“纯电动”，但这只是请求条件，不自动认证所有返回行真实纯电。响应`reportType=3`不能当请求selector：前端请求1/2与响应分类3不是同一代码域。
3. **两库分别验证全分页。**每个核心型号最终各有新、旧两项结果，即4416条“型号×库”台账；这不是4416次网络请求的要求。`collection_mode`记`direct_model`或`global_enumeration`，实际筛选另记`energyType/fuelType`。视图枚举复用须保留每页原响应和完整核验manifest，不能先把首屏总数当采完。对照总数、页数、**全部原行数**、回显页号和页内容；第2页须回显2，检查请求忽略/原页重复。不同ID数只做剖面，不要求等于总行数；新库同UUID、不同`abandonTime`真实状态行都保留。检查漂移/提前空页；未解释异常须停。旧`fuelType8`视图已发现返回`reportType1`的分类矛盾行：原行不删，另标不一致/未认证；这不证明真实动力类型，也不影响其作为原响应被保留。零命中仅描述成功完整的**指定公开筛选视图**，不能表示全库隐藏历史/全网没有资料。
4. **逐原行／状态版本保留所有字段。**配置、企业、备案号、uuid/uniqId/applyId、公告批次、质量、续航、消耗量、标准代码、`issueDate/createTime/submitDate/enableDate/activationDate/updateTime/abandonTime/overtimeCause` 等原值全保留；旧库保留`publicTime`和**整组**`workConditionVos`。不能只导出最新记录或首个工况，**也不能仅按UUID/备案号去重删行**。记录实体键=库+稳定ID；版本键再加完整原字段行哈希；发生项键另加快照、页号、0-based行序。行哈希用完整对象规范JSON（`sort_keys=True,ensure_ascii=False,separators=(',',':')`）的UTF8 SHA256，不删null、日期或状态。全字段相同的重复行也保留每次来源位置。不同实体ID数、不同全字段哈希数、原行发生数分别报；型号/质量相同不合并，跨库仅候选关联。无法确定全部历史版本则写实际可见范围。
5. **逐版本取原件／旧详情。**新库沿实际前端给出的公开引用下载非空完整标签原PDF，下载线索为同前缀 `/file/file/file/download?m=<实际fullLabel>&p=1`，保存SHA/页码/文本并核对型号和数据。旧库逐条取列表`applyId`，POST同前缀 `/fcSearchCtr/queryDetail`，体 `{"applyId":"<实际列表值>"}`；本轮该实际路径已取到 [2295详情](inputs/schema_probe/JX_old_detail_2295_candidate_response.json)、[2360详情](inputs/schema_probe/JX_old_detail_2360_candidate_response.json)，含字面标准和质量。保存JSON原响应、所用applyId、标准quote与JSONpointer；**详情可能不回传applyId/uniqId，仍须保留请求—列表映射。**不猜旧PDF直链，不把JSON详情称为官方PDF/检测报告。旧页面另有合法公开原件时再按实际路径取。PDF无引用、下载失败、验证码HTML、扫描件难读分别记状态；同字节可复用但每条记录都关联。
6. **分层提取标准、原工况代码、显式工况名。**逐标签/旧详情抄标准编号年版、原文、页码或JSONpointer；单独保留`workConditionVos`原`workConditionType`。`CATC`不能机械映射CLTC-P；“新的中国工况”也不是明确CLTC-P。标签仅写 `GB/T 18386.1—2021` 记“仅标准版本”；具体工况只采**该记录肯定声明按某工况测定**的适用原文。不能从比较/否定句抽名：JX“与NEDC工况略有差异”不能标显式NEDC。没有正式字典不把代码`5`推给其他记录，字典亦核代码域、车型类别、版次。
7. **守住时间和配置边界。**`issueDate`先称“接口原值”，没有官方释义不称“检测报告出具日期”；它早于冻结点不能证明此前公开。旧`publicTime="2023-06"`保持月精度，不虚构为6月1日，也不当试验日或历史首次公开。新库2024年`create/submit/enable/activation`及“老数据切换新油耗系统”并列标记，既不推“2021年已公开”，也不推“2024年前从未公开”。冻结输入需独立历史公开桥，跨目录同配置需正式对应桥，质量和续航相同不足。历史公开、同配置税桥、同工况可比、冻结输入替换flag在对应证明未取得时均为false。**另交版本冲突表：JX旧库22.8与新库19.2 kWh/100km确有差异，虽同型号/293km，仍保留各自版本；不强合并、不平均、不编造迁移原因。**
8. **不倒算能量，不误认低温报告。**电能消耗量×里程不能回填电池总能量；JX第48批空字段继续保留。标签中行业高/低温平均衰减不当作该配置低温检测结果或附录A报告；备案号不当检测报告编号。实际可下载的目标配置报告应另保留报告原件、编号、机构、标准、日期和配置桥，不能只抄一项百分比。
9. **温和、可恢复地采集。**单worker，请求间隔至少2秒，尊重服务端更长间隔。按100型号分批落盘，每页/文件写完再推进断点；重跑复用经SHA验证的已存响应和PDF。仅普通网络超时/5xx有限重试（至多2次、间隔加长）；遇验证码、登录要求、403或429，保存原响应，按服务端提示降速或停止受影响任务，交付已完成部分及未完成清单。不要绕过验证、轮换身份/IP或索取账户/token。
10. **一次交齐机器证据。**交付下述文件、全部原响应/原PDF、脚本、依赖版本、SHA清单、断点状态及简短结果。按型号、型号×库、配置记录、PDF各自统计；显式工况、仅标准版本、历史公开桥、同配置税桥分别统计，不用“备案记录数”冒充“2208缺口关闭数”。不要求用户回传登录token、Cookie、密码或浏览器账户。

## 交付文件约定

- `requests.jsonl`、`query_runs.jsonl`、`records.jsonl`、`label_evidence.jsonl`、`legacy_details.jsonl`、`version_conflicts.jsonl`：每行一个对象，分别遵循 [request](schema/request.schema.json)、[query-run](schema/query_run.schema.json)、[record](schema/record.schema.json)、[label-evidence](schema/label_evidence.schema.json)、[旧详情](schema/legacy_detail.schema.json)、[版本冲突](schema/version_conflict.schema.json) schema。对应 [CSV空表模板](templates/requests_空表模板.csv) 可以同时提供；CSV布尔值用 `true/false`，null用空单元格，数组/对象字段保存合法JSON字符串。
- `raw/requests/` 保存公开请求体，`raw/responses/` 保存**收到的原字节**（包括错误/验证码HTML），`labels/` 保存原PDF，`text/` 保存提取文本及定位。表里使用包内相对路径；实际未收到字节时SHA填null，不填空响应SHA冒充响应。
- `delivery_manifest.json` 遵循 [交付manifest schema](schema/delivery_manifest.schema.json)，逐文件记录路径、字节数、完整SHA256，统计全部实际网络请求、完成/错误/截断/未尝试数。清单自身不列入自身SHA；别丢掉零命中型号。每个核心型号必须有新、旧库两项结果，包括被阻断或尚未尝试的结果。
- 另交 `schema_probe/`（实际新旧接口/页面模式依据）、`checkpoint.json`、可复跑采集脚本和依赖版本、`summary.md`。报告本次访问时间（UTC及北京时间）和真实接口可见范围。未知、未证字段留空或false；不要推填。

用户JX附件给出两个新库记录及一个完整标签；项目本轮还实际取得旧库两个记录/两份JSON详情。旧`publicTime=2023-06`、原工况码CATC、标准`GB/T 18386.1-2021`与新`issueDate=2021-09-30`、2024年迁移字段分别保留。旧22.8与新19.2消耗量冲突不抹平。JX核心电池总能量仍缺；这不等于已关闭历史冻结工况缺口。本任务包生成脚本没有请求网络，也没有修改科学输入。

## 优先级与其他清单串联

2208输入已标出其他用途交叉，实际为**与36配置型号交叉0、与285身份版本涉及型号交叉113、与19低温版本涉及型号交叉9**；可先处理113身份交叉型号，再跑完整名单。**285是版本数、19是版本子集；能耗记录与它们不是天然一对一。**原推荐配置ID和原件定位见 [285版本参考](inputs/285版本_身份与低温用途参考.csv)。能耗字段没有NC配置键时，不能用同型号替代配置对应证明。

[不在2208内的可选型号](不在2208内_其他用途可选精确型号.csv) 只服务其他用途，必须独立报告，不能改变2208分母。JX正对照也独立报告。拿到完整标签并不保证能解决公差、能量、跨目录身份或低温报告缺口。

复建此包可执行 `python build_spec.py --workspace /workspace`；源附件及已冻结旁表按 [固定输入指纹](固定输入指纹.json) 定位。输出文件自身指纹见 [SHA清单](文件_SHA256.csv)。
