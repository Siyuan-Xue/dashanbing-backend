import { useLocale } from "../providers/LocaleProvider";
import { apiCopy, formatRetentionDuration } from "../apiCenter/copy";

const curlExample = `export BASE_URL="http://127.0.0.1:8000"
export API_KEY="dsb_live_replace_with_your_key"

set -eu

TASK_ID="$(curl -fsS -X POST "$BASE_URL/api/v1/tasks" \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"title":"Friday shooting","mode":"quick"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"

curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/inputs/enrollment_video" -H "Authorization: Bearer $API_KEY" -F "file=@/absolute/path/enrollment.mp4"
curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/inputs/cam_01" -H "Authorization: Bearer $API_KEY" -F "file=@/absolute/path/cam_01.mp4"
curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/inputs/cam_02" -H "Authorization: Bearer $API_KEY" -F "file=@/absolute/path/cam_02.mp4"
curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/inputs/cam_03" -H "Authorization: Bearer $API_KEY" -F "file=@/absolute/path/cam_03.mp4"
curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/inputs/cam_04" -H "Authorization: Bearer $API_KEY" -F "file=@/absolute/path/cam_04.mp4"

curl -fsS -X POST "$BASE_URL/api/v1/tasks/$TASK_ID/submit" -H "Authorization: Bearer $API_KEY"
while :; do
  TASK_JSON="$(curl -fsS "$BASE_URL/api/v1/tasks/$TASK_ID" -H "Authorization: Bearer $API_KEY")"
  STATUS="$(printf '%s' "$TASK_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  case "$STATUS" in
    completed) curl -fsS "$BASE_URL/api/v1/tasks/$TASK_ID/result" -H "Authorization: Bearer $API_KEY"; break ;;
    failed|canceled|expired) printf 'Task ended with status: %s\\n' "$STATUS" >&2; exit 1 ;;
    *) sleep 5 ;;
  esac
done`;

const pythonExample = `import os
import time
from pathlib import Path
import requests

base_url = os.environ["BASE_URL"].rstrip("/")
headers = {"Authorization": f"Bearer {os.environ['API_KEY']}"}
files = {
    "enrollment_video": Path("/absolute/path/enrollment.mp4"),
    "cam_01": Path("/absolute/path/cam_01.mp4"),
    "cam_02": Path("/absolute/path/cam_02.mp4"),
    "cam_03": Path("/absolute/path/cam_03.mp4"),
    "cam_04": Path("/absolute/path/cam_04.mp4"),
}

response = requests.post(f"{base_url}/api/v1/tasks", headers=headers,
                         json={"title": "Friday shooting", "mode": "full"})
response.raise_for_status()
task = response.json()

for slot, path in files.items():
    with path.open("rb") as stream:
        response = requests.put(f"{base_url}/api/v1/tasks/{task['id']}/inputs/{slot}",
                                headers=headers, files={"file": (path.name, stream)})
    response.raise_for_status()

response = requests.post(f"{base_url}/api/v1/tasks/{task['id']}/submit", headers=headers)
response.raise_for_status()

while True:
    response = requests.get(f"{base_url}/api/v1/tasks/{task['id']}", headers=headers)
    response.raise_for_status()
    task = response.json()
    if task["status"] in {"completed", "failed", "canceled", "expired"}:
        break
    time.sleep(5)

if task["status"] == "completed":
    response = requests.get(f"{base_url}/api/v1/tasks/{task['id']}/result", headers=headers)
    response.raise_for_status()
    print(response.json())`;

const tocZh = [["overview", "模式比较"], ["auth", "认证"], ["workflow", "创建与上传"], ["polling", "轮询与结果"], ["lifecycle", "生命周期"], ["limits", "配额与保留"], ["examples", "可执行示例"], ["errors", "状态与错误"]];
const tocEn = [["overview", "Mode comparison"], ["auth", "Authentication"], ["workflow", "Create and upload"], ["polling", "Polling and results"], ["lifecycle", "Lifecycle"], ["limits", "Limits and retention"], ["examples", "Executable examples"], ["errors", "Statuses and errors"]];

function Code({ children }: { children: string }) { return <pre className="api-code"><code>{children}</code></pre>; }

export function ApiDocsPage() {
  const { locale } = useLocale();
  const c = apiCopy[locale];
  const toc = locale === "zh" ? tocZh : tocEn;
  return <>
    <main className="api-content api-docs">
      <header className="api-page-header"><span>REST · v1</span><h1>{c.docsTitle}</h1><p>{c.docsLead}</p></header>
      <section id="overview"><h2>{locale === "zh" ? "模式比较" : "Mode comparison"}</h2><div className="api-table-wrap"><table><thead><tr><th>{locale === "zh" ? "维度" : "Dimension"}</th><th>quick</th><th>full</th></tr></thead><tbody><tr><td>{locale === "zh" ? "处理路径" : "Processing path"}</td><td>{locale === "zh" ? "较短快速路径" : "Shorter fast path"}</td><td>{locale === "zh" ? "完整分析路径" : "Complete analysis path"}</td></tr><tr><td>{locale === "zh" ? "输入" : "Inputs"}</td><td colSpan={2}>{locale === "zh" ? "均需注册视频与 cam_01–cam_04，共五个有效文件" : "Both require enrollment video and cam_01–cam_04: five valid files"}</td></tr><tr><td>{locale === "zh" ? "输出合同" : "Output contract"}</td><td colSpan={2}>{locale === "zh" ? "相同的任务、结果与媒体结构" : "The same task, result, and media shapes"}</td></tr></tbody></table></div></section>
      <section id="auth"><h2>{locale === "zh" ? "认证" : "Authentication"}</h2><p>{locale === "zh" ? "在 API 管理中创建密钥。服务端集成的每个请求都发送：" : "Create a key in API Management. Send this on every server-side request:"}</p><Code>Authorization: Bearer dsb_live_…</Code><p className="api-note">{locale === "zh" ? "完整密钥只在创建成功响应中出现一次；列表永远只返回前缀与末四位。" : "The full key appears only in the successful create response; lists return only its prefix and last four characters."}</p></section>
      <section id="workflow"><h2>{locale === "zh" ? "创建草稿、上传五个槽位并提交" : "Create a draft, upload five slots, and submit"}</h2><ol><li><code>POST /api/v1/tasks</code> · <code>{`{"title":"Friday shooting","mode":"quick"}`}</code></li><li><code>PUT /api/v1/tasks/{`{task_id}`}/inputs/{`{slot}`}</code> · {locale === "zh" ? "multipart 字段" : "multipart field"} <code>file</code></li><li><code>POST /api/v1/tasks/{`{task_id}`}/submit</code> · {locale === "zh" ? "无请求体" : "no request body"}</li></ol><div className="slot-row">{["enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04"].map(slot => <code key={slot}>{slot}</code>)}</div><p>{locale === "zh" ? "每次 PUT 上传一个完整文件；对同一槽位再次成功上传会原子替换旧文件。提交前五个槽位必须全部有效。" : "Each PUT uploads one complete file. A later successful upload atomically replaces that slot. All five must be valid before submit."}</p></section>
      <section id="polling"><h2>{locale === "zh" ? "轮询、结果与媒体" : "Polling, results, and media"}</h2><p><code>GET /api/v1/tasks/{`{task_id}`}</code> {locale === "zh" ? "返回 status、progress、stage_message 与 inputs。只轮询到终态。" : "returns status, progress, stage_message, and inputs. Poll only until a terminal state."}</p><p><code>GET /api/v1/tasks/{`{task_id}`}/result</code> {locale === "zh" ? "仅在 completed 后可用，返回参与人数、动作计数、投篮汇总、事件、warnings、disclaimer 和 media URL。" : "is available only after completed and returns participant count, action counts, shot summary, events, warnings, disclaimer, and media URLs."}</p><p>{locale === "zh" ? "媒体种类严格为" : "Media kinds are exactly"}: <code>phases</code>, <code>cam_01</code>, <code>cam_02</code>, <code>cam_03</code>, <code>cam_04</code>. <code>GET /api/v1/tasks/{`{task_id}`}/media/{`{kind}`}</code></p></section>
      <section id="lifecycle"><h2>{locale === "zh" ? "任务生命周期" : "Task lifecycle"}</h2><p className="lifecycle-line">draft → uploading → queued → running → completed</p><ul><li><code>POST /api/v1/tasks/{`{task_id}`}/cancel</code> — {locale === "zh" ? "草稿、上传中、排队或运行任务；运行任务可能先保持 running，stage_message 显示正在取消。" : "draft, uploading, queued, or running tasks; a running task may remain running briefly while stage_message reports cancellation."}</li><li><code>POST /api/v1/tasks/{`{task_id}`}/retry</code> — {locale === "zh" ? "仅 failed 或 canceled，且原始输入仍完整。" : "only failed or canceled tasks whose original inputs remain complete."}</li><li><code>DELETE /api/v1/tasks/{`{task_id}`}</code> — {locale === "zh" ? "可删除草稿或任何终态（completed、failed、canceled、expired）；活动任务要先取消。" : "delete a draft or any terminal task (completed, failed, canceled, expired); cancel active work first."}</li></ul></section>
      <section id="limits"><h2>{locale === "zh" ? "配额、文件限制与保留" : "Quotas, file limits, and retention"}</h2><div className="api-table-wrap"><table><tbody><tr><th>{locale === "zh" ? "草稿" : "Drafts"}</th><td>3 · {formatRetentionDuration(locale, "24 hours")}</td></tr><tr><th>{locale === "zh" ? "未完成任务" : "Unfinished tasks"}</th><td>5</td></tr><tr><th>{locale === "zh" ? "每日提交（UTC）" : "Daily submissions (UTC)"}</th><td>20</td></tr><tr><th>{locale === "zh" ? "活动 API 密钥" : "Active API keys"}</th><td>5</td></tr><tr><th>{locale === "zh" ? "单任务五个文件总量" : "Aggregate five-file job"}</th><td>30 GB</td></tr><tr><th>{locale === "zh" ? "注册数据 / 原始输入 / 结果" : "Enrollment / raw inputs / results"}</th><td>{formatRetentionDuration(locale, "7 days")} / {formatRetentionDuration(locale, "30 days")} / {formatRetentionDuration(locale, "180 days")}</td></tr></tbody></table></div><p>{locale === "zh" ? "视频需通过容器签名与 ffprobe 校验。到期草稿变为 expired；保留清理不删除排队或运行任务。" : "Videos must pass container-signature and ffprobe validation. Expired drafts become expired; retention cleanup does not remove queued or running tasks."}</p></section>
      <section id="examples"><h2>{locale === "zh" ? "可执行 Curl" : "Executable Curl"}</h2><p>{locale === "zh" ? "设置 BASE_URL、API_KEY，并替换五个绝对文件路径。" : "Set BASE_URL and API_KEY, then replace all five absolute file paths."}</p><Code>{curlExample}</Code><h3>{locale === "zh" ? "可执行 Python（requests）" : "Executable Python (requests)"}</h3><p>{locale === "zh" ? "运行前执行：python3 -m pip install requests" : "Before running: python3 -m pip install requests"}</p><Code>{pythonExample}</Code></section>
      <section id="errors"><h2>{locale === "zh" ? "状态与常见错误" : "Statuses and common errors"}</h2><div className="api-table-wrap"><table><thead><tr><th>Status</th><th>{locale === "zh" ? "含义" : "Meaning"}</th></tr></thead><tbody>{[["draft", "可上传或替换输入"], ["uploading", "正在验证一个槽位"], ["queued", "等待单 GPU 队列"], ["running", "处理中"], ["completed", "结果可取"], ["failed", "失败，可在输入仍保留时重试"], ["canceled", "已取消"], ["expired", "24 小时草稿已过期"]].map(([a,b]) => <tr key={a}><td><code>{a}</code></td><td>{locale === "zh" ? b : ({draft:"Inputs may be uploaded or replaced",uploading:"One slot is being validated",queued:"Waiting for the single-GPU queue",running:"Processing",completed:"Result is available",failed:"Failed; retry while inputs remain",canceled:"Canceled",expired:"24-hour draft expired"} as Record<string,string>)[a]}</td></tr>)}</tbody></table></div><div className="api-table-wrap"><table><thead><tr><th>HTTP</th><th>{locale === "zh" ? "处理" : "Handling"}</th></tr></thead><tbody><tr><td>400 / 422</td><td>{locale === "zh" ? "请求或视频无效；修正后重试。" : "Invalid request or video; correct it and retry."}</td></tr><tr><td>401</td><td>{locale === "zh" ? "密钥无效、过期或已撤销。" : "Key is invalid, expired, or revoked."}</td></tr><tr><td>404</td><td>{locale === "zh" ? "任务、媒体或密钥不属于当前账户或不存在。" : "Task, media, or key is missing or belongs to another account."}</td></tr><tr><td>409</td><td>{locale === "zh" ? "生命周期冲突、输入不全或已有上传。" : "Lifecycle conflict, incomplete inputs, or another upload is active."}</td></tr><tr><td>413</td><td>{locale === "zh" ? "上传超过限制。" : "Upload exceeds the limit."}</td></tr><tr><td>429</td><td>{locale === "zh" ? "账户配额已满。" : "Account quota reached."}</td></tr><tr><td>503 / 507</td><td>{locale === "zh" ? "服务未就绪或本地空间不足；稍后重试。" : "Service unavailable or insufficient local storage; retry later."}</td></tr></tbody></table></div></section>
    </main>
    <aside className="api-toc"><nav aria-label={c.toc}><strong>{c.toc}</strong>{toc.map(([id,label]) => <a key={id} href={`#${id}`}>{label}</a>)}</nav></aside>
  </>;
}
