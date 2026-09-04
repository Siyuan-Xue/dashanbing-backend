# AutoDL Linux / NVIDIA 部署手册

本文记录篮球课堂训练复盘产品在 AutoDL 类 GPU 租赁环境中的完整部署流程，供更换实例、机器重启后恢复或后续交接时复用。本文主线是 **Ubuntu 22.04 + Python 3.12 + CUDA 12.4、无 Docker 守护进程** 的直接部署方式；如果目标机具备 Docker Engine、Compose v2 和 NVIDIA Container Toolkit，优先参考项目根目录的 [README](../README.md) 使用 Compose。

本文不会记录 SSH 密码、管理员密码、JWT 密钥等真实凭据。所有 `<...>` 或 `replace-with-...` 都必须在执行前替换，并且不要把替换后的命令、`.env` 或终端输出提交到 Git。

## 1. 部署结果与架构

部署完成后的访问链路为：

```text
本地浏览器
  -> 本机 127.0.0.1:8000（或 6006）
  -> SSH 本地端口转发
  -> GPU 运行机 127.0.0.1:8000
  -> 单个 Uvicorn worker
  -> SQLite 队列
  -> 最多一个科研推理子进程占用 GPU
```

服务不需要公网可访问。Uvicorn 必须绑定运行机的 `127.0.0.1:8000`，再通过 SSH 隧道访问。不要为了方便把它改成面向公网的 `0.0.0.0`，除非另行配置了反向代理、TLS、访问控制和主机防火墙。

本次已验证的环境如下，后续部署可将它作为基线，而不是绝对最低配置：

| 项目 | 已验证值 |
| --- | --- |
| 操作系统 | Ubuntu 22.04.4 LTS |
| Python | 3.12.3 |
| GPU | NVIDIA GeForce RTX 4090，24 GiB 显存 |
| NVIDIA 驱动 | 580.76.05 |
| PyTorch | 2.5.1+cu124 |
| TorchVision | 0.20.1+cu124 |
| ONNX Runtime | onnxruntime-gpu 1.19.2 |
| 项目路径 | `/root/autodl-tmp/dashanbing-backend` |
| Python 环境 | `/root/autodl-tmp/envs/dashanbing` |
| Git origin | `https://gitee.com/milesxue/dashanbing-backend.git` |
| 跟踪分支 | `main` |
| 服务管理 | `screen` + Uvicorn，单 worker |
| 对外方式 | SSH 本地端口转发 |

`nvidia-smi` 中显示的 `CUDA Version` 是驱动能够兼容的最高 CUDA 版本，不等于当前 PyTorch 使用的 CUDA 运行时。验收时以 `torch.version.cuda == "12.4"`、`torch.cuda.is_available() == True` 和实际空帧推理通过为准。

建议使用 24 GiB 显存的 GPU。更小显存尚未完成真实全流程验收，不应直接承诺能够运行完整模式。

## 2. 部署前检查清单

开始前确认：

- 运行机是 Linux，拥有可用的 NVIDIA GPU 和驱动；
- AutoDL 镜像为 Ubuntu 22.04、Python 3.12、CUDA 12.4；
- 数据盘至少有约 15 GiB 空闲空间，若还要保留多次上传和推理结果，应准备更多空间；
- 本地已经准备两个原始归档，以及单独取得的 InsightFace `buffalo_l`；
- 运行机可以从 Gitee 镜像拉取代码；本地开发继续向 GitHub 推送。如果镜像暂不可用，再通过 SSH/SCP/rsync 上传；
- 本地已安装 Git、rsync；构建前端时还需要 Node.js 22 和 pnpm；
- 已决定使用哪个分支或提交，部署时记录准确的 Git commit；
- 已准备现场四机位同步偏移。如果只展示预置样例，可以先不运行自定义上传，但仍要提供格式有效的部署同步文件；
- SSH 密码、网站管理员密码和 JWT 密钥彼此独立。

大文件应放在 AutoDL 数据盘 `/root/autodl-tmp`，不要依赖容量较小或实例释放后可能丢失的系统临时目录。`references/`、`local-assets/`、`runtime/`、`.env` 和前端构建产物均已被 Git 忽略。

## 3. 在本地准备代码、模型和样例

以下操作在保存原始归档的开发机仓库中完成。

### 3.1 检出并记录部署版本

```bash
cd /path/to/dashanbing-backend
git status --short
git branch --show-current
git rev-parse HEAD
```

部署前应保证待部署源码已提交，记录 `git rev-parse HEAD` 的输出。不要把本地未提交代码当成可复现的正式版本。

正式复部署默认使用稳定分支 `main`，并在部署记录中写下实际 commit。需要复现历史环境时，优先使用已验收的 commit 或 tag；不要依赖后续可能删除的短期功能分支。

### 3.2 解压归档并整理运行模型

把下面两个归档放在 `references/`：

```text
references/models_20260901.tar.gz
references/v3_data_and_outputs_20260901.tar.gz
```

执行：

```bash
./scripts/prepare_local_assets.sh
```

脚本会校验归档 SHA-256，使用安全解压逻辑，并生成：

```text
local-assets/
├── models/                         # 原始模型包，部署不需要整体上传
├── runtime-models/                 # 产品运行模型
│   ├── detection/yolox_m/end2end.onnx
│   ├── detection/yolo_pose/yolo11m-pose.pt
│   ├── detection/yolo_ball/Basketball_v1.pt
│   ├── pose/rtmw_l/end2end.onnx
│   ├── reid/osnet_x1_0_msmt17.pth
│   └── insightface/models/buffalo_l/
└── sample-bundle/data/             # v3 输入与预计算输出
```

脚本不会联网下载 `buffalo_l`。必须把合法取得的以下五个 ONNX 文件放到：

```text
local-assets/runtime-models/insightface/models/buffalo_l/
├── 1k3d68.onnx
├── 2d106det.onnx
├── det_10g.onnx
├── genderage.onnx
└── w600k_r50.onnx
```

检查模型：

```bash
find local-assets/runtime-models -type f -print | sort
du -sh local-assets/runtime-models
```

首版不需要 RTMW3D、MotionBERT、备用篮球模型、模型下载压缩包、缓存和重复权重。InsightFace 开源模型有独立授权条件；用于产品或商业展示前，应确认取得了适用许可。

### 3.3 准备现场同步配置

```bash
mkdir -p local-assets/deployment
cp deployment/sync.example.json local-assets/deployment/sync.json
```

编辑 `local-assets/deployment/sync.json`，填写 cam01、cam02、cam04 相对于 cam03 的现场固定偏移。cam03 是锚点，必须保持 `0`。

示例文件中的全零偏移只是占位值。它能通过格式检查，但除非四台相机确实已经硬件同步，否则不能用于真实自定义上传。预置 group3–6 重新分析时会使用样例包内各自的 `sync/group_XX.json`，不使用这份现场同步文件。

### 3.4 构建前端

FastAPI 会直接提供静态前端，因此无 Docker 部署必须提前生成 `app/frontend/`。在开发机执行：

```bash
corepack enable
cd frontend
pnpm install --frozen-lockfile
pnpm run build
cd ..
```

确认以下文件存在：

```bash
test -f app/frontend/index.html
find app/frontend -maxdepth 2 -type f -print | sort
```

`app/frontend/` 被 Git 忽略，所以仅拉取仓库不会得到前端页面。可以选择在运行机安装 Node.js 后重新构建，也可以按本文后续步骤把本地构建产物一并上传。后者更适合展示机。

## 4. 把源码放到运行机

先连接运行机并准备目录：

```bash
ssh -p <SSH_PORT> <SSH_USER>@<SSH_HOST>
mkdir -p /root/autodl-tmp/dashanbing-backend
exit
```

### 4.1 首选：从 Gitee 镜像 clone

AutoDL 访问 GitHub 经常出现 TLS、HTTP/2 或 `GnuTLS recv error`。运行机请把 Git 远端设为 Gitee 镜像，不要从 GitHub 直接拉取：

```text
https://gitee.com/milesxue/dashanbing-backend.git
```

本地开发机继续向 GitHub 推送；运行机只负责从镜像拉取。镜像如何与 GitHub 同步不在运行机操作范围内。产品化分支已经合并，展示部署跟踪稳定分支 `main`。

```bash
ssh -p <SSH_PORT> <SSH_USER>@<SSH_HOST>
cd /root/autodl-tmp
git clone --branch main --single-branch \
  https://gitee.com/milesxue/dashanbing-backend.git
cd dashanbing-backend
git config http.version HTTP/1.1
git config pull.ff only
git remote -v
git rev-parse HEAD
```

如果 HTTPS 仍出现 HTTP/2 或 TLS 问题，强制使用 HTTP/1.1：

```bash
git -c http.version=HTTP/1.1 clone \
  --branch main \
  --single-branch \
  https://gitee.com/milesxue/dashanbing-backend.git
```

HTTP/1.1 只解决一部分中间链路问题。Gitee 仍然失败时，不要反复重试大文件下载，改用下一节的 SSH 上传方案，上传后再按 13.2 把已有目录接入 Gitee 远端。

### 4.2 备用：本地打包源码后通过 SCP 上传

在开发机执行：

```bash
cd /path/to/dashanbing-backend
git archive \
  --format=tar.gz \
  --output=/tmp/dashanbing-source.tar.gz \
  main
shasum -a 256 /tmp/dashanbing-source.tar.gz
scp -P <SSH_PORT> \
  /tmp/dashanbing-source.tar.gz \
  <SSH_USER>@<SSH_HOST>:/root/autodl-tmp/
```

在运行机核对 SHA-256 与本地输出一致，再解压：

```bash
cd /root/autodl-tmp/dashanbing-backend
tar -xzf /root/autodl-tmp/dashanbing-source.tar.gz
```

`git archive` 只包含已提交文件，不包含 `.git`、`app/frontend/`、模型、样例和 `.env`。归档部署本身不能 `git pull`；源码就位后应按 13.2 把现有目录接入 Gitee 镜像，后续即可直接拉取。不要把归档解压到错误的嵌套目录，也不要覆盖 `.env`、`runtime/` 或 `local-assets/`。

## 5. 上传前端、模型和预置样例

以下命令从开发机的项目根目录执行。先设置本次命令使用的参数；不要把真实密码写进变量或脚本，SSH 会交互式询问，长期使用建议配置 SSH 密钥。

```bash
ssh_user="root"
ssh_host="replace-with-autodl-host"
ssh_port="replace-with-autodl-port"
remote_project="/root/autodl-tmp/dashanbing-backend"
```

先创建所有被 Git 忽略、不会随源码出现的远端父目录。这样也兼容不支持 `rsync --mkpath` 的旧版本：

```bash
ssh -p "${ssh_port}" "${ssh_user}@${ssh_host}" \
  "mkdir -p \
  '${remote_project}/local-assets/runtime-models' \
  '${remote_project}/local-assets/deployment' \
  '${remote_project}/local-assets/sample-bundle/data' \
  '${remote_project}/app/frontend'"
```

### 5.1 上传运行模型、现场配置和前端

```bash
rsync -a --partial --progress \
  -e "ssh -p ${ssh_port}" \
  local-assets/runtime-models/ \
  "${ssh_user}@${ssh_host}:${remote_project}/local-assets/runtime-models/"

rsync -a --partial --progress \
  -e "ssh -p ${ssh_port}" \
  local-assets/deployment/ \
  "${ssh_user}@${ssh_host}:${remote_project}/local-assets/deployment/"

rsync -a --partial --progress \
  -e "ssh -p ${ssh_port}" \
  app/frontend/ \
  "${ssh_user}@${ssh_host}:${remote_project}/app/frontend/"
```

### 5.2 上传最小预置样例集

首页四张预置卡片只需要 group3–6。上传注册视频、四组输入、各组同步配置以及最终输出：

```bash
rsync -aR --partial --progress \
  -e "ssh -p ${ssh_port}" \
  local-assets/sample-bundle/data/test_data_v3/0-2.mkv \
  local-assets/sample-bundle/data/test_data_v3/{3,4,5,6}-{1,2,3,4}.mkv \
  local-assets/sample-bundle/data/test_data_v3/sync/group_0{3,4,5,6}.json \
  local-assets/sample-bundle/data/outputs/v3/manifest.json \
  local-assets/sample-bundle/data/outputs/v3/group_0{3,4,5,6}/ \
  "${ssh_user}@${ssh_host}:${remote_project}/"
```

`-R` 会保留从 `local-assets/` 开始的相对路径。四个完整 group 输出目录中包括公开页面需要的 `report.json`、`summary.json`、`eval_vs_gt.json`、`motion.json` 和 `viz/` 视频，也会带上少量内部诊断文件。如果只追求最小体积，可进一步按文件筛选，但必须保留每组四宫格标注视频和对应四路原片输入：

```text
viz/phases.mp4
test_data_v3/{group}-{1,2,3,4}.mkv
```

四路单独复核视频使用上述原片，不再使用 `cam_*_annotated.mp4` / `cam_04_ball.mp4`。标注单路视频仍可用于科研排查，但产品页面不展示。

如果运行机磁盘充足，也可以直接上传整个 `local-assets/sample-bundle/data/`。这更简单，但会包含首版页面不用的 group1、group2、group7 和科研诊断产物。

### 5.3 网络较慢时的传输策略

- 使用 `rsync --partial`，连接中断后重新执行同一命令可续传未完成文件；
- macOS 自带的旧版 rsync 不支持 `--info=progress2`，本文统一使用兼容的 `--progress`；
- 视频本身已经压缩，SSH 的 `-C` 通常收益不大，反而可能增加两端 CPU 开销；
- 可以把模型、输入视频和输出视频拆成 3–4 个独立 rsync 连接并行上传；
- 不要让所有并行 rsync 都复用同一个 SSH ControlMaster，它们会共享一条 TCP 连接，丢包时可能一起降速；
- 单个大文件快结束时尽量不要手动中断，否则可能重复校验或传输文件尾部；
- 不要使用 `--delete`，避免因本地目录不完整而删除运行机已有资产。

### 5.4 校验上传结果

对关键目录做 checksum dry-run。下面命令退出码为 0 且没有文件差异输出，表示两端内容一致：

```bash
rsync -aRnc --itemize-changes \
  -e "ssh -p ${ssh_port}" \
  local-assets/runtime-models/ \
  local-assets/deployment/ \
  app/frontend/ \
  local-assets/sample-bundle/data/test_data_v3/0-2.mkv \
  local-assets/sample-bundle/data/test_data_v3/{3,4,5,6}-{1,2,3,4}.mkv \
  local-assets/sample-bundle/data/test_data_v3/sync/group_0{3,4,5,6}.json \
  local-assets/sample-bundle/data/outputs/v3/manifest.json \
  local-assets/sample-bundle/data/outputs/v3/group_0{3,4,5,6}/ \
  "${ssh_user}@${ssh_host}:${remote_project}/"
```

在运行机检查体积与空间：

```bash
du -sh /root/autodl-tmp/dashanbing-backend/local-assets
df -h /root/autodl-tmp
```

本次最小运行资产约 4 GiB；实际大小会随媒体文件变化。部署完 Python 环境和资产后，本次 50 GiB 数据盘剩余约 38.9 GiB。

## 6. 在运行机安装系统与 Python 依赖

以下操作均在运行机执行。

### 6.1 安装系统工具

```bash
apt-get update
apt-get install -y ffmpeg libglib2.0-0 build-essential screen curl rsync
ffmpeg -version
ffprobe -version
```

科研引擎会调用 FFmpeg，上传接口还会用同一软件包提供的 `ffprobe` 检查视频流。只有 Python OpenCV 而没有这两个命令，readiness 仍会失败。

### 6.2 创建独立 Conda 环境

AutoDL 基础镜像通常已在 base 环境中配置 PyTorch/CUDA。为避免污染 base，克隆到数据盘：

```bash
mkdir -p /root/autodl-tmp/envs
conda create -y \
  -p /root/autodl-tmp/envs/dashanbing \
  --clone base
/root/autodl-tmp/envs/dashanbing/bin/python --version
```

后续命令均使用该环境的绝对 Python 路径，不依赖 shell 是否执行过 `conda activate`。

### 6.3 安装 GPU 和应用依赖

Python 3.12 下，如果同时让多个包自由解析 NumPy 与 OpenCV，pip 可能长时间回溯。先创建约束文件：

```bash
printf '%s\n' \
  'numpy==1.26.4' \
  'opencv-python==4.11.0.86' \
  'opencv-python-headless==4.11.0.86' \
  > /root/autodl-tmp/dashanbing-constraints.txt
```

然后安装：

```bash
cd /root/autodl-tmp/dashanbing-backend

/root/autodl-tmp/envs/dashanbing/bin/python -m pip install \
  --upgrade pip setuptools wheel

/root/autodl-tmp/envs/dashanbing/bin/python -m pip install \
  --index-url https://download.pytorch.org/whl/cu124 \
  torch==2.5.1 torchvision==0.20.1

/root/autodl-tmp/envs/dashanbing/bin/python -m pip uninstall -y onnxruntime

/root/autodl-tmp/envs/dashanbing/bin/python -m pip install \
  -c /root/autodl-tmp/dashanbing-constraints.txt \
  -r research_engine/requirements-gpu.txt

/root/autodl-tmp/envs/dashanbing/bin/python -m pip uninstall -y \
  opencv-python \
  opencv-contrib-python \
  opencv-contrib-python-headless \
  opencv-python-headless

/root/autodl-tmp/envs/dashanbing/bin/python -m pip install \
  --require-hashes \
  -r requirements-app.lock
```

最后一步会按锁文件重新安装 `numpy==1.26.4` 和 `opencv-python-headless==4.11.0.86`。产品运行环境只保留 headless OpenCV，避免服务器因 GUI 库产生额外依赖和冲突。

检查依赖元数据：

```bash
/root/autodl-tmp/envs/dashanbing/bin/python -m pip check
```

可能看到 `ultralytics` 声明需要 `opencv-python` 的提示。当前环境有相同 `cv2` 功能的 `opencv-python-headless`，这是为无图形服务器做的有意替换。除此之外不应出现缺失或冲突。若出现其他错误，先修复再继续。

### 6.4 检查 CUDA、PyTorch、ONNX Runtime 与 OpenCV

```bash
nvidia-smi

/root/autodl-tmp/envs/dashanbing/bin/python - <<'PY'
import cv2
import onnxruntime as ort
import torch

print("torch:", torch.__version__)
print("torch CUDA runtime:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "unavailable")
print("ONNX Runtime:", ort.__version__)
print("ONNX providers:", ort.get_available_providers())
print("OpenCV:", cv2.__version__)
PY
```

必须满足：

- `torch.cuda.is_available()` 为 `True`；
- `torch.version.cuda` 为 `12.4`；
- ONNX providers 包含 `CUDAExecutionProvider`；
- 导入 `cv2` 没有动态库错误。

如果 ONNX Runtime 找不到 CUDA/CuDNN 库，服务启动脚本会把 Conda 环境的 `lib/` 加入 `LD_LIBRARY_PATH`。

## 7. 配置应用

### 7.1 生成独立凭据

在运行机分别生成网站管理员密码和 JWT 密钥：

```bash
openssl rand -base64 24
openssl rand -hex 32
```

把两行输出分别保存到密码管理器。不要使用 SSH 登录密码作为网站密码，也不要把真实值粘贴到部署文档、聊天记录、启动脚本或 Git。

本次部署过程中如果任何临时密码曾通过聊天或其他协作渠道明文传递，正式展示前应在 AutoDL 控制台重置 SSH 密码，并重新生成网站管理员密码和 JWT 密钥。

### 7.2 创建 `.env`

```bash
cd /root/autodl-tmp/dashanbing-backend
umask 077
cp .env.example .env
nano .env
```

填写为：

```dotenv
BASKETBALL_ADMIN_USERNAME=admin
BASKETBALL_ADMIN_PASSWORD=replace-with-a-new-admin-password
BASKETBALL_JWT_SECRET_KEY=replace-with-a-new-64-character-hex-secret
BASKETBALL_COOKIE_SECURE=false
BASKETBALL_SIMULATION_MODE=false
BASKETBALL_WORKER_ENABLED=true
BASKETBALL_MIN_FREE_STORAGE_GB=20

BASKETBALL_DATABASE_URL=sqlite:////root/autodl-tmp/dashanbing-backend/runtime/app.db
BASKETBALL_RUNTIME_ROOT=/root/autodl-tmp/dashanbing-backend/runtime
BASKETBALL_SAMPLE_ROOT=/root/autodl-tmp/dashanbing-backend/local-assets/sample-bundle/data
BASKETBALL_MODEL_ROOT=/root/autodl-tmp/dashanbing-backend/local-assets/runtime-models
BASKETBALL_SYNC_CONFIG=/root/autodl-tmp/dashanbing-backend/local-assets/deployment/sync.json
BASKETBALL_FRONTEND_DIST=/root/autodl-tmp/dashanbing-backend/app/frontend
```

锁定权限并准备运行目录：

```bash
chmod 600 .env
mkdir -p runtime/tmp runtime/yolo-config
```

通过 `http://127.0.0.1` 和 SSH 隧道访问时，`BASKETBALL_COOKIE_SECURE=false` 是必要的。如果以后增加 HTTPS 反向代理，应改为 `true`。

管理员账号只会在空数据库首次启动时创建，而且默认/占位凭据不会创建管理员。数据库已经存在后，只修改 `.env` 中的管理员密码不会重置现有账号；服务会检测配置密码与数据库哈希不一致并让 readiness 失败。如需重新初始化账号，应先备份数据库并显式使用一个新的空数据库路径，不要直接删除仍有任务记录的数据库。

### 7.3 检查关键资产

```bash
cd /root/autodl-tmp/dashanbing-backend
test -f app/frontend/index.html
test -f local-assets/deployment/sync.json
test -f local-assets/runtime-models/detection/yolox_m/end2end.onnx
test -f local-assets/runtime-models/pose/rtmw_l/end2end.onnx
test -f local-assets/runtime-models/detection/yolo_pose/yolo11m-pose.pt
test -f local-assets/runtime-models/detection/yolo_ball/Basketball_v1.pt
test -f local-assets/runtime-models/reid/osnet_x1_0_msmt17.pth
test -f local-assets/runtime-models/insightface/models/buffalo_l/det_10g.onnx
```

## 8. 数据库迁移与启动前验证

### 8.1 执行 Alembic 迁移

```bash
cd /root/autodl-tmp/dashanbing-backend
/root/autodl-tmp/envs/dashanbing/bin/python -m alembic upgrade head
/root/autodl-tmp/envs/dashanbing/bin/python -m alembic current
```

### 8.2 执行严格模型加载和空帧推理

```bash
cd /root/autodl-tmp/dashanbing-backend

CONDA_PREFIX=/root/autodl-tmp/envs/dashanbing \
LD_LIBRARY_PATH=/root/autodl-tmp/envs/dashanbing/lib:${LD_LIBRARY_PATH:-} \
TMPDIR=/root/autodl-tmp/dashanbing-backend/runtime/tmp \
/root/autodl-tmp/envs/dashanbing/bin/python \
  -m research_engine.product_runner \
  --check-readiness \
  --task-root /root/autodl-tmp/dashanbing-backend/runtime/readiness-manual \
  --model-root /root/autodl-tmp/dashanbing-backend/local-assets/runtime-models
```

成功时最后一行 JSON 的 `ready` 为 `true`，并包含 CUDA 设备、ONNX providers 和以下空帧探测：

```text
yolox, rtmw, yolo_pose, basketball
```

该命令还会实际加载 OSNet 和 `buffalo_l`。仅看到 CUDA provider 名称不能替代这一步。

### 8.3 验证四个预置样例

```bash
cd /root/autodl-tmp/dashanbing-backend
/root/autodl-tmp/envs/dashanbing/bin/python scripts/validate_v3_presets.py
```

要求：

- `quick-demo`（group4）：precision/recall 为 1.0/1.0；
- `mixed-actions`（group3）：precision 不低于 0.963，recall 为 1.0；
- `verified-outcome`（group5）：precision 不低于 0.944，recall 为 1.0；
- `layup-demo`（group6）：precision/recall 为 1.0/1.0；
- group5 outcome truth 为 17/17；
- 结果 JSON 不包含 `stu_` 或 `student_id`；
- 每组四宫格标注视频与四路原片输入都存在。

这些阈值只代表固定 v3 测试集，不代表新视频上的泛化性能。

### 8.4 运行测试时的已知注意事项

```bash
cd /root/autodl-tmp/dashanbing-backend
/root/autodl-tmp/envs/dashanbing/bin/python -m pytest -q
```

早期部署版本在真实 GPU 机器上曾出现 46 个通过、2 个失败。两个失败分别来自：

```text
tests/test_readiness.py::test_real_readiness_names_missing_active_models_and_sync
tests/test_analysis_api.py::test_real_upload_is_blocked_before_saving_when_runtime_is_not_ready
```

这两个测试构造了“运行环境缺失”的场景，却同时假设执行测试的机器没有 CUDA；在真实 GPU 主机上 CUDA 检查会通过，因此断言失败。当前代码已经在这两个用例中显式隔离 CUDA 探测，使测试不再依赖执行主机是否有 GPU。新部署应以完整测试全部通过为要求；若仍出现上述失败，说明运行机源码不是包含该修复的最新版本。

### 8.5 验证自定义上传边界

产品只接受 MKV、MP4、MOV、WebM。前端文件选择器和文件头检查只用于尽早提示；服务端会先校验允许的容器签名，再调用 `ffprobe` 确认存在可读取、尺寸有效且时长大于零的视频流。不能信任文件名、扩展名或浏览器上报的 Content-Type。

建议至少验证以下情况：

- 正常五路视频创建任务并进入队列；
- PDF、空文件以及只伪造 Matroska/MP4 文件头的内容返回 HTTP 400，且不会留下任务目录；
- 超出上传总量限制返回 HTTP 413；
- 低于存储保留空间返回 HTTP 507；
- `ffprobe` 不可用时 readiness 失败，上传返回 HTTP 503，而不是跳过校验。

这是一项上传时的快速结构校验，不会为节省几秒而完整解码数小时视频；文件在后续深度解码时仍可能暴露帧级损坏，此时任务应明确失败，不能生成伪结果。

## 9. 使用 screen 管理服务

AutoDL 环境通常没有 systemd，SSH 断开后前台进程也会结束，因此使用 `screen` 保存服务进程。以下脚本放在数据盘，不提交凭据。

### 9.1 启动脚本

创建 `/root/autodl-tmp/start-dashanbing.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

deployment_project="/root/autodl-tmp/dashanbing-backend"
deployment_env="/root/autodl-tmp/envs/dashanbing"
deployment_python="${deployment_env}/bin/python"
deployment_session="dashanbing"
deployment_log="/root/autodl-tmp/dashanbing.log"
deployment_tmp="${deployment_project}/runtime/tmp"
deployment_yolo_config="${deployment_project}/runtime/yolo-config"
deployment_library_path="${deployment_env}/lib"

if [[ -n "${LD_LIBRARY_PATH:-}" ]]; then
  deployment_library_path="${deployment_library_path}:${LD_LIBRARY_PATH}"
fi

cd "${deployment_project}"
mkdir -p "${deployment_tmp}" "${deployment_yolo_config}"

if screen -ls | grep -q "[.]${deployment_session}[[:space:]]"; then
  echo "${deployment_session} is already running"
  exit 0
fi

"${deployment_python}" -m alembic upgrade head

screen -L \
  -Logfile "${deployment_log}" \
  -dmS "${deployment_session}" \
  env \
  CONDA_PREFIX="${deployment_env}" \
  LD_LIBRARY_PATH="${deployment_library_path}" \
  PYTHONUNBUFFERED=1 \
  TMPDIR="${deployment_tmp}" \
  YOLO_CONFIG_DIR="${deployment_yolo_config}" \
  "${deployment_python}" -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1

echo "started ${deployment_session}; log: ${deployment_log}"
```

授权并启动：

```bash
chmod 700 /root/autodl-tmp/start-dashanbing.sh
/root/autodl-tmp/start-dashanbing.sh
```

启动时会执行严格 GPU 预检，首次加载模型可能需要数分钟。不要在 readiness 尚未结束时重复启动第二份服务。

### 9.2 停止脚本

创建 `/root/autodl-tmp/stop-dashanbing.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

deployment_session="dashanbing"

if screen -ls | grep -q "[.]${deployment_session}[[:space:]]"; then
  screen -S "${deployment_session}" -X quit
  echo "stopped ${deployment_session}"
else
  echo "${deployment_session} is not running"
fi
```

授权：

```bash
chmod 700 /root/autodl-tmp/stop-dashanbing.sh
```

### 9.3 日常管理命令

```bash
# 查看会话
screen -ls

# 进入服务终端；按 Ctrl-A，再按 D，可退出但不停止服务
screen -r dashanbing

# 查看持续日志
tail -f /root/autodl-tmp/dashanbing.log

# 停止
/root/autodl-tmp/stop-dashanbing.sh

# 再启动
/root/autodl-tmp/start-dashanbing.sh
```

应用重启后，SQLite 中的排队任务会保留，原先处于运行中的任务会标记为 `interrupted`，需要在页面中从原输入重试。GPU 仍然只同时运行一个任务。

## 10. 建立 SSH 隧道并打开网页

服务只监听运行机的 `127.0.0.1:8000`。在开发机另开一个终端，执行：

```bash
ssh -CN \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -L 8000:127.0.0.1:8000 \
  -p <SSH_PORT> \
  <SSH_USER>@<SSH_HOST>
```

然后访问：

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/docs
```

如果开发机的 8000 端口已占用，可以把本地端口换成 6006，但远端仍然是应用的 8000：

```bash
ssh -CN \
  -o ExitOnForwardFailure=yes \
  -L 6006:127.0.0.1:8000 \
  -p <SSH_PORT> \
  <SSH_USER>@<SSH_HOST>
```

此时访问 `http://127.0.0.1:6006`。

AutoDL 常见示例命令类似：

```text
ssh -CNg -L 6006:127.0.0.1:6006 ...
```

各参数含义：

- `-C`：压缩 SSH 流量；对已压缩视频通常帮助有限；
- `-N`：不执行远端 shell，只建立转发；
- `-g`：允许开发机局域网中的其他主机连接该转发端口；单人本机展示通常不需要，会扩大访问范围；
- `-L 本地端口:远端目标:远端端口`：把本地端口映射到远端地址。

本项目远端服务端口是 8000，因此不能机械照抄示例中的远端 6006。除非确实要让局域网其他设备访问，否则省略 `-g`。

## 11. 服务与 API 验收

### 11.1 运行机本地检查

```bash
curl -i http://127.0.0.1:8000/healthz
curl -i http://127.0.0.1:8000/readyz
```

要求：

- `/healthz` 返回 HTTP 200 和 `{"status":"ok"}`；
- `/readyz` 返回 HTTP 200、`"mode":"gpu"`、`"ready":true`；
- readiness 所有 14 项均为 ready，包括五个活动权重、`buffalo_l`、同步配置、样例包、凭据、任务执行器、FFmpeg、存储、CUDA 和空帧推理。

若 `/healthz` 暂时无法连接，先查看日志。应用在 Uvicorn 完成 startup 之前不会接受请求，而 startup 会执行严格模型检查。

### 11.2 登录并保存 Cookie

```bash
curl -i \
  -c /tmp/dashanbing-cookie.txt \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=admin' \
  --data-urlencode 'password=replace-with-admin-password' \
  http://127.0.0.1:8000/api/v1/login/access-token
```

要求返回 HTTP 200，并写入 HttpOnly、SameSite=Lax Cookie。

### 11.3 检查预置结果

```bash
curl -sS \
  -b /tmp/dashanbing-cookie.txt \
  http://127.0.0.1:8000/api/v1/presets

for preset_id in quick-demo mixed-actions verified-outcome layup-demo; do
  curl -sS -o /dev/null -w "${preset_id}: %{http_code}\n" \
    -b /tmp/dashanbing-cookie.txt \
    "http://127.0.0.1:8000/api/v1/presets/${preset_id}/result"
done
```

四个结果接口必须都是 HTTP 200，并且页面应能秒开预计算结果。

### 11.4 检查视频 Range

```bash
for preset_id in quick-demo mixed-actions verified-outcome layup-demo; do
  for media_kind in cam_01 cam_02 cam_03 cam_04 phases; do
    curl -sS -o /dev/null \
      -w "${preset_id}/${media_kind}: %{http_code} %{size_download}\n" \
      -b /tmp/dashanbing-cookie.txt \
      -H 'Range: bytes=0-1023' \
      "http://127.0.0.1:8000/api/v1/presets/${preset_id}/media/${media_kind}"
  done
done
```

20 个请求都应返回 `206`，下载大小为 `1024` 字节。随后在浏览器确认五个播放器都能播放和拖动。

本次部署已经验证：严格 readiness 全部通过、四个预置结果接口均为 200、20 个媒体 Range 请求均为 206，并且通过 SSH 隧道访问 `/healthz` 返回 200。

## 12. 展示前检查

展示前按顺序执行：

1. 在 AutoDL 控制台确认实例仍在运行、GPU 型号正确、数据盘已挂载；
2. SSH 登录并运行 `nvidia-smi`；
3. 检查 `df -h /root/autodl-tmp`，保证可用空间不低于 `.env` 中阈值；
4. 执行 `/root/autodl-tmp/start-dashanbing.sh`；
5. 用 `screen -ls` 和日志确认没有第二个服务实例；
6. 等待 `/readyz` 返回 200；
7. 从展示电脑建立 SSH 隧道；
8. 登录网页，逐一打开四个预置结果和五类视频；
9. 如果要演示真实重跑，优先选择 `quick-demo`，提前预留约 10 分钟以上，不承诺实时完成；
10. 如果要演示自定义上传，先确认现场同步配置已经实测，不使用全零占位值；
11. 关闭可能占用本地 8000/6006 端口的其他程序；
12. 准备预计算页面作为真实推理等待期间的备用展示内容。

预置样例的科研原环境耗时参考：

| 预置 | 内容 | 原环境完整分析约耗时 |
| --- | --- | --- |
| quick-demo | group4，4 次跳投 | 9.4 分钟 |
| mixed-actions | group3，三威胁 15 次、跳投 12 次 | 26.7 分钟 |
| verified-outcome | group5，罚篮 18 次 | 30.9 分钟 |
| layup-demo | group6，上篮 6 次 | 14.3 分钟 |

这些是参考值，不是当前 GPU 的服务等级承诺。首次模型加载、视频编码、磁盘速度和模式都会影响耗时。

## 13. 更新、重启与数据保留

### 13.1 AutoDL 实例重启

实例重启后数据盘通常仍在，但 `screen` 会话和进程不会自动恢复。重新执行：

```bash
/root/autodl-tmp/start-dashanbing.sh
```

如果平台重新分配了 SSH 域名或端口，还要使用新的 `<SSH_HOST>`、`<SSH_PORT>` 重建本地隧道。

### 13.2 更新代码

运行机 `origin` 必须指向 Gitee 镜像：

```bash
cd /root/autodl-tmp/dashanbing-backend
git remote -v
# origin  https://gitee.com/milesxue/dashanbing-backend.git
```

如果仍指向 GitHub，或还没有 `.git`（早期归档部署），先接入镜像，不要 `reset --hard`，以免覆盖 `.env`、运行数据和已 rsync 的源码：

```bash
cd /root/autodl-tmp/dashanbing-backend
test -d .git || git init
git remote remove origin 2>/dev/null || true
git remote add origin https://gitee.com/milesxue/dashanbing-backend.git
git fetch origin
git reset --mixed origin/main
git branch -M main
git branch --set-upstream-to=origin/main
git config http.version HTTP/1.1
git config pull.ff only
```

本地推送到 GitHub 并完成镜像同步后，运行机执行：

```bash
/root/autodl-tmp/stop-dashanbing.sh
cd /root/autodl-tmp/dashanbing-backend
git status --short
git fetch origin
git pull --ff-only
/root/autodl-tmp/envs/dashanbing/bin/python -m pip install \
  --require-hashes -r requirements-app.lock
/root/autodl-tmp/envs/dashanbing/bin/python -m alembic upgrade head
/root/autodl-tmp/start-dashanbing.sh
```

如果 `git pull --ff-only` 因工作区修改而被拒绝，先停止更新并检查差异：

```bash
git status --short
git diff --stat
git diff
```

确认差异只是可丢弃的旧源码后，也应先备份再逐文件恢复，或新建干净 checkout 并迁移 `.env`、`runtime/`、`local-assets/` 和 `app/frontend/`。不要在生产目录直接使用 `git reset --hard`，也不要对包含本地资产的目录执行会删除未跟踪文件的清理命令。

如果 GPU requirements、PyTorch 或模型发生变化，应重新执行完整依赖安装、严格 readiness 和 [GPU 验收清单](GPU_ACCEPTANCE.md)，不要只重启应用。

前端源码发生变化后，必须重新运行 `pnpm run build` 并上传新的 `app/frontend/`。

### 13.3 备份与保留

重要运行数据位于：

```text
/root/autodl-tmp/dashanbing-backend/.env
/root/autodl-tmp/dashanbing-backend/runtime/app.db
/root/autodl-tmp/dashanbing-backend/runtime/analyses/
```

应用的自动保留策略为：

- 注册 gallery：7 天；
- 上传和科研 raw：30 天；
- 结果与可视化：180 天；
- 只读预置资源不自动清理。

平台实例释放、数据盘销毁或欠费回收不受应用保留策略保护。需要长期保留的数据库和结果应定期复制到受控存储，备份中同样可能包含敏感视频，不得上传到公开仓库。

## 14. 常见故障排查

### 14.1 Git clone 出现 TLS、HTTP/2 或 GnuTLS 错误

运行机不要使用 GitHub 作为 `origin`。确认远端是 Gitee 镜像后，再强制 HTTP/1.1：

```bash
git remote set-url origin https://gitee.com/milesxue/dashanbing-backend.git
git -c http.version=HTTP/1.1 ls-remote origin
git -c http.version=HTTP/1.1 fetch origin
```

仍失败则使用 `git archive` + SCP/rsync，随后按 13.2 接入 Gitee。不要关闭 TLS 校验，也不要设置 `http.sslVerify=false`。

### 14.2 运行机没有 Docker

AutoDL 提供的环境本身往往已经是容器，里面没有 Docker daemon 或 `/var/run/docker.sock`。这是正常情况，按本文 Conda + Uvicorn + screen 路径部署，不要尝试在受限容器里强行启动 Docker-in-Docker。

### 14.3 readiness 报 `ffmpeg` 或 `ffprobe` 失败

```bash
command -v ffmpeg
command -v ffprobe
apt-get install -y ffmpeg
```

安装后重启服务。启动预检失败后，应用会锁住真实任务队列，修正环境但不重启服务仍然不能创建真实任务。

### 14.4 readiness 报 CUDA 不可用

依次检查：

```bash
nvidia-smi
/root/autodl-tmp/envs/dashanbing/bin/python -c \
  'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())'
```

确认没有选到 CPU 实例，且安装的是 `cu124` PyTorch。禁止为了“先跑起来”切换到 CPU 或模拟模式冒充真实推理。

### 14.5 ONNX Runtime 没有 CUDAExecutionProvider

```bash
/root/autodl-tmp/envs/dashanbing/bin/python -m pip show \
  onnxruntime onnxruntime-gpu
/root/autodl-tmp/envs/dashanbing/bin/python -c \
  'import onnxruntime as ort; print(ort.get_available_providers())'
```

不要同时保留 CPU `onnxruntime` 和 `onnxruntime-gpu`。确认启动进程的 `LD_LIBRARY_PATH` 包含 `/root/autodl-tmp/envs/dashanbing/lib`，再重新安装锁定的 `onnxruntime-gpu==1.19.2`。

### 14.6 pip 长时间解析 OpenCV 或 NumPy

确认使用了 `/root/autodl-tmp/dashanbing-constraints.txt`，并且版本为：

```text
numpy==1.26.4
opencv-python==4.11.0.86
opencv-python-headless==4.11.0.86
```

应用最终只保留 `opencv-python-headless`。不要在解析卡住时随意升级到 NumPy 2.x。

### 14.7 readiness 报 `sample_bundle` 不完整

确认 group3–6 各自具备 `report.json`、`summary.json`、`eval_vs_gt.json`、`viz/phases.mp4`，并具备四路原片输入：

```text
test_data_v3/0-2.mkv
test_data_v3/3-1.mkv ... 6-4.mkv
test_data_v3/sync/group_03.json ... group_06.json
```

重新执行 rsync checksum dry-run。顶层 `manifest.json` 的统计可能过期，产品以各组最终 `report.json` 为准；发现不一致时显示后台告警。

### 14.8 登录密码修改后仍无法登录

管理员只在空数据库首次启动时创建。已有 `runtime/app.db` 时，修改 `.env` 不会更新数据库中的密码。先确认连接的数据库路径是否正确。需要重建账号时，保留旧数据库备份并使用新的空数据库路径完成初始化。

### 14.9 本地 8000 或 6006 端口被占用

在开发机检查：

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:6006 -sTCP:LISTEN
```

选择一个空闲的本地端口即可，`-L` 右侧的远端应用端口仍保持 8000。

### 14.10 视频能下载但不能拖动

确认带 `Range: bytes=0-1023` 的请求返回 HTTP 206，而不是 200；确认浏览器携带登录 Cookie。媒体 API 只允许访问 manifest 中的五种文件，不能使用任意文件路径。

### 14.11 存储空间不足

```bash
df -h /root/autodl-tmp
du -sh /root/autodl-tmp/dashanbing-backend/runtime/*
```

先根据保留策略确认哪些已经结束的任务可以清理或备份。不要删除排队、运行中任务或只读预置资源，也不要对项目根目录执行递归清理命令。

## 15. 当前尚未完成的最终验收

2026-09-03 已在本机 RTX 4090 上完成 group4/group5 完整与快速真实重跑：DTO 与 `report.json` 一致，group4 为 1.0/1.0，group5 为 0.944/1.0 且 outcome 17/17。记录见 [GPU_ACCEPTANCE.md](GPU_ACCEPTANCE.md) 本次实测节。GPU 主机完整 pytest 已通过；用例数量会随代码演进，不作为验收指标。

仍未完成、不能当作已交付的部分：

- 使用真实部署机位测量自定义上传的四机位固定同步偏移；
- 正式产品或商业使用前确认 InsightFace 模型授权。

本机耗时约为原科研环境的 2.3–2.5 倍，不应把原 9.4 / 30.9 分钟写成当前服务等级。自定义上传会在排队前拒绝不受支持或结构损坏的封装，但后续深度解码仍可能发现帧级损坏并使任务明确失败。

## 16. 一页式复部署清单

下次创建新实例时，可按此顺序执行：

1. 选择 Ubuntu 22.04、Python 3.12、CUDA 12.4、24 GiB 显存级别 NVIDIA GPU；
2. 检查 `nvidia-smi`、数据盘空间和 SSH；
3. 从 Gitee 镜像 clone `main` 并记录 commit；网络异常时改用 HTTP/1.1，再失败则上传源码归档后按 13.2 接入 Gitee；
4. 本地运行 `scripts/prepare_local_assets.sh` 并补齐 `buffalo_l`；
5. 本地构建 `app/frontend/`；
6. 用 rsync 上传最小运行模型、前端、group3–6 输入输出和现场同步配置；
7. 用 rsync checksum dry-run 校验大文件；
8. 安装 FFmpeg、screen 和系统库；
9. 克隆 Conda base 到 `/root/autodl-tmp/envs/dashanbing`；
10. 按约束安装 cu124 PyTorch、GPU requirements 和应用锁文件；
11. 配置全新管理员密码、JWT 密钥和绝对路径 `.env`；
12. 执行 Alembic、CUDA/ORT 检查、严格空帧推理和 v3 样例验证；
13. 使用单 worker 的 screen 脚本启动；
14. 等待 `/readyz` 全部通过；
15. 建立 SSH 本地端口转发；
16. 验证登录、四个预置结果和 20 个视频 Range 请求；
17. 展示前轮换曾经暴露的临时凭据；
18. 正式验收时按 [GPU_ACCEPTANCE.md](GPU_ACCEPTANCE.md) 完成 group4/group5 真实重跑。
