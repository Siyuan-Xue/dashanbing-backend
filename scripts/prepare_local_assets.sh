#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

model_archive="references/models_20260901.tar.gz"
sample_archive="references/v3_data_and_outputs_20260901.tar.gz"
test -f "$model_archive"
test -f "$sample_archive"

verify_sha256() {
  local expected="$1"
  local file="$2"
  local actual
  if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$file" | awk '{print $1}')"
  else
    actual="$(shasum -a 256 "$file" | awk '{print $1}')"
  fi
  if [[ "$actual" != "$expected" ]]; then
    printf 'SHA-256 mismatch for %s\n' "$file" >&2
    exit 1
  fi
}

verify_sha256 "f33897b95efc8c35bf2a822ffa2c7caa295139fbf2db39b65240ed78156a8acf" "$model_archive"
verify_sha256 "f70050b9bc2ad971db930e98aeafde20c460c7e4f0d4fe30d58ff57845add971" "$sample_archive"

mkdir -p local-assets local-assets/sample-bundle local-assets/runtime-models
python3 scripts/safe_extract.py "$model_archive" local-assets
python3 scripts/safe_extract.py "$sample_archive" local-assets/sample-bundle

mkdir -p \
  local-assets/runtime-models/detection/yolox_m \
  local-assets/runtime-models/pose/rtmw_l \
  local-assets/runtime-models/detection/yolo_pose \
  local-assets/runtime-models/detection/yolo_ball \
  local-assets/runtime-models/reid \
  local-assets/runtime-models/insightface/models/buffalo_l

cp local-assets/models/detection/yolox_m/end2end.onnx local-assets/runtime-models/detection/yolox_m/end2end.onnx
cp local-assets/models/pose/rtmw_l/end2end.onnx local-assets/runtime-models/pose/rtmw_l/end2end.onnx
cp local-assets/models/detection/yolo_pose/yolo11m-pose.pt local-assets/runtime-models/detection/yolo_pose/yolo11m-pose.pt
cp local-assets/models/detection/yolo_ball/Basketball_v1.pt local-assets/runtime-models/detection/yolo_ball/Basketball_v1.pt
cp local-assets/models/reid/osnet_x1_0_msmt17.pth local-assets/runtime-models/reid/osnet_x1_0_msmt17.pth

printf '%s\n' "Prepared the five active research weights and v3 sample bundle."
printf '%s\n' "Install the licensed buffalo_l files under local-assets/runtime-models/insightface/models/buffalo_l/."
