# 旧库详情连续续采：200 / 4497

最新剩余4297条。以[checkpoint](checkpoint.json)和[全部已取详情](details_readonly.jsonl)为准；本目录archive_review_summary及旧标准CSV是原首100阶段快照，不冒充当前全量复核。本轮当前来源/字节独立验证见[当前批次校验](../batch_independent_validation.json)。

`--limit N`是累计前N预算，复跑校验缓存后续取；0是完整4497。正常单worker，至少2秒间隔；访问拒绝保存断点停。详情applyId/uniqId为空时不虚构回显。固定输入来自相邻independent_old_review，旧列表原件位于[原公开视图](../../energy_registry_20261009/public_energy_registry/README.md)。

第101—200条复用用户已上传的DeepSeek原响应，经[逐条来源与原字节导入核查](../provider_import_review.json)后加入断点缓存。原收据、101次尝试和提供方时间保留在原目录；其TLS/匿名请求证明字段缺失，规范收据明确记为null，不声称这100条是本环境重新网络取得。
