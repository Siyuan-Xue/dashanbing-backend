# 篮球课堂训练复盘（本地产品版）

这是一个同机部署的 FastAPI + React 多机位篮球训练复盘产品。注册用户上传 1 段注册视频和四路动作视频，系统串行使用一张 NVIDIA GPU 完成匿名参与者注册、四类动作识别、球轨投篮统计与复核视频导出，最终网页只绑定 `127.0.0.1:8000`。

首版公开动作只有：三威胁/突破、罚篮、跳投、上篮。传球、个人评分、3D 技术结论、关节角和科研诊断数据都不对外展示。动作次数与球轨出手次数来自两套检测结果，不保证一一对应。

## 使用结果

登录后可以：

- 秒开四个 v3 预计算样例，或使用 GPU 重新分析样例；
- 上传标题、快速/完整模式及五个视频文件；
- 自定义上传支持 MKV、MP4、MOV、WebM；浏览器先做容器签名提示，服务端再用容器签名与 `ffprobe` 双重校验；
- 查看排队、注册、人体感知、球跟踪、同步、动作识别、命中判定、导出和可视化进度；
- 查看班级汇总、匿名动作时间线、投篮汇总以及四宫格标注复核与四路机位原视频；
- 取消、重试或删除任务。

`stu_XX` 只可能保留在四宫格标注画面内，含义是本次会话的匿名跟踪编号。四路单独视频是原片。公开 JSON 和文本页面不会返回内部学生 ID、科研 session id 或绝对路径。

## Linux / NVIDIA 部署

要求：Linux、NVIDIA 驱动、Docker Engine、Compose v2、NVIDIA Container Toolkit，以及至少约 12 GiB 的本地资产空间和充足的任务存储空间。GPU 最终验收不能在 Mac 上完成。

如果使用 AutoDL 等没有 Docker 守护进程的 GPU 环境，请参考 [AutoDL Linux / NVIDIA 部署手册](docs/AUTODL_DEPLOYMENT.md)。该文档包含本次实测的 Conda、Uvicorn、screen、模型传输、SSH 隧道和故障恢复流程。

### 1. 准备本地资产

仓库的 `references/` 与 `local-assets/` 均不进入 Git 和镜像。若两个归档位于 `references/`，运行：

```bash
./scripts/prepare_local_assets.sh
```

脚本校验归档后会得到：

- `local-assets/sample-bundle/data/`：只读 v3 输入和预计算结果；
- `local-assets/runtime-models/`：YOLOX-M、RTMW-L、YOLO11m-Pose、OSNet、Basketball_v1 五个活动权重，约 378 MiB。

还必须把 InsightFace `buffalo_l` 的五个 ONNX 文件放到：

```text
local-assets/runtime-models/insightface/models/buffalo_l/
```

官方 v0.7 `buffalo_l.zip` 的 SHA-256 是 `80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f`。模型由 [InsightFace 官方发布页](https://github.com/deepinsight/insightface/releases/tag/v0.7)提供。InsightFace 开源模型有独立的非商业/授权限制；产品化或商业使用前必须向模型权利方确认并取得适用许可，不能把代码仓库许可证当作模型商业许可。

### 2. 配置现场同步与管理员

```bash
mkdir -p local-assets/deployment
cp deployment/sync.example.json local-assets/deployment/sync.json
cp .env.example .env
```

把 `sync.json` 中 cam01、cam02、cam04 相对 cam03 的固定偏移替换成部署现场实测值。cam03 必须保持 `0`。在首次启动前修改 `.env` 的管理员密码和至少 32 字符的随机 JWT 密钥；空数据库首次启动会创建管理员账户，其他用户可通过前端注册页面创建账户。

### 3. 构建与启动

```bash
docker compose build
docker compose up -d
docker compose logs -f app
```

浏览器打开 <http://127.0.0.1:8000>。容器只包含一个 Uvicorn worker、一个 SQLite 队列和最多一个科研子进程。`GET /readyz` 与登录后的 `GET /api/v1/system/readiness` 会验证：

- CUDA 与 ONNX CUDA provider；
- FFmpeg；
- 五个活动权重和 `buffalo_l`；
- 现场同步配置与剩余空间；
- 实际 YOLOX + RTMW 空帧推理，同时加载 YOLO-Pose、OSNet 与 Basketball_v1。

任何检查失败都阻止创建真实任务。严格产品运行模式禁止 stub embedding、模型首次联网下载和 CPU 静默退化。
修正模型、GPU 或同步配置后请重启服务；启动预检通过后，SQLite 中保留的排队任务才会恢复执行，从而避免 readiness 探测与真实任务同时占用 GPU。

## Mac / 无 GPU 开发

Mac 只运行 API、前端与模拟引擎测试：

```bash
uv sync --dev
python scripts/export_openapi.py
cd frontend
pnpm install
pnpm run build
cd ..
uv run alembic upgrade head
BASKETBALL_SIMULATION_MODE=true \
BASKETBALL_WORKER_ENABLED=true \
BASKETBALL_ADMIN_PASSWORD=local-review-password \
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

模拟模式在页面中明确标注，不执行或冒充真实推理。前端类型由 `openapi.json` 生成；API 合同改变后先重新运行 `scripts/export_openapi.py` 和前端构建。

## 数据与运行结构

每个任务位于 `runtime/analyses/<uuid>/`，包含独立的 `input/`、科研 `data/`、`output/` 和 `logs/`。科研 SQLite、gallery、session raw、中间结果互不共享。服务重启后排队任务保留，正在运行的任务变为 `interrupted`，可以从原输入重试。

自动保留策略在 supervisor 启动时及之后每小时执行；只清理已结束任务，排队和运行中的任务不会被清理：

- 注册 gallery：7 天；
- 上传和科研 raw：30 天；
- 结果与可视化：180 天；
- `local-assets/sample-bundle/` 是只读预置资源，永不参与清理。

## API

面向使用者的双语 API 指南位于 <http://127.0.0.1:8000/api/docs>，OpenAPI / Swagger 参考仍位于 <http://127.0.0.1:8000/docs>。在登录后的 <http://127.0.0.1:8000/api/keys> 创建服务端密钥；完整的 `dsb_live_...` 密钥只在创建成功时显示一次。

新的集成应使用分阶段任务接口：

- `POST /api/v1/tasks` 创建 `quick` 或 `full` 草稿；
- `PUT /api/v1/tasks/{id}/inputs/{slot}` 依次上传 `enrollment_video` 与 `cam_01`–`cam_04`（multipart 字段名为 `file`）；
- `POST /api/v1/tasks/{id}/submit` 提交，`GET /api/v1/tasks/{id}` 轮询；
- `GET /api/v1/tasks/{id}/result` 和 `GET /api/v1/tasks/{id}/media/{kind}` 获取结果与复核媒体；
- `POST /api/v1/tasks/{id}/cancel`、`POST /api/v1/tasks/{id}/retry`、`DELETE /api/v1/tasks/{id}` 管理生命周期；
- `GET/POST /api/v1/api-keys`、`DELETE /api/v1/api-keys/{id}` 和 `GET /api/v1/account/usage` 管理密钥与配额。

API 密钥请求使用 `Authorization: Bearer dsb_live_...`。浏览器继续使用 HttpOnly、SameSite=Lax Cookie。旧 `/api/v1/analyses` 仅在兼容期内保留并返回弃用响应头；新集成只应使用 `/tasks` 工作流。其他主要接口：

- `POST /api/v1/login/access-token`、`POST /api/v1/logout`、`GET /api/v1/users/me`
- `GET /api/v1/system/readiness`
- `GET /api/v1/presets`、`GET /api/v1/presets/{id}/result`、`GET /api/v1/presets/{id}/media/{kind}`

浏览器认证令牌写入 HttpOnly、SameSite=Lax Cookie，视频 Range 请求会自然携带身份。

## 验证

本地回归：

```bash
uv run pytest -q
uv run python scripts/validate_v3_presets.py
cd frontend
pnpm test
pnpm run typecheck
pnpm run build
pnpm run test:e2e
```

`pnpm run test:e2e` 包含 48 视图矩阵（6 个页面 × 桌面/手机 × 中/英 × 浅/深）。也可单独运行 `pnpm run test:e2e:visual`；截图写入被 Git 忽略的 `frontend/test-results/**/visual-matrix/`。

数据库迁移：

```bash
uv run alembic upgrade head
uv run alembic current
```

Linux/NVIDIA 上还需真实重跑 group4 和 group5，记录完整与快速模式耗时、峰值显存，并按 [GPU 验收清单](docs/GPU_ACCEPTANCE.md)完成迁移验收。当前 v3 阈值只代表该固定测试集，不是泛化性能承诺。
