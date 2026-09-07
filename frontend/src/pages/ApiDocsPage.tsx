import { Icon } from "../components/Icon";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiChapters, apiHeadings } from "../apiCenter/chapters";
import type { ApiHeadingId } from "../apiCenter/chapters";
import { useMediaQuery } from "../apiCenter/useMediaQuery";
import { useDocsNavigation } from "../apiCenter/useDocsNavigation";
import { useLocale } from "../providers/LocaleProvider";
import { apiCopy } from "../apiCenter/copy";
import { formatRetentionDuration } from "../localization";
import { useAuth } from "../providers/AuthProvider";
import { apiCenterApi } from "../apiCenter/api";
import type { AccountUsage, AccountLimits } from "../apiCenter/api";

const curlExample = `export BASE_URL="http://127.0.0.1:8000"
export API_KEY="dsb_live_replace_with_your_key"
export SYNC_CONFIG="/absolute/path/confirmed-sync.json"

set -eu

TASK_ID="$(curl -fsS -X POST "$BASE_URL/api/v1/tasks" \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"title":"Friday shooting","mode":"quick","analyst_locale":"zh","enrollment_mode":"sequential","expected_persons":4}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"

curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/inputs/enrollment_video" -H "Authorization: Bearer $API_KEY" -F "file=@/absolute/path/enrollment.mp4"
curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/inputs/cam_01" -H "Authorization: Bearer $API_KEY" -F "file=@/absolute/path/cam_01.mp4"
curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/inputs/cam_02" -H "Authorization: Bearer $API_KEY" -F "file=@/absolute/path/cam_02.mp4"
curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/inputs/cam_03" -H "Authorization: Bearer $API_KEY" -F "file=@/absolute/path/cam_03.mp4"
curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/inputs/cam_04" -H "Authorization: Bearer $API_KEY" -F "file=@/absolute/path/cam_04.mp4"

SYNC_META="$(curl -fsS "$BASE_URL/api/v1/tasks/$TASK_ID/sync" -H "Authorization: Bearer $API_KEY")"
export SYNC_INPUT_VERSIONS="$(printf '%s' "$SYNC_META" | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["source_versions"]))')"
SYNC_BODY="$(python3 -c 'import json,os; body=json.load(open(os.environ["SYNC_CONFIG"])); body["input_versions"]=json.loads(os.environ["SYNC_INPUT_VERSIONS"]); print(json.dumps(body))')"
curl -fsS -X PUT "$BASE_URL/api/v1/tasks/$TASK_ID/sync" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d "$SYNC_BODY"

curl -fsS -X POST "$BASE_URL/api/v1/tasks/$TASK_ID/submit" -H "Authorization: Bearer $API_KEY"
while :; do
  TASK_JSON="$(curl -fsS "$BASE_URL/api/v1/tasks/$TASK_ID" -H "Authorization: Bearer $API_KEY")"
  STATUS="$(printf '%s' "$TASK_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  case "$STATUS" in
    completed) curl -fsS "$BASE_URL/api/v1/tasks/$TASK_ID/result" -H "Authorization: Bearer $API_KEY"; break ;;
    failed|canceled|expired|interrupted) printf 'Task ended with status: %s\\n' "$STATUS" >&2; exit 1 ;;
    *) sleep 5 ;;
  esac
done`;

const pythonExample = `import json
import os
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
                         json={"title": "Friday shooting", "mode": "full", "analyst_locale": "zh",
                               "enrollment_mode": "sequential", "expected_persons": 4})
response.raise_for_status()
task = response.json()

for slot, path in files.items():
    with path.open("rb") as stream:
        response = requests.put(f"{base_url}/api/v1/tasks/{task['id']}/inputs/{slot}",
                                headers=headers, files={"file": (path.name, stream)})
    response.raise_for_status()

response = requests.get(f"{base_url}/api/v1/tasks/{task['id']}/sync", headers=headers)
response.raise_for_status()
sync = json.loads(Path(os.environ["SYNC_CONFIG"]).read_text())
sync["input_versions"] = response.json()["source_versions"]
response = requests.put(f"{base_url}/api/v1/tasks/{task['id']}/sync", headers=headers, json=sync)
response.raise_for_status()

response = requests.post(f"{base_url}/api/v1/tasks/{task['id']}/submit", headers=headers)
response.raise_for_status()

while True:
    response = requests.get(f"{base_url}/api/v1/tasks/{task['id']}", headers=headers)
    response.raise_for_status()
    task = response.json()
    if task["status"] in {"completed", "failed", "canceled", "expired", "interrupted"}:
        break
    time.sleep(5)

if task["status"] == "completed":
    response = requests.get(f"{base_url}/api/v1/tasks/{task['id']}/result", headers=headers)
    response.raise_for_status()
    print(response.json())`;

function Code({ children }: { children: string }) {
  const { locale } = useLocale();
  return <pre className="api-code" tabIndex={0} aria-label={locale === "zh" ? "代码示例" : "Code example"}><code>{children}</code></pre>;
}

function DocHeading({ id }: { id: ApiHeadingId }) {
  const { locale } = useLocale();
  const heading = apiHeadings.find(item => item.id === id)!;
  const Tag = heading.level === 2 ? "h2" : "h3";
  return <Tag id={id} tabIndex={-1}>{heading.title[locale]}</Tag>;
}

function CurrentLimits() {
  const { locale } = useLocale();
  const { user } = useAuth();
  const [usage, setUsage] = useState<AccountUsage | null>(null);
  const [limits, setLimits] = useState<AccountLimits | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setUsage(null); setLimits(null); setFailed(false);
    if (user && user.role !== "admin") void Promise.all([apiCenterApi.usage(), apiCenterApi.limits()]).then(([value, current]) => {
      if (!value?.drafts || !value?.unfinished_tasks || !value?.submitted_today || !value?.active_api_keys || !value?.retention || !current?.quotas || !current?.application) throw new Error("Invalid quota response");
      if (active) { setUsage(value); setLimits(current); }
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [user?.id, user?.role]);
  if (!user || user.role === "admin") return <p>{locale === "zh" ? "配额按普通账户生效，登录后可查看当前账户的实际限制，管理员调整后以接口返回值为准" : "Quotas apply to business accounts, sign in to see current limits, API responses reflect administrator changes"} <Link to="/api/keys">{locale === "zh" ? "API 管理" : "API management"}</Link></p>;
  if (!usage || !limits) return <p role={failed ? "alert" : "status"}>{locale === "zh" ? failed ? "暂时无法读取当前配额" : "正在读取当前配额" : failed ? "Current quotas could not be loaded" : "Loading current quotas"}</p>;
  const rows = [
    [locale === "zh" ? "草稿" : "Drafts", usage.drafts.limit],
    [locale === "zh" ? "未完成任务" : "Unfinished tasks", usage.unfinished_tasks.limit],
    [locale === "zh" ? "每日提交（UTC）" : "Daily submissions (UTC)", usage.submitted_today.limit],
    [locale === "zh" ? "活动 API 密钥" : "Active API keys", usage.active_api_keys.limit],
    [locale === "zh" ? "每日主动 AI 操作" : "Daily active AI operations", limits.quotas.daily_ai],
    [locale === "zh" ? "单任务上传总量" : "Aggregate task upload", `${limits.application.max_upload_size_gb} GB`],
    [locale === "zh" ? "草稿保留" : "Draft retention", formatRetentionDuration(locale, usage.retention.drafts)],
    [locale === "zh" ? "注册数据保留" : "Enrollment retention", formatRetentionDuration(locale, usage.retention.enrollment_data)],
    [locale === "zh" ? "原始输入保留" : "Input retention", formatRetentionDuration(locale, usage.retention.raw_inputs)],
    [locale === "zh" ? "结果保留" : "Result retention", formatRetentionDuration(locale, usage.retention.results)],
  ];
  return <div className="api-table-wrap"><table><tbody>{rows.map(([label, value]) => <tr key={label}><th scope="row">{label}</th><td>{value}</td></tr>)}</tbody></table></div>;
}

export function ApiDocsPage() {
  const { locale } = useLocale();
  const c = apiCopy[locale];
  const compact = useMediaQuery("(max-width: 1279px)");
  const [expanded, setExpanded] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const { active, tocRef } = useDocsNavigation(locale, expanded, compact);
  const tocLink = (id: ApiHeadingId, label: string) => <Link
    to={{ hash: `#${id}` }}
    aria-current={active === id ? "location" : undefined}
    onClick={event => {
      if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) setExpanded(false);
    }}
  >{label}</Link>;

  return <div className="api-docs-layout">
    <aside className="api-toc" onKeyDown={event => {
      if (event.key === "Escape" && compact && expanded) {
        event.preventDefault();
        setExpanded(false);
        toggleRef.current?.focus();
      }
    }}>
      {compact ? <button ref={toggleRef} className="api-toc-toggle" type="button" aria-expanded={expanded} aria-controls="api-table-of-contents" onClick={() => setExpanded(!expanded)}>{c.toc}<span className="api-lucide-chevron"><Icon name={expanded ? "chevronDown" : "chevronRight"} size={16}/></span></button> : <strong className="api-toc-title">{c.toc}</strong>}
      <nav ref={tocRef} id="api-table-of-contents" aria-label={c.toc} hidden={compact && !expanded}>
        <ul>{apiChapters.map(chapter => <li key={chapter.id}>
          {tocLink(chapter.id, chapter.title[locale])}
          {chapter.children.length > 0 && <ul>{chapter.children.map(child => <li key={child.id}>{tocLink(child.id, child.title[locale])}</li>)}</ul>}
        </li>)}</ul>
      </nav>
    </aside>
    <main className="api-content api-docs">
      <header className="api-page-header"><h1 className="sr-only">{c.docsTitle}</h1><p>{c.docsLead}</p></header>
      <section aria-labelledby="overview">
        <DocHeading id="overview"/>
        <div className="api-table-wrap"><table>
          <thead><tr><th scope="col">{locale === "zh" ? "维度" : "Dimension"}</th><th scope="col">quick</th><th scope="col">full</th></tr></thead>
          <tbody>
            <tr><td>{locale === "zh" ? "处理路径" : "Processing path"}</td><td>{locale === "zh" ? "较短快速路径" : "Shorter fast path"}</td><td>{locale === "zh" ? "完整分析路径" : "Complete analysis path"}</td></tr>
            <tr><td>{locale === "zh" ? "输入" : "Inputs"}</td><td colSpan={2}>{locale === "zh" ? "均需注册视频与 cam_01–cam_04，共五个有效文件" : "Both require enrollment video and cam_01–cam_04: five valid files"}</td></tr>
            <tr><td>{locale === "zh" ? "输出合同" : "Output contract"}</td><td colSpan={2}>{locale === "zh" ? "相同的任务、结果与媒体结构" : "The same task, result, and media shapes"}</td></tr>
          </tbody>
        </table></div>
      </section>
      <section aria-labelledby="auth">
        <DocHeading id="auth"/>
        <p>{locale === "zh" ? "在 API 管理中创建密钥。服务端集成的每个请求都发送：" : "Create a key in API Management. Send this on every server-side request:"}</p>
        <Code>Authorization: Bearer dsb_live_…</Code>
        <p>{locale === "zh" ? "业务 API Key 与网页共用账户权限和配额，停用账户或撤销密钥后不能继续访问，业务密钥不能调用管理员接口" : "API keys share the web account's permissions and quotas, disabled accounts or revoked keys lose access, business keys cannot call admin endpoints"}</p>
        <p className="api-note">{locale === "zh" ? "完整密钥只在创建成功响应中出现一次；列表永远只返回前缀与末四位。" : "The full key appears only in the successful create response; lists return only its prefix and last four characters."}</p>
      </section>
      <section aria-labelledby="workflow">
        <DocHeading id="workflow"/>
        <DocHeading id="create"/>
        <p><code>POST /api/v1/tasks</code></p>
        <Code>{`{"title":"Friday shooting","mode":"quick","analyst_locale":"zh","enrollment_mode":"sequential","expected_persons":4}`}</Code>
        <p>{locale === "zh" ? "enrollment_mode 为 sequential（逐人）或 lineup（并排），expected_persons 为 1–6，草稿可暂不填写人数，提交前必须明确，analyst_locale 决定自动报告的语言" : "enrollment_mode is sequential or lineup, expected_persons is 1–6 and required before submission, analyst_locale sets the language of automatic reports"}</p>
        <p><code>PATCH /api/v1/tasks/{`{task_id}`}</code> · {locale === "zh" ? "提交前可修改任务名称和分析模式，请求体同上，已上传视频保留" : "Before submission, update the title and mode using the same body, keeping uploaded videos"}</p>
        <DocHeading id="upload"/>
        <p><code>PUT /api/v1/tasks/{`{task_id}`}/inputs/{`{slot}`}</code> · {locale === "zh" ? "multipart 字段" : "multipart field"} <code>file</code></p>
        <div className="slot-row">{["enrollment_video", "cam_01", "cam_02", "cam_03", "cam_04"].map(slot => <code key={slot}>{slot}</code>)}</div>
        <p>{locale === "zh" ? "每次 PUT 上传一个完整文件；对同一槽位再次成功上传会原子替换旧文件。" : "Each PUT uploads one complete file. A later successful upload atomically replaces that slot."}</p>
        <DocHeading id="video-sync"/>
        <p><code>GET /api/v1/tasks/{`{task_id}`}/sync</code> · <code>PUT /api/v1/tasks/{`{task_id}`}/sync</code></p>
        <p>{locale === "zh" ? "GET 返回 status、source_versions 和 config，PUT 提交四路同一事件的本地毫秒时间或已确认偏移，input_versions 使用 GET 返回的 source_versions" : "GET returns status, source_versions and config, PUT accepts local milliseconds of the same event in all cameras or verified offsets, use the returned source_versions as input_versions"}</p>
        <Code>{'{"input_versions":{"cam_01":"version-1","cam_02":"version-2","cam_03":"version-3","cam_04":"version-4"},"selected_timestamps_ms":{"cam_01":1000,"cam_02":1100,"cam_03":900,"cam_04":950}}'}</Code>
        <p>{locale === "zh" ? "也可改用 offsets_ms，两种形式不能同时传入，机位 3 的偏移必须为 0，公共时间 = 本地时间 − 机位偏移，调用者负责选取真实对应的瞬间" : "Alternatively send offsets_ms, never both representations, cam_03 offset must be zero, common time = local time − camera offset, the caller is responsible for selecting the same real event"}</p>
        <p>{locale === "zh" ? "不需要打开网页，API 直接提交配置即可完成确认，更换任意动作视频后需使用新版本重新确认，更换注册视频不影响同步" : "No browser interaction is required, submitting valid configuration confirms synchronization, replacing a camera requires fresh confirmation while replacing enrollment does not"}</p>
        <p><code>POST /api/v1/tasks/{`{task_id}`}/sync/preview</code> · <code>GET /api/v1/tasks/{`{task_id}`}/sync/preview</code></p>
        <p>{locale === "zh" ? "可选的可视化预览入口，POST 准备预览，GET 查询 unprepared、preparing、ready 或 failed，ready 返回各机位 video_url、frame_timestamps_ms、duration_ms 与 source_version" : "Optional visual preview, POST prepares media and GET returns unprepared, preparing, ready or failed, ready cameras include video_url, frame_timestamps_ms, duration_ms and source_version"}</p>
        <p><code>GET /api/v1/tasks/{`{task_id}`}/sync/frames/{`{camera}`}?time_ms=1000</code></p>
        <p>{locale === "zh" ? "返回邻近实际帧的 actual_time_ms、frame_index 和 image_data_url，确认时使用实际帧时间，首版支持恒定帧率且无中途剪接或变速的四路视频，不补偿时钟漂移" : "Returns actual_time_ms, frame_index and image_data_url for the nearest frame, confirm actual frame times, v1 supports constant frame rates without midstream edits or speed changes and does not compensate for clock drift"}</p>
        <DocHeading id="submit"/>
        <p><code>POST /api/v1/tasks/{`{task_id}`}/submit</code> · {locale === "zh" ? "无请求体" : "no request body"}</p>
        <p>{locale === "zh" ? "提交前五个槽位必须有效、人数明确且同步已确认，缺少配置返回 422，视频版本改变使同步失效返回 409，提交后使用任务独立快照" : "Submission requires five valid inputs, an explicit person count and confirmed synchronization, missing configuration returns 422 and stale video versions return 409, execution uses an immutable task snapshot"}</p>
        <DocHeading id="single-upload"/>
        <p><code>POST /api/v1/analyses/upload</code></p>
        <p>{locale === "zh" ? "multipart 包含 title、mode、enrollment_mode、expected_persons、analyst_locale、五个视频和 sync，sync 为上述配置的 JSON 字符串，可省略 input_versions，由服务端绑定本次上传文件" : "Multipart fields are title, mode, enrollment_mode, expected_persons, analyst_locale, five videos and sync, encode sync as the JSON above and omit input_versions to bind the newly uploaded files"}</p>
        <p>{locale === "zh" ? "一次上传和分步上传共享校验、配额与后台队列，原路由和既有响应字段保留，旧客户端须补充新必需参数，历史已提交任务不受影响" : "Both upload routes share validation, quotas and queues, existing routes and response fields remain but older clients must add the new required parameters, previously submitted tasks are unaffected"}</p>
      </section>
      <section aria-labelledby="polling">
        <DocHeading id="polling"/>
        <DocHeading id="poll-status"/>
        <p><code>GET /api/v1/tasks/{`{task_id}`}</code> {locale === "zh" ? "返回 status、progress、stage_message 与 inputs。只轮询到终态。" : "returns status, progress, stage_message, and inputs. Poll only until a terminal state."}</p>
        <DocHeading id="result"/>
        <p><code>GET /api/v1/tasks/{`{task_id}`}/result</code> {locale === "zh" ? "仅在 completed 后可用，返回参与人数、动作计数、投篮汇总、事件、warnings、disclaimer 和 media URL。" : "is available only after completed and returns participant count, action counts, shot summary, events, warnings, disclaimer, and media URLs."}</p>
        <DocHeading id="media"/>
        <p>{locale === "zh" ? "媒体种类严格为" : "Media kinds are exactly"}: <code>phases</code>, <code>cam_01</code>, <code>cam_02</code>, <code>cam_03</code>, <code>cam_04</code>.</p>
        <p><code>GET /api/v1/tasks/{`{task_id}`}/media/{`{kind}`}</code></p>
      </section>
      <section aria-labelledby="analyst">
        <DocHeading id="analyst"/>
        <p>{locale === "zh" ? "使用当前账户的 Cookie 会话或 Bearer 认证，分析师不可用时仍可读取已有任务结果与视频" : "Use the current account's cookie session or Bearer authentication; existing task results and videos remain available when the analyst is unavailable"}</p>
        <DocHeading id="analyst-context"/>
        <p><code>GET /api/v1/tasks/{`{id}`}/analyst/context</code></p>
        <p>{locale === "zh" ? "返回 facts、subjects、team_profile_id、comparison_id 和 comparisons；facts 包含指标、匿名球员、warnings、pose_available 与 evidence，每条证据的 times_ms 按 phases 和各机位给出毫秒时间，不应跨机位复用时间" : "Returns facts, subjects, team_profile_id, comparison_id and comparisons; facts include metrics, anonymous subjects, warnings, pose_available and evidence. Each evidence item's times_ms supplies milliseconds for phases and individual cameras; use the selected camera's own time"}</p>
        <p><code>PUT /api/v1/tasks/{`{id}`}/analyst/context</code></p>
        <Code>{'{"subjects":[{"id":"subject-id","profile_id":"profile-id"}],"team_profile_id":null,"comparison_id":null}'}</Code>
        <p>{locale === "zh" ? "统一确认球员或球队档案，null 解除关联，本场报告保持不变，示例不关联个人档案" : "Confirm player and team bindings together, null removes a link, the original session report stays unchanged, presets do not link personal profiles"}</p>
        <p>{locale === "zh" ? "默认不对比，绑定时 comparison_id 传 null，省略也不自动选择历史，历史需属于已绑定档案、同模式且包含相同动作，视频到期后保留的有效指标仍可对比" : "No comparison by default, send comparison_id: null when binding profiles, omission does not automatically select history either, eligible history belongs to a linked profile, uses the same mode and shares an action, retained valid metrics remain comparable after video expiry"}</p>
        <p><code>GET /api/v1/tasks/{`{id}`}/analyst/comparisons?locale=zh&amp;style=coach</code></p>
        <p><code>POST /api/v1/tasks/{`{id}`}/analyst/comparisons</code></p>
        <Code>{'{"comparison_id":"observation-id","locale":"zh","style":"coach"}'}</Code>
        <p>{locale === "zh" ? "GET 接受 locale、style，返回 items 列表，POST 独立排队生成对比报告并返回状态和 comparison_id，重复请求复用结果，不修改绑定或原报告，对比失败可单独重试，档案或历史变化后需重新请求有效对比" : "GET accepts locale and style and returns items, POST queues a separate comparison report and returns its state and comparison_id, repeated requests reuse the result without changing bindings or the original report, comparison failures can be retried independently, request a fresh comparison after profile or history changes"}</p>
        <DocHeading id="analyst-reports"/>
        <p><code>GET /api/v1/tasks/{`{id}`}/analyst/reports?locale=zh</code></p>
        <p><code>POST /api/v1/tasks/{`{id}`}/analyst/reports</code></p>
        <Code>{'{"locale":"zh"}'}</Code>
        <p>{locale === "zh" ? "任务完成后按 analyst_locale（默认 zh）预生成全场与每位球员的 coach、roast 报告，集合返回 items、facts、subjects，每项包含 subject_id、locale、style、status、report、error，subject_id 为 null 代表全场，POST 只补齐缺少版本，另一语言整套按一次主动操作计数，已完成版本直接切换，失败项单独重试" : "Completion prepares coach and roast reports for the session and every player in analyst_locale (zh by default), collections return items, facts and subjects, each item contains subject_id, locale, style, status, report and error, null subject_id means the session, POST fills missing variants only, a new language set costs one active operation, completed variants switch immediately and failed items retry individually"}</p>
        <p><code>GET /api/v1/tasks/{`{id}`}/analyst/report?locale=zh&amp;style=coach</code></p>
        <p><code>POST /api/v1/tasks/{`{id}`}/analyst/report</code></p>
        <Code>{'{"locale":"zh","style":"coach","subject_id":null,"regenerate":false}'}</Code>
        <p>{locale === "zh" ? "GET 和 POST 可选 subject_id 读取或刷新个人完整报告，省略代表全场，regenerate 仅刷新当前版本并按一次主动操作计数，生成期间保留原正文，主动对比同时准备两种语气且不修改本场报告" : "GET and POST accept optional subject_id for a full personal report, omission means the session, regenerate refreshes only that variant for one active operation while keeping its old body, an explicit comparison prepares both styles without changing session reports"}</p>
        <p>{locale === "zh" ? "locale 为 zh 或 en，style 为 coach 或 roast；响应包含 status、report、error，状态为 disabled、waiting、queued、running、completed 或 failed，POST 接受任务后返回 202 或已有结果 200，仅 queued/running 需要轮询" : "locale is zh or en; style is coach or roast. Responses contain status, report and error, with disabled, waiting, queued, running, completed or failed states. POST returns 202 for accepted work or 200 for an existing result; poll only queued/running states"}</p>
        <p>{locale === "zh" ? "报告包含 summary、highlights、players、comparison、suggestions 与模型、语言、风格、生成时间；evidence_ids 仅引用当前 facts.evidence 中的证据" : "Reports include summary, highlights, players, comparison, suggestions, model, locale, style and creation time; evidence_ids refer to entries in the current facts.evidence"}</p>
        <p><code>GET /api/v1/presets/{`{id}`}/analyst/report?locale=zh&amp;style=coach</code></p>
        <p><code>GET /api/v1/presets/{`{id}`}/analyst/reports?locale=zh</code></p>
        <p>{locale === "zh" ? "预设报告只读，额外返回 facts 和 subjects，无生成 POST；仅真实已验证 GLM 报告与当前事实匹配时返回 provenance（provider、verified、facts_hash）" : "Preset reports are read only and also return facts and subjects, with no generation POST. provenance (provider, verified, facts_hash) is present only for a verified real GLM report matching current facts"}</p>
        <DocHeading id="analyst-chat"/>
        <p><code>POST /api/v1/analyst/conversations</code></p>
        <Code>{'{"task_id":"task-id","subject_id":"subject-id","locale":"zh","style":"coach"}'}</Code>
        <p>{locale === "zh" ? "task_id 与 preset_id 二选一，可选 subject_id 与 comparison_id 限定对话范围；返回 id 和 messages" : "Supply either task_id or preset_id; optional subject_id and comparison_id scope the conversation. Returns id and messages"}</p>
        <p><code>GET /api/v1/analyst/conversations/{`{id}`}</code></p>
        <p><code>POST /api/v1/analyst/conversations/{`{id}`}/messages</code></p>
        <p>{locale === "zh" ? '请求体为 {content, request_id}，content 最多 4000 字符，同一发送重试复用 request_id；返回 message_id 与 job_id' : 'Send {content, request_id} with at most 4000 content characters; reuse request_id when retrying the same send. Returns message_id and job_id'}</p>
        <p><code>GET /api/v1/analyst/conversations/{`{id}`}/events</code></p>
        <p>{locale === "zh" ? "SSE 的 message 事件 data 是完整消息（id、role、content、citations、status），按 id 替换而非追加文本；done 表示空闲，断线或刷新后用 GET 对话恢复，消息状态为 queued、running、completed、failed" : "SSE message data is the full message (id, role, content, citations, status); replace by id rather than appending text. done indicates idle. Recover after disconnect or refresh with GET conversation. Message states are queued, running, completed and failed"}</p>
        <DocHeading id="training-profiles"/>
        <p><code>GET /api/v1/training-profiles</code> · <code>POST /api/v1/training-profiles</code></p>
        <Code>{'{"kind":"player","name":"Alex","goals":"Footwork","notes":"Confirmed by the player"}'}</Code>
        <p>{locale === "zh" ? "kind 为 player 或 team；name 必填，goals 和 notes 可选，notes 由用户确认，返回 id、kind、name、goals、notes、created_at、updated_at" : "kind is player or team; name is required, goals and user-confirmed notes are optional. Returns id, kind, name, goals, notes, created_at and updated_at"}</p>
        <p><code>PATCH /api/v1/training-profiles/{`{id}`}</code> · <code>DELETE /api/v1/training-profiles/{`{id}`}</code></p>
        <p>{locale === "zh" ? "PATCH 支持 name、goals、notes；DELETE 删除档案" : "PATCH accepts name, goals and notes; DELETE removes the profile"}</p>
        <p><code>GET /api/v1/training-profiles/{`{id}`}/history</code></p>
        <p>{locale === "zh" ? "返回观察记录数组：id、profile_id、task_id、occurred_at、mode、metrics、media_available；媒体过期后指标仍可保留，task_id 可为空，仅媒体可用时提供回看入口，错误统一使用 detail" : "Returns observations with id, profile_id, task_id, occurred_at, mode, metrics and media_available. Metrics may remain after media expires; task_id can be null. Offer replay only when media is available. Errors use detail"}</p>
      </section>
      <section aria-labelledby="lifecycle">
        <DocHeading id="lifecycle"/>
        <p className="lifecycle-line" tabIndex={0}>draft → uploading → queued → running → completed</p>
        <ul>
          <li><code>POST /api/v1/tasks/{`{task_id}`}/cancel</code> — {locale === "zh" ? "草稿、上传中、排队或运行任务；运行任务可能先保持 running，stage_message 显示正在取消。" : "draft, uploading, queued, or running tasks; a running task may remain running briefly while stage_message reports cancellation."}</li>
          <li><code>POST /api/v1/tasks/{`{task_id}`}/retry</code> — {locale === "zh" ? "仅 failed 或 canceled，且原始输入仍完整。" : "only failed or canceled tasks whose original inputs remain complete."}</li>
          <li><code>POST /api/v1/tasks/{`{task_id}`}/return-to-input</code> — {locale === "zh" ? "失败或中断后返回草稿，保留上传文件以修改登记配置或视频，已有完整报告或输入已清理时不可使用" : "Return failed or interrupted work to a draft while keeping uploads for correction, unavailable when a complete report exists or inputs were cleaned up"}</li>
          <li><code>DELETE /api/v1/tasks/{`{task_id}`}</code> — {locale === "zh" ? "可删除草稿或任何终态（completed、failed、canceled、expired）；活动任务要先取消。" : "delete a draft or any terminal task (completed, failed, canceled, expired); cancel active work first."}</li>
        </ul>
      </section>
      <section aria-labelledby="limits">
        <DocHeading id="limits"/>
        <CurrentLimits/>
        <p><code>GET /api/v1/account/usage</code> · {locale === "zh" ? "读取当前账户的配额与保留周期，实际上传限制由服务端配置决定" : "Read effective account quotas and retention, upload limits are configured by the server"}</p>
        <p>{locale === "zh" ? "视频需通过容器签名与 ffprobe 校验。到期草稿变为 expired；保留清理不删除排队或运行任务。" : "Videos must pass container-signature and ffprobe validation. Expired drafts become expired; retention cleanup does not remove queued or running tasks."}</p>
      </section>
      <section aria-labelledby="examples">
        <DocHeading id="examples"/>
        <DocHeading id="curl"/>
        <p>{locale === "zh" ? "设置 BASE_URL、API_KEY、SYNC_CONFIG，替换五个视频路径，SYNC_CONFIG 文件填写你已确认的 selected_timestamps_ms 或 offsets_ms，不要直接使用示意时间" : "Set BASE_URL, API_KEY and SYNC_CONFIG, replace the five video paths, and fill the sync JSON with your verified selected_timestamps_ms or offsets_ms instead of example times"}</p>
        <Code>{curlExample}</Code>
        <DocHeading id="python"/>
        <p>{locale === "zh" ? "运行前执行：python3 -m pip install requests" : "Before running: python3 -m pip install requests"}</p>
        <Code>{pythonExample}</Code>
      </section>
      <section aria-labelledby="errors">
        <DocHeading id="errors"/>
        <div className="api-table-wrap"><table>
          <thead><tr><th scope="col">Status</th><th scope="col">{locale === "zh" ? "含义" : "Meaning"}</th></tr></thead>
          <tbody>{[["draft", "可上传或替换输入"], ["uploading", "正在验证一个槽位"], ["queued", "等待单 GPU 队列"], ["running", "处理中"], ["completed", "结果可取"], ["failed", "失败，可在输入仍保留时重试"], ["canceled", "已取消"], ["expired", "已达到配置的保留周期"]].map(([status, meaning]) => <tr key={status}><td><code>{status}</code></td><td>{locale === "zh" ? meaning : ({draft:"Inputs may be uploaded or replaced",uploading:"One slot is being validated",queued:"Waiting for the single-GPU queue",running:"Processing",completed:"Result is available",failed:"Failed; retry while inputs remain",canceled:"Canceled",expired:"Configured retention period reached"} as Record<string,string>)[status]}</td></tr>)}</tbody>
        </table></div>
        <div className="api-table-wrap"><table>
          <thead><tr><th scope="col">HTTP</th><th scope="col">{locale === "zh" ? "处理" : "Handling"}</th></tr></thead>
          <tbody>
            <tr><td>400 / 422</td><td>{locale === "zh" ? "请求或视频无效；修正后重试。" : "Invalid request or video; correct it and retry."}</td></tr>
            <tr><td>401</td><td>{locale === "zh" ? "密钥无效、过期或已撤销。" : "Key is invalid, expired, or revoked."}</td></tr>
            <tr><td>403</td><td>{locale === "zh" ? "角色不允许此操作，普通用户与业务密钥不能调用管理接口，管理员不能读取业务内容" : "Role forbidden, business users and API keys cannot call admin endpoints, administrators cannot read business content"}</td></tr>
            <tr><td>404</td><td>{locale === "zh" ? "任务、媒体或密钥不属于当前账户或不存在。" : "Task, media, or key is missing or belongs to another account."}</td></tr>
            <tr><td>409</td><td>{locale === "zh" ? "生命周期冲突、输入不全或已有上传。" : "Lifecycle conflict, incomplete inputs, or another upload is active."}</td></tr>
            <tr><td>413</td><td>{locale === "zh" ? "上传超过限制。" : "Upload exceeds the limit."}</td></tr>
            <tr><td>429</td><td>{locale === "zh" ? "账户配额已满。" : "Account quota reached."}</td></tr>
            <tr><td>503 / 507</td><td>{locale === "zh" ? "服务未就绪或本地空间不足；稍后重试。" : "Service unavailable or insufficient local storage; retry later."}</td></tr>
          </tbody>
        </table></div>
        <p>{locale === "zh" ? "输入与同步错误使用 detail.code、detail.message 和必要字段，运行失败读取任务 error_code、error_message 与 stage_message" : "Input and sync errors use detail.code, detail.message and required fields, execution failures use task error_code, error_message and stage_message"}</p>
        <div className="api-table-wrap"><table><tbody>{[
          ["registration_config_required", "选择注册方式和 1–6 人", "Specify registration method and 1–6 people"],
          ["registration_count_mismatch / registration_quality_failed", "返回输入页核对人数或更换注册视频", "Return to inputs and correct headcount or registration video"],
          ["sync_config_required", "提交四路同步数据", "Submit synchronization data for all four cameras"],
          ["sync_stale", "动作视频已更换，重新读取版本并确认同步", "Action videos changed, read new versions and confirm sync again"],
          ["sync_invalid / sync_no_overlap", "核对时间、参考机位与共同时间区间", "Check times, reference camera and the overlapping interval"],
          ["unsupported_timeline", "使用恒定帧率、无变速或剪接的视频", "Use constant-frame-rate videos without speed changes or edits"],
          ["preview_not_ready / preview_busy / preview_failed", "读取预览状态，再准备或重试，原文件保留", "Read preview state before preparation or retry, originals are preserved"],
        ].map(([code, zh, en]) => <tr key={code}><th scope="row"><code>{code}</code></th><td>{locale === "zh" ? zh : en}</td></tr>)}</tbody></table></div>
      </section>
    </main>
  </div>;
}
