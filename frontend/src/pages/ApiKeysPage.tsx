import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
import { apiCenterApi } from "../apiCenter/api";
import type { AccountUsage, ApiKey, CreatedApiKey } from "../apiCenter/api";
import { apiCopy } from "../apiCenter/copy";
import { Icon } from "../components/Icon";
import { useLocale } from "../providers/LocaleProvider";

function formatDate(value: string | null, locale: "zh" | "en") {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    const first = root.current?.querySelector<HTMLElement>("input, button");
    first?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab" || !root.current) return;
      const items = [...root.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled)')];
      if (!items.length) return;
      const firstItem = items[0], last = items.at(-1)!;
      if (event.shiftKey && document.activeElement === firstItem) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); firstItem.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return <div className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section ref={root} className="api-modal" role="dialog" aria-modal="true" aria-labelledby="api-modal-title"><h2 id="api-modal-title">{title}</h2>{children}</section></div>;
}

export function ApiKeysPage() {
  const { locale } = useLocale();
  const c = apiCopy[locale];
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [usage, setUsage] = useState<AccountUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [days, setDays] = useState(90);
  const [busy, setBusy] = useState(false);
  const [secret, setSecret] = useState<CreatedApiKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const [revoke, setRevoke] = useState<ApiKey | null>(null);
  const [notice, setNotice] = useState("");
  const modalTrigger = useRef<HTMLElement | null>(null);

  const restoreModalTrigger = () => requestAnimationFrame(() => modalTrigger.current?.focus());
  const closeCreating = () => { setCreating(false); restoreModalTrigger(); };
  const closeSecret = () => { setSecret(null); restoreModalTrigger(); };
  const closeRevoke = () => { setRevoke(null); restoreModalTrigger(); };

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [nextKeys, nextUsage] = await Promise.all([apiCenterApi.keys(), apiCenterApi.usage()]);
      setKeys(nextKeys); setUsage(nextUsage);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Request failed"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true); setError("");
    try {
      const created = await apiCenterApi.createKey({ name: name.trim(), expires_in_days: days });
      setCreating(false); setName(""); setSecret(created); setCopied(false); setCopyFailed(false);
      const [nextKeys, nextUsage] = await Promise.all([apiCenterApi.keys(), apiCenterApi.usage()]);
      setKeys(nextKeys); setUsage(nextUsage);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Request failed"); }
    finally { setBusy(false); }
  }
  async function confirmRevoke() {
    if (!revoke) return;
    setBusy(true);
    try {
      await apiCenterApi.revokeKey(revoke.id);
      closeRevoke(); setNotice(locale === "zh" ? "密钥已撤销" : "Key revoked");
      const [nextKeys, nextUsage] = await Promise.all([apiCenterApi.keys(), apiCenterApi.usage()]);
      setKeys(nextKeys); setUsage(nextUsage);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Request failed"); }
    finally { setBusy(false); }
  }
  const quotaCards = usage ? [
    [locale === "zh" ? "今日提交" : "Submitted today", usage.submitted_today],
    [locale === "zh" ? "未完成任务" : "Unfinished tasks", usage.unfinished_tasks],
    [locale === "zh" ? "草稿" : "Drafts", usage.drafts],
    [locale === "zh" ? "活动密钥" : "Active keys", usage.active_api_keys],
  ] as const : [];

  return <main className="api-content api-keys-page">
    <header className="api-page-header"><span>ACCOUNT · API</span><h1>{c.keysTitle}</h1><p>{c.keysLead}</p></header>
    {error && <div className="inline-error" role="alert">{error}</div>}
    {notice && <p className="api-notice" role="status">{notice}</p>}
    {loading ? <p role="status">{locale === "zh" ? "正在加载 API 数据…" : "Loading API data…"}</p> : <>
      <section aria-labelledby="usage-title"><div className="api-section-heading"><div><h2 id="usage-title">{locale === "zh" ? "账户用量" : "Account usage"}</h2><p>{locale === "zh" ? "当前 Beta 配额按账户隔离。" : "Current beta quotas are isolated by account."}</p></div></div><div className="api-quota-grid">{quotaCards.map(([label, quota]) => <article key={label}><span>{label}</span><strong>{quota.used} / {quota.limit}</strong><i><b style={{ width: `${Math.min(100, quota.used / quota.limit * 100)}%` }}/></i></article>)}</div></section>
      <section aria-labelledby="key-list-title"><div className="api-section-heading"><div><h2 id="key-list-title">{locale === "zh" ? `API 密钥 (${usage?.active_api_keys.used ?? 0}/5)` : `API keys (${usage?.active_api_keys.used ?? 0}/5)`}</h2><p>{locale === "zh" ? "默认 90 天有效，最多五个活动密钥。列表不保存完整密钥。" : "Keys last 90 days by default, with at most five active keys. Full secrets are not retained in this list."}</p></div><button className="button button-primary" type="button" disabled={(usage?.active_api_keys.used ?? 0) >= 5} onClick={event => { modalTrigger.current = event.currentTarget; setCreating(true); }}><Icon name="plus"/>{locale === "zh" ? "创建 API 密钥" : "Create API key"}</button></div>
        <div className="api-key-table-wrap"><table className="api-key-table"><thead><tr><th>{locale === "zh" ? "名称" : "Name"}</th><th>{locale === "zh" ? "密钥" : "Key"}</th><th>{locale === "zh" ? "状态" : "Status"}</th><th>{locale === "zh" ? "创建 / 到期" : "Created / expires"}</th><th>{locale === "zh" ? "操作" : "Action"}</th></tr></thead><tbody>{keys.map(key => <tr key={key.id}><td><strong>{key.name}</strong></td><td><code>{key.prefix}••••{key.last_four}</code></td><td><span className={`key-status ${key.status}`}>{locale === "zh" ? ({active:"活动",expired:"已过期",revoked:"已撤销"} as const)[key.status] : key.status}</span></td><td><span>{formatDate(key.created_at, locale)}</span><small>{formatDate(key.expires_at, locale)}</small></td><td>{key.status !== "revoked" ? <button className="table-action action-delete" type="button" aria-label={`${locale === "zh" ? "撤销" : "Revoke"} ${key.name}`} onClick={event => { modalTrigger.current = event.currentTarget; setRevoke(key); }}><Icon name="trash" size={15}/>{locale === "zh" ? "撤销" : "Revoke"}</button> : "—"}</td></tr>)}</tbody></table></div>
      </section>
      {usage && <section className="api-retention" aria-labelledby="retention-title"><h2 id="retention-title">{locale === "zh" ? "数据保留" : "Data retention"}</h2><p>{locale === "zh" ? "草稿 / 注册数据 / 原始输入 / 结果" : "Drafts / enrollment / raw inputs / results"}</p><strong>{usage.retention.drafts} · {usage.retention.enrollment_data} · {usage.retention.raw_inputs} · {usage.retention.results}</strong></section>}
    </>}
    {creating && <Modal title={locale === "zh" ? "创建 API 密钥" : "Create API key"} onClose={() => !busy && closeCreating()}><form onSubmit={create}><label>{locale === "zh" ? "密钥名称" : "Key name"}<input required value={name} onChange={event => setName(event.target.value)} /></label><label>{locale === "zh" ? "有效期" : "Expires in"}<select value={days} onChange={event => setDays(Number(event.target.value))}><option value={30}>30 {locale === "zh" ? "天" : "days"}</option><option value={90}>90 {locale === "zh" ? "天" : "days"}</option><option value={365}>365 {locale === "zh" ? "天" : "days"}</option></select></label><div><button className="button button-outline" type="button" disabled={busy} onClick={closeCreating}>{locale === "zh" ? "取消" : "Cancel"}</button><button className="button button-primary" type="submit" disabled={busy}>{locale === "zh" ? "创建密钥" : "Create key"}</button></div></form></Modal>}
    {secret && <Modal title={locale === "zh" ? "保存新密钥" : "Save your new key"} onClose={closeSecret}><div className="secret-warning" role="alert">{locale === "zh" ? "完整密钥只显示一次。现在复制并保存在安全位置；关闭后无法再次查看。" : "The full key is shown only once. Copy and store it securely now; it cannot be shown again."}</div><code className="secret-value">{secret.secret}</code><div className="secret-actions"><button className="button button-outline" type="button" onClick={async () => { try { await navigator.clipboard.writeText(secret.secret); setCopied(true); setCopyFailed(false); } catch { setCopied(false); setCopyFailed(true); } }}>{locale === "zh" ? "复制完整密钥" : "Copy full key"}</button>{copied && <span role="status">{locale === "zh" ? "已复制" : "Copied"}</span>}{copyFailed && <span role="alert">{locale === "zh" ? "复制失败，请手动选择密钥" : "Copy failed; select the key manually"}</span>}<button className="button button-primary" type="button" onClick={closeSecret}>{locale === "zh" ? "我已保存" : "I saved it"}</button></div></Modal>}
    {revoke && <Modal title={locale === "zh" ? "撤销 API 密钥" : "Revoke API key"} onClose={() => !busy && closeRevoke()}><p>{locale === "zh" ? `撤销“${revoke.name}”后，使用它的请求将立即失效。` : `Requests using “${revoke.name}” will stop working immediately.`}</p><div className="modal-actions"><button className="button button-outline" type="button" disabled={busy} onClick={closeRevoke}>{locale === "zh" ? "取消" : "Cancel"}</button><button className="button button-danger" type="button" disabled={busy} onClick={() => void confirmRevoke()}>{locale === "zh" ? "确认撤销" : "Revoke key"}</button></div></Modal>}
  </main>;
}
