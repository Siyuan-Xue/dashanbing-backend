import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
import { apiCenterApi } from "../apiCenter/api";
import type { AccountUsage, ApiKey, CreatedApiKey } from "../apiCenter/api";
import { apiCopy } from "../apiCenter/copy";
import { Icon } from "../components/Icon";
import { formatRetentionDuration } from "../localization";
import { useLocale } from "../providers/LocaleProvider";

function formatDate(value: string | null, locale: "zh" | "en") {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function Modal({ title, children, onClose, busy = false }: { title: string; children: React.ReactNode; onClose: () => void; busy?: boolean }) {
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const first = root.current?.querySelector<HTMLElement>("input:not(:disabled), button:not(:disabled), select:not(:disabled)");
    (first || root.current)?.focus();
    return () => { document.body.style.overflow = previousOverflow; };
  }, []);
  useEffect(() => {
    if (busy && !root.current?.querySelector("input:not(:disabled), button:not(:disabled), select:not(:disabled)")) root.current?.focus();
  }, [busy]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab" || !root.current) return;
      const items = [...root.current.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled)')];
      if (!items.length) { event.preventDefault(); root.current.focus(); return; }
      const firstItem = items[0], last = items.at(-1)!;
      if (!root.current.contains(document.activeElement) || document.activeElement === root.current) { event.preventDefault(); (event.shiftKey ? last : firstItem).focus(); }
      else if (event.shiftKey && document.activeElement === firstItem) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); firstItem.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return <div className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section ref={root} tabIndex={-1} className="api-modal" role="dialog" aria-modal="true" aria-busy={busy} aria-labelledby="api-modal-title"><h2 id="api-modal-title">{title}</h2>{children}</section></div>;
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
  const [modalError, setModalError] = useState("");
  const modalTrigger = useRef<HTMLElement | null>(null);
  const createButton = useRef<HTMLButtonElement>(null);
  const keyListHeading = useRef<HTMLHeadingElement>(null);
  const secretInput = useRef<HTMLInputElement>(null);
  const [restoreAfterRefresh, setRestoreAfterRefresh] = useState(false);
  const [creatingRefresh, setCreatingRefresh] = useState(false);
  const [restoreAfterCreateRefresh, setRestoreAfterCreateRefresh] = useState(false);

  const restoreModalTrigger = () => requestAnimationFrame(() => {
    const trigger = modalTrigger.current;
    if (trigger?.isConnected && !(trigger instanceof HTMLButtonElement && trigger.disabled)) { trigger.focus(); return; }
    if (createButton.current?.isConnected && !createButton.current.disabled) { createButton.current.focus(); return; }
    keyListHeading.current?.focus();
  });
  useEffect(() => {
    if (!restoreAfterRefresh) return;
    restoreModalTrigger();
    setRestoreAfterRefresh(false);
  }, [keys, restoreAfterRefresh, usage]);
  useEffect(() => {
    if (!restoreAfterCreateRefresh || creatingRefresh) return;
    restoreModalTrigger();
    setRestoreAfterCreateRefresh(false);
  }, [creatingRefresh, restoreAfterCreateRefresh]);
  const closeCreating = () => { if (busy) return; setCreating(false); setModalError(""); restoreModalTrigger(); };
  const closeSecret = () => {
    setSecret(null);
    if (creatingRefresh) setRestoreAfterCreateRefresh(true);
    else restoreModalTrigger();
  };
  const closeRevoke = (force = false) => { if (busy && !force) return; setRevoke(null); setModalError(""); restoreModalTrigger(); };
  const failureMessage = (cause: unknown) => {
    const detail = cause instanceof ApiError ? cause.message : "Request failed";
    return locale === "zh" ? `操作失败：${detail}` : `Request failed: ${detail}`;
  };

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
    setBusy(true); setModalError("");
    try {
      const created = await apiCenterApi.createKey({ name: name.trim(), expires_in_days: days });
      setCreating(false); setName(""); setSecret(created); setCopied(false); setCopyFailed(false); setCreatingRefresh(true);
      const [nextKeys, nextUsage] = await Promise.all([apiCenterApi.keys(), apiCenterApi.usage()]);
      setKeys(nextKeys); setUsage(nextUsage);
    } catch (cause) { setModalError(failureMessage(cause)); }
    finally { setBusy(false); setCreatingRefresh(false); }
  }
  async function confirmRevoke() {
    if (!revoke) return;
    setBusy(true); setModalError("");
    try {
      await apiCenterApi.revokeKey(revoke.id);
      setRevoke(null); setModalError(""); setNotice(locale === "zh" ? "密钥已撤销" : "Key revoked");
      const [nextKeys, nextUsage] = await Promise.all([apiCenterApi.keys(), apiCenterApi.usage()]);
      setKeys(nextKeys); setUsage(nextUsage); setRestoreAfterRefresh(true);
    } catch (cause) { setModalError(failureMessage(cause)); }
    finally { setBusy(false); }
  }
  const quotaCards = usage ? [
    [locale === "zh" ? "今日提交" : "Submitted today", usage.submitted_today],
    [locale === "zh" ? "未完成任务" : "Unfinished tasks", usage.unfinished_tasks],
    [locale === "zh" ? "草稿" : "Drafts", usage.drafts],
    [locale === "zh" ? "活动密钥" : "Active keys", usage.active_api_keys],
  ] as const : [];

  return <main className="api-content api-keys-page">
    <header className="api-page-header"><h1>{c.keysTitle}</h1><p>{c.keysLead}</p></header>
    {error && <div className="inline-error" role="alert">{error}</div>}
    {notice && <p className="api-notice" role="status">{notice}</p>}
    {loading ? <p role="status">{locale === "zh" ? "正在加载 API 数据…" : "Loading API data…"}</p> : <>
      <section aria-labelledby="usage-title"><div className="api-section-heading"><div><h2 id="usage-title">{locale === "zh" ? "API 概览" : "API overview"}</h2><p>{locale === "zh" ? "当前 Beta 配额按账户隔离。" : "Current beta quotas are isolated by account."}</p></div></div><div className="api-quota-grid">{quotaCards.map(([label, quota]) => <article key={label}><span>{label}</span><strong>{quota.used} / {quota.limit}</strong><i aria-hidden="true"><b style={{ width: `${quota.limit > 0 ? Math.min(100, Math.max(0, quota.used / quota.limit * 100)) : 0}%` }}/></i></article>)}</div></section>
      <section className="api-key-panel" aria-labelledby="key-list-title"><div className="api-section-heading"><div><h2 ref={keyListHeading} id="key-list-title" tabIndex={-1}>{locale === "zh" ? `API 密钥 (${usage?.active_api_keys.used ?? 0}/${usage?.active_api_keys.limit ?? 5})` : `API keys (${usage?.active_api_keys.used ?? 0}/${usage?.active_api_keys.limit ?? 5})`}</h2><p>{locale === "zh" ? `默认 90 天有效，最多 ${usage?.active_api_keys.limit ?? 5} 个活动密钥。列表不保存完整密钥。` : `Keys last 90 days by default, with at most ${usage?.active_api_keys.limit ?? 5} active keys. Full secrets are not retained in this list.`}</p></div><button ref={createButton} className="button button-primary" type="button" disabled={(usage?.active_api_keys.used ?? 0) >= (usage?.active_api_keys.limit ?? 5)} onClick={event => { modalTrigger.current = event.currentTarget; setModalError(""); setCreating(true); }}><Icon name="plus"/>{locale === "zh" ? "创建 API 密钥" : "Create API key"}</button></div>
        <div className="api-key-table-wrap"><table className="api-key-table"><thead><tr><th scope="col">{locale === "zh" ? "名称" : "Name"}</th><th scope="col">{locale === "zh" ? "密钥" : "Key"}</th><th scope="col">{locale === "zh" ? "状态" : "Status"}</th><th scope="col">{locale === "zh" ? "创建 / 到期" : "Created / expires"}</th><th scope="col">{locale === "zh" ? "操作" : "Action"}</th></tr></thead><tbody>{keys.map(key => <tr key={key.id}><td data-label={locale === "zh" ? "名称" : "Name"}><strong>{key.name}</strong></td><td data-label={locale === "zh" ? "密钥" : "Key"}><code>{key.prefix}••••{key.last_four}</code></td><td data-label={locale === "zh" ? "状态" : "Status"}><span className={`key-status ${key.status}`}>{locale === "zh" ? ({active:"活动",expired:"已过期",revoked:"已撤销"} as const)[key.status] : key.status}</span></td><td data-label={locale === "zh" ? "创建 / 到期" : "Created / expires"}><span>{formatDate(key.created_at, locale)}</span><small>{formatDate(key.expires_at, locale)}</small></td><td data-label={locale === "zh" ? "操作" : "Action"}>{key.status !== "revoked" ? <button className="table-action action-delete" type="button" aria-label={`${locale === "zh" ? "撤销" : "Revoke"} ${key.name}`} title={`${locale === "zh" ? "撤销" : "Revoke"} ${key.name}`} onClick={event => { modalTrigger.current = event.currentTarget; setModalError(""); setRevoke(key); }}><Icon name="trash"/></button> : "—"}</td></tr>)}</tbody></table></div>
        {keys.length === 0 && <p className="api-key-empty">{locale === "zh" ? "暂无 API 密钥。创建密钥以开始服务端集成。" : "No API keys yet. Create a key to start your server integration."}</p>}
      </section>
      {usage && <section className="api-retention" aria-labelledby="retention-title"><h2 id="retention-title">{locale === "zh" ? "数据保留" : "Data retention"}</h2><p>{locale === "zh" ? "草稿 / 注册数据 / 原始输入 / 结果" : "Drafts / enrollment / raw inputs / results"}</p><strong>{formatRetentionDuration(locale, usage.retention.drafts)} · {formatRetentionDuration(locale, usage.retention.enrollment_data)} · {formatRetentionDuration(locale, usage.retention.raw_inputs)} · {formatRetentionDuration(locale, usage.retention.results)}</strong></section>}
    </>}
    {creating && <Modal title={locale === "zh" ? "创建 API 密钥" : "Create API key"} busy={busy} onClose={closeCreating}>{busy && <p role="status">{locale === "zh" ? "正在创建密钥…" : "Creating key…"}</p>}{modalError && <div className="inline-error" role="alert" aria-live="assertive">{modalError}</div>}<form onSubmit={create}><label>{locale === "zh" ? "密钥名称" : "Key name"}<input required disabled={busy} value={name} onChange={event => setName(event.target.value)} /></label><label>{locale === "zh" ? "有效期" : "Expires in"}<select disabled={busy} value={days} onChange={event => setDays(Number(event.target.value))}><option value={30}>30 {locale === "zh" ? "天" : "days"}</option><option value={90}>90 {locale === "zh" ? "天" : "days"}</option><option value={365}>365 {locale === "zh" ? "天" : "days"}</option></select></label><div><button className="button button-outline" type="button" disabled={busy} onClick={closeCreating}>{locale === "zh" ? "取消" : "Cancel"}</button><button className="button button-primary" type="submit" disabled={busy}>{locale === "zh" ? "创建密钥" : "Create key"}</button></div></form></Modal>}
    {secret && <Modal title={locale === "zh" ? "保存新密钥" : "Save your new key"} onClose={closeSecret}><div className="secret-warning" role="alert">{locale === "zh" ? "完整密钥只显示一次。现在复制并保存在安全位置；关闭后无法再次查看。" : "The full key is shown only once. Copy and store it securely now; it cannot be shown again."}</div><input ref={secretInput} aria-label={locale === "zh" ? "新 API 密钥" : "New API key"} className="secret-value" readOnly value={secret.secret} onFocus={event => event.currentTarget.select()}/><div className="secret-actions"><button className="button button-outline button-icon" type="button" aria-label={locale === "zh" ? "复制完整密钥" : "Copy full key"} title={locale === "zh" ? "复制完整密钥" : "Copy full key"} onClick={async () => { try { await navigator.clipboard.writeText(secret.secret); setCopied(true); setCopyFailed(false); } catch { setCopied(false); setCopyFailed(true); requestAnimationFrame(() => { secretInput.current?.focus(); secretInput.current?.select(); }); } }}><Icon name="copy"/></button>{copied && <span role="status">{locale === "zh" ? "已复制" : "Copied"}</span>}{copyFailed && <span role="alert">{locale === "zh" ? "复制失败；已选中密钥，可用键盘复制。" : "Copy failed; the key is selected for keyboard copy."}</span>}<button className="button button-primary" type="button" onClick={closeSecret}>{locale === "zh" ? "我已保存" : "I saved it"}</button></div></Modal>}
    {revoke && <Modal title={locale === "zh" ? "撤销 API 密钥" : "Revoke API key"} busy={busy} onClose={closeRevoke}>{busy && <p role="status">{locale === "zh" ? "正在撤销密钥…" : "Revoking key…"}</p>}{modalError && <div className="inline-error" role="alert" aria-live="assertive">{modalError}</div>}<p>{locale === "zh" ? `撤销“${revoke.name}”后，使用它的请求将立即失效。` : `Requests using “${revoke.name}” will stop working immediately.`}</p><div className="modal-actions"><button className="button button-outline" type="button" disabled={busy} onClick={() => closeRevoke()}>{locale === "zh" ? "取消" : "Cancel"}</button><button className="button button-primary" type="button" disabled={busy} onClick={() => void confirmRevoke()}>{locale === "zh" ? "确认撤销" : "Revoke key"}</button></div></Modal>}
  </main>;
}
