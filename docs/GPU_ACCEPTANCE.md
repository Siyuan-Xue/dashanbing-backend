# Linux / NVIDIA 迁移验收

## 环境门槛

1. `docker compose up -d` 后 `/readyz` 返回 HTTP 200。
2. readiness 中 CUDA、FFmpeg、五个活动权重、buffalo_l、同步配置、空间和空帧推理全部为 `ready=true`。
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
- 复核视频区域说明画面标签只是“会话内匿名编号”；画面本身允许保留预计算的 `stu_XX`。
- group2 类似的“16 个上篮动作、17 次球轨出手”必须正常展示，页面不暗示两者一一对应。
- 引擎产生 pass/unknown 时不误归类，`unsupported_event_count` 增加并出现当前版本不支持提示。
- 五个播放器都能播放、拖动并返回正确的 206 Range。

## 恢复与保留

- 重启容器：queued 保留，活动任务变为 interrupted；retry 使用原输入。
- 验证取消子进程、失败重试和删除任务。
- 验证 gallery 7 天、上传/raw 30 天、结果 180 天；只读预置不被清理。
