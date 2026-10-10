# 新库标签官方原件归档

原字符串严格匹配主队列。

固定2208型号清单本口径命中 539 型号、936 条全行记录；按实际公开 fullLabel 标识去重后 936 份标签，全部记录状态仍保留。

截至 2026-10-10T13:33:59.349570+00:00：实际HTTP200、SHA一致、PDF魔数和PyMuPDF验证通过 728 份，覆盖 728 条记录、450 型号；完成标志 False。停止原因：{"label_job_id": "6b593a6719ffce451a037818c46166ec2284f0fb5282e71481187941d5a68d8b", "fullLabel": "4323c00818cf0a1a421b5fb9c029a874@231317", "attempt": 1, "method": "GET", "requested_url": "https://yhgscx.miit.gov.cn/fuel-consumption-center/fuel-consumption-center/file/file/file/download?m=4323c00818cf0a1a421b5fb9c029a874%40231317&p=1", "observed_utc": "2026-10-10T13:33:51.769001+00:00", "tls_verified": true, "no_credentials_or_captcha_solution_submitted": true, "accepted": false, "record_reference_count": 1, "http_status": 200, "content_type": "application/pdf;charset=UTF-8", "final_url": "https://yhgscx.miit.gov.cn/fuel-consumption-center/fuel-consumption-center/file/file/file/download?m=4323c00818cf0a1a421b5fb9c029a874%40231317&p=1", "bytes": 231317, "sha256": "70b207a1a8cb5b8a7610599db3b4cdcdd9ba888ad31a989b3336ec121ab14847", "response_file": "responses/6b593a6719ffce451a037818c46166ec2284f0fb5282e71481187941d5a68d8b_attempt01.pdf", "finished_utc": "2026-10-10T13:33:59.292670+00:00", "stop_boundary": "HTTP200 invalid PDF: PDF encrypted or empty"}。

来源页、JSON pointer、全行哈希和每次HTTP尝试均保留；同uuid的状态版本不合并。标签实际全文及标准所在原句逐PDF保存，不因代码5或6而泛化标准映射。issueDate、enableDate、createTime、abandonTime按原始字段保留；issueDate不等于原试验报告日期或历史公开可取得日期。

本旁表不认证与免征目录的配置身份、冻结点同工况资格、低温试验报告或逐车税收资格；不以电耗乘续航回填电池总能量，不改变52张科学CSV及2208待核口径。

正常匿名GET、TLS验证、单worker、请求间隔至少2秒；401/403/429及HTTP200非PDF立即停，仅网关5xx/超时最多共3次尝试。公开fullLabel是文档标识，不需要账户令牌。

复跑：`python collect_matched_labels.py`。脚本只采用receipt与原件SHA一致且仍能解析的成功缓存，遇到已留存的访问拒绝不会继续请求。`--prepare-only`仅重建队列，不访问网络。
