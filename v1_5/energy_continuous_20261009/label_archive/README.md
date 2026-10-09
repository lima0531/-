# 新库标签官方原件归档

原字符串严格匹配主队列。

固定2208型号清单本口径命中 539 型号、936 条全行记录；按实际公开 fullLabel 标识去重后 936 份标签，全部记录状态仍保留。

截至 2026-10-09T16:04:24.389036+00:00：实际HTTP200、SHA一致、PDF魔数和PyMuPDF验证通过 500 份，覆盖 500 条记录、325 型号；完成标志 False。停止原因：planned_review_stage_boundary: accepted 500 of 936; resume available。

来源页、JSON pointer、全行哈希和每次HTTP尝试均保留；同uuid的状态版本不合并。标签实际全文及标准所在原句逐PDF保存，不因代码5或6而泛化标准映射。issueDate、enableDate、createTime、abandonTime按原始字段保留；issueDate不等于原试验报告日期或历史公开可取得日期。

本旁表不认证与免征目录的配置身份、冻结点同工况资格、低温试验报告或逐车税收资格；不以电耗乘续航回填电池总能量，不改变52张科学CSV及2208待核口径。

正常匿名GET、TLS验证、单worker、请求间隔至少2秒；401/403/429及HTTP200非PDF立即停，仅网关5xx/超时最多共3次尝试。公开fullLabel是文档标识，不需要账户令牌。

复跑：`python collect_matched_labels.py`。脚本只采用receipt与原件SHA一致且仍能解析的成功缓存，遇到已留存的访问拒绝不会继续请求。`--prepare-only`仅重建队列，不访问网络。
