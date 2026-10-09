# 旧库分页及重试独立复核

只读重核通过：47个有效页、9,336原始行、9,336唯一applyId，与用户交付的旧库核验文件逐页一致。47页的实际字节、SHA256、收据、请求页码、业务result=1、回显页码及页长全部通过；最后一页136行。两次失败加重试共49个已保存收据；其中48个有响应字节，其字节和SHA均核验，另一个超时无响应原件。

第10页首次为HTTP503、95字节、非JSON网关文本。第17页首次则是TimeoutError，只有收据、无HTTP状态和响应字节；不能写成“同样503/95字节”。checkpoint明确采用两页各自attempt02：HTTP200、result=1、页码正确、200行。此差别不影响用户旧库逐页JSON核验结果及9,336总行数。

不能只按默认首次文件计数，也不能用“任何可JSON解析尝试”作为成功标准。若一页出现多个有效但字节不同的尝试，应保留各次观测边界并核查，不能自动拿最新文件拼接成同一事务快照。本轮每页只有一个有效尝试，未发生此歧义。

从原始页重新进行原字符串精确匹配：2,208目标中命中1,233型号、4,497记录；JX6550T-M5BEV不在该2,208名单。输出集合可与新库集合计算交、并、差，不能将两库型号数量直接相加。原工况代码不映射为标准版本，不证明同免税配置，也不证明公告前公开可得；冻结工况清单关闭数仍为0。fuelType=8筛选视图包含原有响应分类异常，不将每一行认证为纯电车型。

本复核不请求网络、不修改原数据；52份冻结科学CSV均与gold指纹一致。请求观测窗口见review.json；checkpoint的started_utc是续采启动时间，早于此时的缓存页仍保留各自真实observed_utc。公开筛选视图分页采集不具有事务原子性，也不证明隐藏或全部历史备案已收齐。

- [复核明细](review.json)
- [1,233型号集合](1233型号_旧库精确命中集合.csv)
- [4,497记录及固定来源键](4497记录_旧库精确命中固定来源键.jsonl)
- [可复跑脚本](review_old_snapshot.py)
- [输出SHA清单](文件_SHA256.csv)

固定来源键采用old:applyId:全行SHA256；来源位置另保留old:page:零基行号、原页文件、JSON Pointer、原页SHA及请求观测时间。全行SHA使用Python json.dumps(record, ensure_ascii=False, sort_keys=True)的UTF-8字节（默认空格），与既有旁表一致。

复跑时可传--registry-root、--targets、--user-review、--golden、--science-root及--output。脚本只在--output目录写复核产物；原库及名单均只读。仓库已有[原旧库及checkpoint](https://github.com/lima0531/-/tree/purchase-tax-v1-4-files/v1_5/energy_registry_20261009/public_energy_registry)及[2,208型号名单](https://github.com/lima0531/-/blob/purchase-tax-v1-4-files/v1_5/energy_registry_20261009/bulk_handoff/2208精确请求型号名单.csv)。
