#!/usr/bin/env python3
"""大山冰 API 最小演示：上传五个视频 → 等待完成 → 保存结果

安装：python3 -m pip install requests
运行：python3 examples/api_demo.py

先建立 SSH 隧道，运行后输入普通用户在「API 管理」创建的大山冰 API Key
默认使用已准备的 01_jump_shot_quick，快速分析、依次注册、4 人、中文
可用 BASE_URL、API_KEY、DEMO_DIR 环境变量覆盖地址、密钥及该 demo 的目录
每次运行创建一个新任务，Ctrl+C 只停止本地等待，不取消服务器任务
"""

import json
import os
import time
from contextlib import ExitStack
from getpass import getpass
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
DEMO_DIR = Path(os.environ.get(
    "DEMO_DIR", ROOT / "local-assets/demo-uploads/jennie-20260905/01_jump_shot_quick"
)).expanduser()
SLOTS = ("enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04")


def request_json(session, method, path, **kwargs):
    response = session.request(method, BASE_URL + path, timeout=(10, 600), **kwargs)
    if not response.ok:
        raise RuntimeError(f"接口返回 HTTP {response.status_code}：{response.text}")
    return response.json()


def main():
    # 1、检查视频，并使用业务 API Key 认证，不使用管理员或 GLM 的密钥
    paths = {slot: DEMO_DIR / f"{slot}.mp4" for slot in SLOTS}
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(f"找不到演示视频：{path}")
    key = (os.environ.get("API_KEY") or getpass("大山冰 API Key：")).strip()
    if not key:
        raise ValueError("请提供普通用户的 API Key")

    with requests.Session() as session:
        session.headers["Authorization"] = f"Bearer {key}"

        # 2、一次上传并提交，不需要再调用 /submit
        # 这份剪辑 demo 已按原始偏移对齐并归零，四路偏移均为 0 毫秒
        # 只适用于这个演示包，换成自己的视频时必须填写实际同步偏移
        fields = {
            "title": "API Demo｜跳投命中与未中",
            "mode": "quick",
            "enrollment_mode": "sequential",
            "expected_persons": 4,
            "analyst_locale": "zh",
            "sync": json.dumps({"offsets_ms": {slot: 0 for slot in SLOTS[1:]}}),
        }
        print(f"正在上传：{DEMO_DIR}", flush=True)
        with ExitStack() as stack:
            files = {
                slot: (path.name, stack.enter_context(path.open("rb")), "video/mp4")
                for slot, path in paths.items()
            }
            task = request_json(session, "POST", "/api/v1/analyses/upload", data=fields, files=files)
        task_id = task["id"]
        print(f"任务 ID：{task_id}")
        print(f"网页查看：{BASE_URL}/workspace/tasks/{task_id}", flush=True)

        # 3、每 5 秒查询一次，失败、取消等情况停止等待并显示原因
        while True:
            print(f"{task['status']}  {task['progress']}%  {task.get('stage_message', '')}", flush=True)
            if task["status"] == "completed":
                break
            if task["status"] in {"failed", "canceled", "expired", "interrupted"}:
                raise RuntimeError(
                    f"任务结束：{task['status']}，{task.get('error_code') or ''} "
                    f"{task.get('error_message') or task.get('stage_message', '')}"
                )
            time.sleep(5)
            task = request_json(session, "GET", f"/api/v1/analyses/{task_id}")

        # 4、获取篮球分析结果，AI 报告由后台继续自动生成
        result = request_json(session, "GET", f"/api/v1/analyses/{task_id}/result")
        output = Path("runtime/api-demo") / task_id / "result.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"结果已保存：{output.resolve()}")
        print(f"AI 报告接口：{BASE_URL}/api/v1/tasks/{task_id}/analyst/reports")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("已停止等待，服务器任务仍会继续，可通过上方任务链接查看")
    except (requests.RequestException, OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error))
