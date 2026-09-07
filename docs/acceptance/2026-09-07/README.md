# 2026-09-07 验收证据索引

统一代码基线：`eff724d27266112bac12594ed367fed0d221c4f2`

正式结论见 [验收记录](../../release-acceptance.md)，产品范围见 [能力说明](../../release-capabilities.md)。本目录保留脱敏结果与代表截图，原始失败没有删除，未追加修复复测

| 材料 | 文件 |
| --- | --- |
| 汇总与逐项数据 | [summary.json](summary.json)、[page-measurements.json](page-measurements.json) |
| 后端全部结果 | [JUnit](raw/backend-tests.xml)、[日志](raw/backend-tests.log) |
| 前端全部结果 | [单元测试](raw/frontend-unit.json)、[E2E](raw/frontend-e2e.json)、[构建日志](raw/frontend-build.log) |
| 失败逐项归因 | [failure-triage.md](failure-triage.md) |
| 真实 Chrome | [300 页面与 40 组角色检查](raw/chrome-summary.json) |
| 真实 Safari | [Mac](raw/safari-mac.json)、[iPhone](raw/safari-ios.json) |
| 1/5/10/20 用户负载 | [全部 720 次请求与进程采样](raw/capacity.json) |
| GPU | [八项未执行结果](raw/remote-gpu-results.json)、[预检阻塞](raw/remote-gpu-readiness.json)、[硬件快照](raw/remote-gpu-hardware.json) |
| GLM | [实际调用原始计时](raw/remote-glm-calls.jsonl)、[预置作业元数据](raw/remote-glm-preset-jobs.json)、[测量来源](raw/remote-glm-preset-enqueue.json) |
| 恢复 | [完整隔离演练](raw/recovery-drill.json) |
| 环境与源文件 | [本机](raw/environment.json)、[远端](raw/remote-environment.json)、[前端源文件哈希](raw/frontend-source-manifest.json)、[GPU 源包哈希](raw/gpu-source-manifest.json) |
| 文件校验 | [checksums.json](checksums.json) |

代表截图是浏览器实际输出，未模拟产品结果；亮色遮挡块为测试账号字段的采集遮罩

- [管理员桌面概览](screenshots/admin-overview-admin-1440x900-zh-light.png)
- [管理员手机排版缺陷](screenshots/admin-users-admin-390x900-en-dark.png)
- [手机创建任务](screenshots/new-user-390x900-zh-light.png)
- [首页](screenshots/home-anonymous-1440x900-zh-light.png)
- [Mac Safari 中断现场](screenshots/safari-mac-interrupted.png)
- [iPhone Safari 中断现场](screenshots/safari-ios-interrupted.png)

完整 300 张页面截图、40 组角色截图、逐页几何/资源计时与原始日志仍保留在验收工作树的 `runtime/release-closeout/ui-final-chrome/`。Safari 与恢复的原始数据在同级对应目录，未将隔离数据库或视频纳入 Git。Git 版本中的文本只替换本机绝对路径、设备标识和终端颜色码，测试状态、数字和失败内容保留

可复用工具：

- `scripts/run_closeout_preview.py` 创建隔离网页/API 测试库
- `scripts/serve_closeout_phone.py` 临时私网真机代理
- `scripts/verify_safari_product_flow.py` 真实 Safari 草稿与同步流程
- `frontend/scripts/capture-closeout.mjs` 页面矩阵与角色边界，说明见 `frontend/scripts/README-closeout.md`
- `scripts/measure_capacity.py` 只读多用户负载，`scripts/measure_gpu_acceptance.py` 八组 GPU 测量
- `scripts/run_closeout_gpu.py` 新建独立 GPU/GLM 实例，`scripts/closeout_glm_metrics.py` 脱敏真实调用计时
- `scripts/release_recovery.py` 显式离线快照、校验与恢复

执行脚本需要显式选择隔离目录、账户与执行开关；本索引不触发任何任务，也不要求在生产环境重跑
