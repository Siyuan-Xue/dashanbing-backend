# 预置结果一致性修复（2026-09-06）

旧 v3 导入包的最终动作已筛选并重新编号，但 `shot_outcomes` 仍保留旧编号及部分旧球员归属，根 manifest 也未同步更新。仅按编号关联会把投篮结果挂到其他动作上，甚至挂到三威胁动作上

修复范围为共享预置包，不重跑用户上传任务，不修改命中模型判断或动作时间

| 示例 | 最终动作 | 投篮统计 | 修复内容 |
| --- | --- | --- | --- |
| 快速演示 | 4 次跳投 | 4 次、2 中、2 未中 | 无数据修改 |
| 混合动作 | 15 次三威胁、12 次跳投 | 12 次、4 中、8 未中 | 校正 12 条结果的对应关系，其中 9 条编号或球员发生变化，索引从 30 改为 27 个动作 |
| 命中验证 | 18 次罚篮动作 | 17 次已有投篮判断、10 中、7 未中 | 索引从 17 改为 18，不为额外动作虚构命中判断 |
| 上篮演示 | 6 次上篮 | 6 次、5 中、1 未中 | 校正 6 条结果的对应关系，索引从 12 改为 6 个动作 |

`scripts/repair_v3_presets.py` 只接受两份已核对原始 report 的 SHA-256。使用已有摄像机同步，将球轨迹时间转换为动作时间；每条结果必须在出手后 0–3500ms 内找到唯一的同类动作，并且与最终投篮片段一一对应。该范围仅用于这两组已复核样例的离线修复，不作为线上任意视频的自动重关联算法

修复同时同步 report、motion 中的结果副本、旧 dashboard JSON/HTML 及 manifest，保留原始命中值、置信度、轨迹信息、动作和 motion 帧记录。先在副本中执行检查，再生成报告并发布完整文件集

```sh
python scripts/repair_v3_presets.py --sample-root /path/to/sample/data
python scripts/repair_v3_presets.py --sample-root /path/to/staging/data --apply --backup-dir /path/to/new-backup
python scripts/validate_v3_presets.py --sample-root /path/to/staging/data
python scripts/generate_analyst_presets.py --presets mixed-actions layup-demo --locales zh en
```

应用备份目录必须不存在，重复执行或源文件发生漂移会拒绝覆盖。真实报告以修复后 facts hash 校验，旧报告不能作为新结果返回，只有受影响的版本需要重新生成

线上读取共用 `outcome_links.py`，检查唯一片段编号、已有球员信息、动作类型；对带科研时钟来源的数据检查明显时间冲突。缺少时钟信息的旧接口仍兼容原有编号关联，不臆测其他片段。无可靠关联保留未知，冲突判断显示未确定，总体原始统计保持独立。该检查是防止错误关联的保护，不能代替源输出的一致性验收

验收包括：四组最终结果无一致性警告、所有已有投篮判断正确关联、三威胁没有命中结果、个人投篮统计汇总与全场一致（存在无判断动作时保留未知）、原始用户任务未被预置修复改变，及中英文、两种语气、全场/个人报告的事实 hash 和引用检查
