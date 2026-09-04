# Linux / NVIDIA 迁移验收

## 环境门槛

1. `docker compose up -d` 后 `/readyz` 返回 HTTP 200。
2. readiness 中 CUDA、FFmpeg/ffprobe、五个活动权重、buffalo_l、同步配置、空间和空帧推理全部为 `ready=true`。
3. 容器启动和任务运行期间断网，确认不会尝试下载模型。
4. 人为移除任一模型、buffalo_l 或同步文件时，创建真实任务返回 503；禁用 GPU 时同样失败。

## 基线重跑

分别通过页面对 `quick-demo`（group4）和 `verified-outcome`（group5）执行完整重跑，再各跑一次快速模式。每次记录：镜像 ID、GPU 型号、驱动、耗时、峰值显存、任务日志和 report SHA-256。

同时保存容器内 `python3.10 -m pip freeze`；首版镜像锁定 PyTorch 2.5.1/cu124、TorchVision 0.20.1，以及 `requirements-gpu.txt` 中的关键推理库版本。任何版本升级都必须重新执行本清单并记录新镜像摘要。

同次运行的产品 DTO 必须以该任务的 `report.json` 为准，四类动作计数与 report clips 完全一致。不得拿过期顶层 manifest 作结果来源。

## v3 回归阈值

运行 `python scripts/validate_v3_presets.py`。要求：

- group3 precision ≥ 0.963、recall = 1.0；
- group5 precision ≥ 0.944、recall = 1.0；
- group4、group6 precision = recall = 1.0；
- group5 outcome truth 保持 17/17；
- 四个预置组均有五个可 Range 播放的视频。

这些数字只对应 v3 固定测试集。

## 产品边界

- 产品结果 JSON 与事件文本不包含 `stu_`、`student_id`、内部 session id 和绝对路径。
- 四宫格复核视频说明画面标签只是“会话内匿名编号”；画面本身允许保留预计算的 `stu_XX`。四路单独视频为各机位原片。
- group2 类似的“16 个上篮动作、17 次球轨出手”必须正常展示，页面不暗示两者一一对应。
- 引擎产生 pass/unknown 时不误归类，`unsupported_event_count` 增加并出现当前版本不支持提示。
- 五个播放器都能播放、拖动并返回正确的 206 Range。

## 恢复与保留

- 重启容器：queued 保留，活动任务变为 interrupted；retry 使用原输入。
- 验证取消子进程、失败重试和删除任务。
- 验证 gallery 7 天、上传/raw 30 天、结果 180 天；只读预置不被清理。

## 本次 AutoDL RTX 4090 实测（2026-09-03）

非 Docker 部署：`/root/autodl-tmp/dashanbing-backend`，PyTorch 2.5.1+cu124，驱动 580.76.05。四次推理执行时的 Git 基线为 `990ffa5`，工作区另有当时尚未合入的生命周期修复；这不是当前部署版本声明。原始 JSON 在运行机 `/root/autodl-tmp/gpu-acceptance-results.json`。

| 任务 | 模式 | 墙钟 | 原参考 | 峰值显存 | report SHA-256 | 动作 / 球轨 | v3 评估 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| group4 `e3957663` | 完整 | 21.84 min | 9.4 min | 3705 MiB | `a92ac3b767f573ea13885339f09967c92a404effb2f452b23c6a262dde0157d1` | 跳投 4；4 次（2/2） | precision/recall 1.0/1.0，4/4 |
| group5 `1e850982` | 完整 | 75.89 min | 30.9 min | 3703 MiB | `717fa47c28598019d092a8a08095d8a6703a5c190d6de5ca123a3232af9542e2` | 罚篮 18；18 次（11/7） | precision/recall 0.944/1.0，outcome 17/17，fa=1 |
| group4 `db21082b` | 快速 | 16.29 min | — | 4671 MiB | `254c241a65c59671023d31a20e38d023cd8ead543f9d93116bb6a4dccd0c4d2d` | 跳投 4；4 次（2/2） | precision/recall 1.0/1.0，4/4 |
| group5 `02e370df` | 快速 | 55.67 min | — | 5139 MiB | `0dc46fb24e890f5bc5c5252fda44395436fade7b54e13d9be3d5d2375d883802` | 罚篮 18；18 次（11/7） | precision/recall 0.944/1.0，outcome 17/17，fa=1 |

四次运行的产品 DTO 动作计数均与同次 `report.json` clips 一致，公开 JSON 不含 `stu_` / `student_id`。推理输出生成处理后的 `phases.mp4`；在原片交付修复后，又对已完成的 group5 快速任务验证了四路输入原片加 `phases.mp4` 共五个媒体端点均支持 HTTP 206 Range。group5 的 18 个预测片段中 17 个匹配真值（允许 1 个 false alarm），命中对错 17/17。本机耗时约为原科研环境的 2.3–2.5 倍，峰值显存远低于 24 GiB。

这只证明固定 v3 测试集在该 GPU 上可复现，不覆盖现场四机位同步实测，也不覆盖任意自定义上传。
