# 官方能耗系统匿名查询：本环境实际复现

观察：2026-10-09。本目录的普通POST查询及公开标签GET均未提交账户、Cookie、滑块答案或其他身份凭证。JX新版查询实际HTTP200、业务result=200，返回两条记录；原JSON与用户提交5325字节快照逐字节一致。两条完整PDF也分别由对应公开引用成功取回，2295kg标签是本轮新增原件。

| 新版备案号 | 整备质量 | 完整标签 | 字节数 |
|---|---:|---|---:|
| GD20240715105558048 | 2360kg | [原PDF](JX_2360_full_label_response.pdf) | 80946 |
| GD20240715105576581 | 2295kg | [原PDF](JX_2295_full_label_response.pdf) | 80956 |

两PDF各自明确GB/T18386.1—2021，均293km、19.2kWh/100km、120kW、启用2024-07-15；不从代码5或第一份PDF替第二份映射标准。它们无电池总能量及2021年出具日期。高温15%、低温40%是“行业续驶里程平均约下降”，不是车型实测结果。详见[双引擎独立复核](../independent_pdf_review/live_label_pair_review.md)。

## 新旧记录各自保留

旧版`queryList`实际HTTP200、result=1，返回两个JX的M1记录，`publicTime="2023-06"`（月精度）、`workConditionVos`原工况代码`CATC`、293km、**22.8kWh/100km**。对两条实际applyId再POST`queryDetail`成功，分别2295/2360kg，原文字面标准均GB/T18386.1-2021，并有“本车型能耗、里程基于新的中国工况，与NEDC工况略有差异”。这句不能标为NEDC，也不把CATC自动转成CLTC-P。

[2360旧详情](JX_old_detail_2360_candidate_response.json)和[2295旧详情](JX_old_detail_2295_candidate_response.json)均是公开原JSON。旧版完整标签按钮实际上进入`oilDetail`页面读取`queryDetail`并打印，不能把源码中注释的`downloadEnergyConsumptionMark`当作已验证PDF下载口。

新版电耗19.2与旧版22.8不一致。相同型号、质量、续航只构成候选连接，未证明同申报配置或同版本；不拼接为一条。旧`publicTime`与新`issueDate=2021-09-30`也分别保留，不能把它们合称检测报告日期或首次公开日期。

GTM6470BFEBEV新旧库各返回两条615/400km记录；CC7000CG00FBEV两库本次均为零，严格限定这两个请求的可见范围。GTM、CC及JX均不在2208数值齐备清单，作为其他配置用途或查询对照单列，不能用它们直接减少2208。

## 已实际抓到的参数问题

- `pageNum=1`可以得到默认第一页，但另请求`pageNum=2`仍回显`currentPage=1`且与第一页逐字节相同。失败分页对照及停机状态保存在[完整枚举目录](../public_energy_registry/README.md)。**正式分页须用`currentPage`**；本目录实际`currentPage=2`的新旧响应都回显2，且内容与第一页不同。成功首屏不能证明分页参数有效。
- 请求中的`reportType`选择域与返回行的`reportType`代码域不同。请求`reportType=3`没有实现纯电筛选，实际返回混合1/2/3行；这些探针不用于认定纯电全库。新高级筛选正常字段`energyType="8"`已由前端及实际返回验证。
- 旧`fuelType`是动态字典。[实际官方字典响应](official_fuel_type_dictionary_response.json)确认`FC_FUEL_TYPE`的`dictCode="8" / dictName="纯电动"`，旧高级筛选使用`fuelType="8"`。筛选视图仍须保留分类矛盾行，不把筛选条件本身当成每行车型资格证书。

每次请求均有独立receipt：完整实际URL、方法、请求JSON、UTC时间、TLS验证、HTTP/业务状态、原响应长度及SHA。`m=`是官网公开文件引用，不是账户登录凭证。HTTP200之外还校验JSON业务结构或PDF内容，不能将错误页记成零命中。

`collect_pilot.py`为有限样本复现脚本，经SHA校验复用缓存；其JX首页配方保留`pageNum=1`用于复现用户原请求，**不作后续分页示例**。全量正确分页脚本位于[registry](../public_energy_registry/collect_registry.py)。本目录其他模式探针的请求配方以相应原receipt为准，不重复请求它们。

本轮当前取得官方资料的事实已推翻此前“本环境未取标签”的能力判断。前端确有滑块组件和正常UI动作，但本次匿名查询接口未要求提交验证；不能把UI观察泛化为所有查询的接口前置条件。遇到接口明确验证码、登录或访问限制时仍应停下，不能绕过。

全部材料先入旁表。JX在风险集380单值不足中，不在2208里；核心1型号1能量字段、冻结工况清单及跨目录身份认证均未据此改写。详见[总报告](../README.md)与[范围独立复核](../independent_scope_review/README.md)。
