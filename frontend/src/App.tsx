import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import {
  Link,
  Navigate,
  Outlet,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";

import {
  Analysis,
  api,
  errorMessage,
  Preset,
  ProductResult,
  Readiness,
  uploadAnalysis,
} from "./api";

const actionNames: Record<string, string> = {
  triple_threat: "三威胁 / 突破",
  free_throw: "罚篮",
  jump_shot: "跳投",
  layup: "上篮",
};

const statusNames: Record<string, string> = {
  queued: "排队中",
  registering: "参与者注册",
  perception: "人体感知",
  ball_tracking: "球轨跟踪",
  synchronizing: "多机位同步",
  action_recognition: "动作识别",
  outcome_detection: "命中判定",
  exporting: "结果导出",
  visualizing: "复核视频",
  completed: "已完成",
  failed: "失败",
  canceled: "已取消",
  cancel_requested: "正在取消",
  interrupted: "已中断",
};

const stageOrder = [
  "queued",
  "registering",
  "perception",
  "ball_tracking",
  "synchronizing",
  "action_recognition",
  "outcome_detection",
  "exporting",
  "visualizing",
  "completed",
];

function Shell() {
  const navigate = useNavigate();
  async function logout() {
    await api.POST("/api/v1/logout");
    navigate("/login");
  }
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/">
          <span className="brand-mark">B</span>
          <span><b>篮球课堂</b><small>训练复盘工作台</small></span>
        </Link>
        <nav>
          <Link to="/">首页</Link>
          <Link className="button small primary" to="/upload">新建分析</Link>
          <button className="button small ghost" onClick={logout}>退出</button>
        </nav>
      </header>
      <main className="page"><Outlet /></main>
      <footer>AI 识别结果，仅供训练复盘 · 本地运行，不上传公网</footer>
    </div>
  );
}

function LoginPage() {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const body = new URLSearchParams();
    body.set("username", String(data.get("username") || ""));
    body.set("password", String(data.get("password") || ""));
    const response = await fetch("/api/v1/login/access-token", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    setPending(false);
    if (!response.ok) {
      setError("用户名或密码不正确");
      return;
    }
    navigate("/");
  }
  return (
    <div className="login-page">
      <section className="login-hero">
        <div className="court-lines" />
        <span className="eyebrow">LOCAL TRAINING REVIEW</span>
        <h1>把多机位录像，<br />变成可复核的课堂记录。</h1>
        <p>四类篮球动作、独立球轨统计、匿名时间线和五路复核视频，都留在本机。</p>
      </section>
      <form className="login-card" onSubmit={submit}>
        <div className="brand-mark large">B</div>
        <h2>管理员登录</h2>
        <p>使用部署时配置的本地管理员账号。</p>
        <label>用户名<input name="username" autoComplete="username" required /></label>
        <label>密码<input name="password" type="password" autoComplete="current-password" required /></label>
        {error && <div className="alert danger">{error}</div>}
        <button className="button primary wide" disabled={pending}>{pending ? "登录中…" : "进入工作台"}</button>
      </form>
    </div>
  );
}

function useHomeData() {
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [unauthorized, setUnauthorized] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([
      api.GET("/api/v1/system/readiness"),
      api.GET("/api/v1/presets"),
      api.GET("/api/v1/analyses"),
    ]).then(([readyResponse, presetsResponse, analysesResponse]) => {
      if (readyResponse.response.status === 401) {
        setUnauthorized(true);
        return;
      }
      if (readyResponse.error || presetsResponse.error || analysesResponse.error) {
        setError("无法读取工作台数据");
        return;
      }
      setReadiness(readyResponse.data as Readiness);
      setPresets(presetsResponse.data as Preset[]);
      setAnalyses(analysesResponse.data || []);
    });
  }, []);
  return { readiness, presets, analyses, unauthorized, error };
}

function HomePage() {
  const { readiness, presets, analyses, unauthorized, error } = useHomeData();
  if (unauthorized) return <Navigate to="/login" replace />;
  return (
    <>
      <section className="hero-panel">
        <div>
          <span className="eyebrow">FOUR-CAMERA BASKETBALL REVIEW</span>
          <h1>训练结束后，先看证据，再看结论。</h1>
          <p>上传 cam02 注册视频与 cam01–04 四路动作视频。动作数量和投篮结果分别检测，不强制一一对应。</p>
          <Link className="button primary" to="/upload">上传五路视频</Link>
        </div>
        <ReadinessBadge readiness={readiness} />
      </section>
      {error && <div className="alert danger">{error}</div>}
      <SectionTitle title="预置样例" subtitle="直接打开已有结果；只有“重新分析”才会占用 GPU。" />
      <div className="preset-grid">
        {presets.map((preset, index) => (
          <article className="preset-card" key={preset.id}>
            <span className={`preset-index tone-${index + 1}`}>0{index + 1}</span>
            <div><h3>{preset.title}</h3><p>{preset.description}</p></div>
            <small>完整分析约 {preset.expected_minutes} 分钟</small>
            <Link className="button secondary wide" to={`/presets/${preset.id}`}>秒开结果</Link>
          </article>
        ))}
      </div>
      <SectionTitle title="历史任务" subtitle="GPU 每次只执行一个任务，其余任务保留在 SQLite 队列中。" action={<Link to="/upload">新建分析 →</Link>} />
      <AnalysisTable analyses={analyses} />
    </>
  );
}

function ReadinessBadge({ readiness }: { readiness: Readiness | null }) {
  if (!readiness) return <aside className="readiness loading">正在检查运行环境…</aside>;
  const failed = readiness.checks.filter((item) => !item.ready);
  return (
    <aside className={`readiness ${readiness.ready ? "ready" : "blocked"}`}>
      <span className="status-dot" />
      <div>
        <b>{readiness.mode === "simulation" ? "开发模拟引擎" : readiness.ready ? "真实分析已就绪" : "真实分析未就绪"}</b>
        <small>{readiness.mode === "simulation" ? "仅用于开发测试，不执行真实推理" : readiness.ready ? "可创建 GPU 分析任务" : failed.map((item) => item.name).join("、") || "正在检查"}</small>
      </div>
    </aside>
  );
}

function SectionTitle({ title, subtitle, action }: { title: string; subtitle: string; action?: ReactNode }) {
  return <div className="section-title"><div><h2>{title}</h2><p>{subtitle}</p></div>{action}</div>;
}

function AnalysisTable({ analyses }: { analyses: Analysis[] }) {
  if (!analyses.length) return <div className="empty-state">尚无分析任务。预置结果不会出现在任务队列中。</div>;
  return (
    <div className="table-wrap">
      <table><thead><tr><th>标题</th><th>来源</th><th>模式</th><th>状态</th><th>创建时间</th><th /></tr></thead>
        <tbody>{analyses.map((analysis) => <tr key={analysis.id}>
          <td><b>{analysis.title}</b><small>{analysis.id.slice(0, 8)}</small></td>
          <td>{analysis.source_type === "preset" ? "预置重跑" : "五文件上传"}</td>
          <td>{analysis.mode === "quick" ? "快速" : "完整"}</td>
          <td><span className={`status-pill ${analysis.status}`}>{statusNames[analysis.status] || analysis.status}</span></td>
          <td>{new Date(analysis.created_at).toLocaleString("zh-CN")}</td>
          <td><Link to={`/analyses/${analysis.id}`}>查看 →</Link></td>
        </tr>)}</tbody>
      </table>
    </div>
  );
}

function looksLikeVideoHeader(bytes: Uint8Array) {
  if (bytes.length < 4) return false;
  if (bytes[0] === 0x1a && bytes[1] === 0x45 && bytes[2] === 0xdf && bytes[3] === 0xa3) return true;
  if (bytes[0] === 0x46 && bytes[1] === 0x4c && bytes[2] === 0x56) return true;
  if (
    bytes.length >= 12 &&
    bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 &&
    bytes[8] === 0x41 && bytes[9] === 0x56 && bytes[10] === 0x49 && bytes[11] === 0x20
  ) return true;
  if (bytes.length >= 8 && bytes[4] === 0x66 && bytes[5] === 0x74 && bytes[6] === 0x79 && bytes[7] === 0x70) return true;
  return bytes[0] === 0x00 && bytes[1] === 0x00 && bytes[2] === 0x01 && (bytes[3] === 0xba || bytes[3] === 0xb3);
}

async function assertUploadedVideos(form: FormData) {
  const labels: Record<string, string> = {
    enrollment_video: "注册视频",
    cam_01: "cam01 视频",
    cam_02: "cam02 视频",
    cam_03: "cam03 视频",
    cam_04: "cam04 视频",
  };
  for (const [name, title] of Object.entries(labels)) {
    const value = form.get(name);
    if (!(value instanceof File)) continue;
    const header = new Uint8Array(await value.slice(0, 16).arrayBuffer());
    if (!looksLikeVideoHeader(header)) {
      throw { detail: `${title} 不是可识别的视频文件。请上传 mkv/mp4/mov/webm，不要改扩展名后上传 PDF 或其他文档。` };
    }
  }
}

function UploadPage() {
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      const form = new FormData(event.currentTarget);
      await assertUploadedVideos(form);
      const analysis = await uploadAnalysis(form);
      navigate(`/analyses/${analysis.id}`);
    } catch (reason) {
      setError(errorMessage(reason, "创建任务失败，请检查运行环境和视频文件。"));
      setPending(false);
    }
  }
  const files = [
    ["enrollment_video", "注册视频", "cam02 顺序正面注册，自动识别 1–6 人"],
    ["cam_01", "动作视频 · cam01", "左侧边线"],
    ["cam_02", "动作视频 · cam02", "右侧边线"],
    ["cam_03", "动作视频 · cam03", "底线与动作主时钟"],
    ["cam_04", "动作视频 · cam04", "篮筐与球轨"],
  ];
  return (
    <div className="narrow-page">
      <div className="backline"><Link to="/">← 返回首页</Link></div>
      <SectionTitle title="新建训练分析" subtitle="五个视频需来自同一段训练；部署现场使用固定同步偏移。" />
      <form className="upload-form" onSubmit={submit}>
        <div className="form-row">
          <label>任务标题<input name="title" placeholder="例如：周三投篮训练" required maxLength={120} /></label>
          <fieldset><legend>分析模式</legend>
            <label className="radio-card"><input type="radio" name="mode" value="quick" defaultChecked /><span><b>快速模式</b><small>辅助机位与球跟踪降采样</small></span></label>
            <label className="radio-card"><input type="radio" name="mode" value="full" /><span><b>完整模式</b><small>保持科研引擎 full 路径</small></span></label>
          </fieldset>
        </div>
        <div className="file-stack">
          {files.map(([name, title, hint], index) => <label className="file-input" key={name}>
            <span className="file-number">{index + 1}</span>
            <span><b>{title}</b><small>{hint}</small></span>
            <input type="file" name={name} accept="video/*,.mkv" required />
          </label>)}
        </div>
        <div className="notice"><b>处理说明</b><span>快速与完整模式都会生成复核视频，但均不承诺实时完成。任务在本机串行使用 GPU。</span></div>
        {error && <div className="alert danger">{error}</div>}
        <button className="button primary wide" disabled={pending}>{pending ? "正在上传…" : "上传并加入队列"}</button>
      </form>
    </div>
  );
}

function AnalysisPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [result, setResult] = useState<ProductResult | null>(null);
  const [error, setError] = useState("");

  async function load() {
    const response = await api.GET("/api/v1/analyses/{analysis_id}", { params: { path: { analysis_id: id } } });
    if (response.response.status === 401) { navigate("/login"); return; }
    if (response.error) { setError("任务不存在或无法读取"); return; }
    setAnalysis(response.data);
    if (response.data.status === "completed") {
      const resultResponse = await api.GET("/api/v1/analyses/{analysis_id}/result", { params: { path: { analysis_id: id } } });
      if (resultResponse.data) setResult(resultResponse.data);
      else setError("任务已完成，但结果文件不可用");
    }
  }
  useEffect(() => {
    load();
    const terminal = analysis && ["completed", "failed", "canceled", "interrupted"].includes(analysis.status);
    const timer = terminal || result ? undefined : window.setInterval(load, 2500);
    return () => window.clearInterval(timer);
  }, [id, result, analysis?.status]);

  async function mutate(action: "cancel" | "retry") {
    const path = action === "cancel" ? "/api/v1/analyses/{analysis_id}/cancel" : "/api/v1/analyses/{analysis_id}/retry";
    const response = await api.POST(path, { params: { path: { analysis_id: id } } });
    if (response.data) { setAnalysis(response.data); setResult(null); }
    else setError(errorMessage(response.error, "操作失败，请稍后重试"));
  }
  async function remove() {
    if (!window.confirm("删除该任务的上传文件、原始数据和结果？此操作无法恢复。")) return;
    const response = await api.DELETE("/api/v1/analyses/{analysis_id}", { params: { path: { analysis_id: id } } });
    if (response.response.ok) navigate("/");
    else setError(errorMessage(response.error, "删除失败，请刷新任务状态"));
  }
  if (error) return <div className="alert danger">{error}</div>;
  if (!analysis) return <div className="loading-panel">正在读取任务…</div>;
  if (result) return <ResultView title={analysis.title} result={result} back="/" />;
  const retryable = ["failed", "canceled", "interrupted"].includes(analysis.status);
  const cancelable = ["queued", ...stageOrder.slice(1, -1)].includes(analysis.status);
  return (
    <div className="narrow-page">
      <div className="backline"><Link to="/">← 返回首页</Link></div>
      <section className="task-heading"><span className={`status-pill ${analysis.status}`}>{statusNames[analysis.status]}</span><h1>{analysis.title}</h1><p>{analysis.stage_message}</p></section>
      <div className="progress-card">
        <div className="progress-top"><b>处理进度</b><span>{analysis.progress}%</span></div>
        <div className="progress-track"><i style={{ width: `${analysis.progress}%` }} /></div>
        <div className="stage-list">{stageOrder.slice(0, -1).map((stage, index) => {
          const currentIndex = stageOrder.indexOf(analysis.status);
          const done = analysis.status === "completed" || index < currentIndex;
          const active = stage === analysis.status;
          return <div className={`${done ? "done" : ""} ${active ? "active" : ""}`} key={stage}><span>{done ? "✓" : index + 1}</span>{statusNames[stage]}</div>;
        })}</div>
      </div>
      {analysis.error_message && <div className="alert danger"><b>{analysis.error_code}</b>{analysis.error_message}</div>}
      <div className="task-actions">
        {cancelable && <button className="button secondary" onClick={() => mutate("cancel")}>取消任务</button>}
        {retryable && <button className="button primary" onClick={() => mutate("retry")}>从原输入重新运行</button>}
        {!cancelable && <button className="button danger" onClick={remove}>删除任务</button>}
      </div>
    </div>
  );
}

function PresetPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [result, setResult] = useState<ProductResult | null>(null);
  const [error, setError] = useState("");
  const [rerunning, setRerunning] = useState(false);
  useEffect(() => {
    api.GET("/api/v1/presets/{preset_id}/result", { params: { path: { preset_id: id } } }).then((response) => {
      if (response.response.status === 401) navigate("/login");
      else if (response.data) setResult(response.data);
      else setError("预置结果不可用");
    });
  }, [id]);
  async function rerun() {
    setRerunning(true);
    const response = await api.POST("/api/v1/analyses/preset", { body: { preset_id: id, mode: "full" } });
    if (response.data) navigate(`/analyses/${response.data.id}`);
    else { setError(errorMessage(response.error, "运行环境未就绪")); setRerunning(false); }
  }
  if (error) return <div className="alert danger">{error}</div>;
  if (!result) return <div className="loading-panel">正在导入最终分组报告…</div>;
  return <ResultView title="预置训练样例" result={result} back="/" action={<button className="button secondary" onClick={rerun} disabled={rerunning}>{rerunning ? "创建中…" : "使用 GPU 重新分析"}</button>} />;
}

function ResultView({ title, result, back, action }: { title: string; result: ProductResult; back: string; action?: ReactNode }) {
  const counts = result.action_counts as Record<string, number>;
  const mediaOrder = ["phases", "cam_01", "cam_02", "cam_03", "cam_04"];
  const mediaEntries = [
    ...mediaOrder.filter((kind) => result.media[kind]).map((kind) => [kind, result.media[kind]] as const),
    ...Object.entries(result.media).filter(([kind]) => !mediaOrder.includes(kind)),
  ];
  return (
    <div>
      <div className="result-head"><div><Link to={back}>← 返回</Link><span className="eyebrow">ANALYSIS RESULT</span><h1>{title}</h1><p>{result.disclaimer}</p></div>{action}</div>
      {(result.warnings || []).map((warning) => <div className="alert warning" key={warning}>{warning}</div>)}
      <div className="metric-grid">
        <Metric label="匿名参与者" value={result.registered_participant_count} suffix="人" />
        {Object.entries(actionNames).map(([key, label]) => <Metric key={key} label={label} value={counts[key] || 0} suffix="次" />)}
      </div>
      <SectionTitle title="球轨投篮统计" subtitle="与动作识别独立计算；无法可靠关联的结果只计入汇总。" />
      <div className="shot-panel">
        <Metric label="出手" value={result.shots.attempts} suffix="次" />
        <Metric label="命中" value={result.shots.makes} suffix="次" />
        <Metric label="未中" value={result.shots.misses} suffix="次" />
        <Metric label="无法判断" value={result.shots.undetermined} suffix="次" />
        <Metric label="命中率" value={result.shots.make_rate == null ? "—" : Math.round(result.shots.make_rate * 100)} suffix={result.shots.make_rate == null ? "" : "%"} />
      </div>
      <SectionTitle title="匿名动作时间线" subtitle="不显示身份或个人统计；命中结果仅在可以可靠关联时出现。" />
      {result.events.length ? <div className="timeline">{result.events.map((event) => <div className="timeline-event" key={event.event_index}>
        <span className="event-number">{String(event.event_index).padStart(2, "0")}</span>
        <div><b>{actionNames[event.action_type]}</b><small>{formatTime(event.start_ms)} – {formatTime(event.end_ms)} · 关键时刻 {formatTime(event.time_ms)}</small></div>
        <span className={`outcome ${event.result || "none"}`}>{event.result === "make" ? "命中" : event.result === "miss" ? "未中" : event.result === "undetermined" ? "无法判断" : "未关联"}</span>
      </div>)}</div> : <div className="empty-state">未识别到当前版本支持的动作。</div>}
      <SectionTitle title="复核视频" subtitle="四宫格为人体/球轨标注画面，编号只是本次会话内匿名跟踪标签；四路单独视频为各机位原片。" />
      <div className="video-grid">{mediaEntries.map(([kind, url]) => <figure className={kind === "phases" ? "wide-video" : ""} key={kind}>
        <video controls preload="metadata" src={url} /><figcaption>{mediaName(kind)}</figcaption>
      </figure>)}</div>
    </div>
  );
}

function Metric({ label, value, suffix }: { label: string; value: string | number; suffix: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}<small>{suffix}</small></strong></div>;
}

function formatTime(ms: number) {
  const seconds = Math.max(0, ms / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}

function mediaName(kind: string) {
  return ({
    cam_01: "cam01 原视频",
    cam_02: "cam02 原视频",
    cam_03: "cam03 原视频",
    cam_04: "cam04 原视频",
    phases: "四宫格标注复核",
  } as Record<string, string>)[kind] || kind;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Shell />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/analyses/:id" element={<AnalysisPage />} />
        <Route path="/presets/:id" element={<PresetPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
