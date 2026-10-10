# 官方能耗证据连续续采

状态：**stopped_at_recorded_boundary**。更新UTC：2026-10-10T13:33:59.838619+00:00（北京时间＝UTC＋8小时）。

| 固定自动队列 | 累计已归档 | 待取 |
|---|---:|---:|
| 新库原样精确标签 | 728 / 936 | 208 |
| 旧库匹配applyId详情 | 200 / 4497 | 4297 |

{"label_job_id": "6b593a6719ffce451a037818c46166ec2284f0fb5282e71481187941d5a68d8b", "fullLabel": "4323c00818cf0a1a421b5fb9c029a874@231317", "attempt": 1, "method": "GET", "requested_url": "https://yhgscx.miit.gov.cn/fuel-consumption-center/fuel-consumption-center/file/file/file/download?m=4323c00818cf0a1a421b5fb9c029a874%40231317&p=1", "observed_utc": "2026-10-10T13:33:51.769001+00:00", "tls_verified": true, "no_credentials_or_captcha_solution_submitted": true, "accepted": false, "record_reference_count": 1, "http_status": 200, "content_type": "application/pdf;charset=UTF-8", "final_url": "https://yhgscx.miit.gov.cn/fuel-consumption-center/fuel-consumption-center/file/file/file/download?m=4323c00818cf0a1a421b5fb9c029a874%40231317&p=1", "bytes": 231317, "sha256": "70b207a1a8cb5b8a7610599db3b4cdcdd9ba888ad31a989b3336ec121ab14847", "response_file": "responses/6b593a6719ffce451a037818c46166ec2284f0fb5282e71481187941d5a68d8b_attempt01.pdf", "finished_utc": "2026-10-10T13:33:59.292670+00:00", "stop_boundary": "HTTP200 invalid PDF: PDF encrypted or empty"}

单worker、至少2秒间隔，先余下标签，再余下旧详情；按100条一批落盘、来源/SHA/双文本引擎核验并提交同一分支。本轮由[GitHub云端任务](https://github.com/lima0531/-/actions/runs/38055756530)执行，关闭聊天不影响该任务。每100条核验后提交本分支；页面计数仅代表最后一次成功发布。任务最多运行330分钟，完成队列、遇访问边界或本地/发布异常时停止。若被取消或达到任务时限，使用仓库Actions页面的Run workflow从已提交断点恢复；最后一次running不等于此刻仍在线。 网络拒绝、登录/验证码、429等保存断点并停，不切换路由或凭证。

以首100实测节奏，剩余公开原件约数小时；这不是全部科学缺口闭合时间。新库53页不重复采，复用已核验原字节；2条BMW空白候选保留在原阶段，不增加936口径。两库并集1246与被冻结的2208缺口不同。历史配置身份、历史公开时间、低温或逐车资格未经认证，不修改主CSV。JX历史电池总能量仍需企业/检测机构材料。

每份新PDF使用自身标准原文，不按代码/年份推工况；旧详情的空applyId/uniqId保留，不能虚构唯一回显。每批保护52份科学CSV和7个已有ZIP原SHA，原阶段包不重打。

- [机器状态与真实计数](job_status.json)
- [本批独立字节及来源核验](batch_independent_validation.json)
- [新标签、原件与剩余队列](label_archive/README.md)
- [旧详情、原件与剩余队列](old_details/README.md)
- [固定旧库输入](independent_old_review/README.md)
- [首100＋2及新库完整验收](../energy_new_complete_20261009/README.md)
- [实际运行脚本](run_continuous.py)
- [输出SHA清单](文件_SHA256.csv)

运行：仓库Actions页面可手动运行`Continue official energy evidence`；或在已有原仓库checkout中执行`python v1_5/energy_continuous_20261009/run_continuous.py --batch-size 100`。需Python/PDF依赖、正常公开网络；自动提交需已有GitHub写入连接。不需要官网账户凭证。`--no-publish`仅采集与本地验证，不提交Git。当前是否运行以实际Actions任务或本地进程为准，checkpoint是已保存证据的观察时间。
