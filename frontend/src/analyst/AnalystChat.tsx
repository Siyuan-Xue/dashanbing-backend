import { useEffect, useRef, useState } from "react";
import { Icon } from "../components/Icon";
import { useLocale } from "../providers/LocaleProvider";
import { analystApi } from "./api";
import { useAnalystCopy } from "./copy";
import { EvidenceLinks } from "./EvidenceLinks";
import type { AnalystMessage, AnalystSource, AnalystStyle, Evidence } from "./types";
export type ChatProps = { refreshKey?: number; source: AnalystSource; style: AnalystStyle; subjectId: string; comparisonId: string | null; accountId?: number; disabled: boolean; evidence: Evidence[]; onEvidence: (value: Evidence) => void };
const pending = (message: AnalystMessage) => message.status === "running" || message.status === "queued";
const stored = (key: string | null) => { try { return key ? sessionStorage.getItem(key) : null; } catch { return null; } };
const persist = (key: string | null, id: string) => { try { if (key) sessionStorage.setItem(key, id); } catch { /* Session storage may be disabled */ } };

export function AnalystChat(props: ChatProps) {
  const { locale } = useLocale();
  const key = `analyst:${props.accountId}:${props.source.kind}:${props.source.id}:${props.subjectId}:${props.comparisonId || ""}:${locale}:${props.style}`;
  return <ChatSession key={key} {...props} storageKey={props.accountId === undefined ? null : key}/>;
}
function ChatSession({ refreshKey = 0, source, style, subjectId, comparisonId, disabled, evidence, onEvidence, storageKey }: ChatProps & { storageKey: string | null }) {
  const t = useAnalystCopy(); const { locale } = useLocale();
  const [conversationId, setConversationId] = useState<string | null>(() => stored(storageKey));
  const conversationRef = useRef(conversationId);
  const [messages, setMessages] = useState<AnalystMessage[]>([]);
  const [text, setText] = useState(""); const [sending, setSending] = useState(false); const [recovering, setRecovering] = useState(Boolean(conversationId)); const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);
  const streamRef = useRef<EventSource | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const retryRequest = useRef<{ content: string; id: string } | null>(null);
  const posting = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const previousContext = useRef(refreshKey);
  useEffect(() => {
    const controller = new AbortController(); controllerRef.current = controller;
    if (previousContext.current !== refreshKey) {
      previousContext.current = refreshKey;
      setMessages([]); setRecovering(Boolean(conversationId));
    }
    posting.current = false; setSending(false);
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stream: EventSource | null = null;
    const close = () => { stream?.close(); stream = null; streamRef.current = null; };
    const refresh = async (allowStream: boolean) => {
      if (!conversationId || disabled) { setRecovering(false); return; }
      try {
        const current = await analystApi.conversation(conversationId, controller.signal);
        if (controller.signal.aborted) return;
        setMessages(current.messages); setError(false); setRecovering(false);
        if (!current.messages.some(pending)) { close(); return; }
        if (allowStream && typeof EventSource !== "undefined") {
          close();
          stream = new EventSource(analystApi.eventsUrl(conversationId), { withCredentials: true }); streamRef.current = stream;
          stream.addEventListener("message", event => {
            if (controller.signal.aborted) return;
            try {
              const message = JSON.parse(event.data) as AnalystMessage;
              if (!message.id || !["user", "assistant"].includes(message.role) || typeof message.content !== "string" || !Array.isArray(message.citations)) throw new Error("Invalid message");
              setMessages(values => values.some(value => value.id === message.id) ? values.map(value => value.id === message.id ? message : value) : [...values, message]);
            } catch { close(); void refresh(false); }
          });
          stream.addEventListener("done", () => { close(); void refresh(false); });
          stream.addEventListener("error", () => { close(); void refresh(false); });
        } else timer = setTimeout(() => void refresh(false), 2000);
      } catch { if (!controller.signal.aborted) { close(); setError(true); setRecovering(false); } }
    };
    void refresh(true);
    return () => { controller.abort(); clearTimeout(timer); close(); };
  }, [conversationId, disabled, revision, refreshKey]);
  useEffect(() => {
    if (nearBottom.current && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);
  const send = async () => {
    const content = text.trim();
    if (!content || disabled || posting.current) return;
    posting.current = true; setSending(true); setError(false);
    // An accepted POST can lose its response; retries of the same text reuse its idempotency key
    if (retryRequest.current?.content !== content) retryRequest.current = { content, id: crypto.randomUUID() };
    const controller = new AbortController();
    const parent = controllerRef.current;
    const abort = () => controller.abort(); parent?.signal.addEventListener("abort", abort, { once: true });
    try {
      let id = conversationRef.current;
      if (!id) {
        const conversation = await analystApi.createConversation(source, { ...(subjectId ? { subject_id: subjectId } : {}), ...(comparisonId ? { comparison_id: comparisonId } : {}), locale, style }, controller.signal);
        if (controller.signal.aborted) return;
        id = conversation.id;
        persist(storageKey, id);
        conversationRef.current = id;
      }
      await analystApi.send(id, content, retryRequest.current!.id, controller.signal);
      if (controller.signal.aborted) return;
      setText(""); retryRequest.current = null; setRecovering(true);
      setConversationId(id); setRevision(value => value + 1);
    } catch { if (!controller.signal.aborted) setError(true); }
    finally { parent?.signal.removeEventListener("abort", abort); if (!controller.signal.aborted) { setSending(false); posting.current = false; } }
  };
  const waiting = messages.some(pending);
  const blocked = disabled || sending || recovering || waiting;
  return <section className="analyst-chat" aria-label={t("chat")}>
    <header className="analyst-chat-header"><h3><Icon name="chat" size={16}/>{t("chat")}</h3><div className="analyst-quick-questions">{(["quickReview", "quickPractice", "quickCompare", "quickRoast"] as const).map(key => <button key={key} type="button" disabled={blocked} title={`${t("fillQuestion")} · ${t(key)}`} onClick={() => { if (!blocked) { setText(t(key)); textareaRef.current?.focus(); } }}>{t(key)}</button>)}</div></header>
    {messages.length > 0 && <div ref={logRef} className="analyst-messages" onScroll={event => { const log = event.currentTarget; nearBottom.current = log.scrollHeight - log.scrollTop - log.clientHeight <= 40; }} role="log" aria-live="polite" aria-label={t("chat")}>
      {messages.map(message => <article className={`analyst-message ${message.role}`} key={message.id}><span>{t(message.role === "user" ? "user" : "assistant")}</span><p>{message.content || (pending(message) ? t("responding") : t("failed"))}</p>{message.role === "assistant" && <EvidenceLinks ids={message.citations} evidence={evidence} onEvidence={onEvidence}/>} {message.status === "failed" && message.content && <small>{t("failed")}</small>}</article>)}
    </div>}
    {error && <p className="analyst-error" role="alert">{t("chatError")} {conversationId && <button className="table-action" type="button" title={t("restore")} aria-label={t("restore")} onClick={() => { setRecovering(true); setRevision(value => value + 1); }}><Icon name="refresh" size={16}/></button>}</p>}

    <form className="analyst-composer" onSubmit={event => { event.preventDefault(); void send(); }}>
      <textarea ref={textareaRef} aria-label={t("ask")} placeholder={t("prompt")} value={text} maxLength={4000} rows={2} disabled={blocked} onChange={event => setText(event.target.value)}/>
      <button className="button button-primary button-icon" type="submit" disabled={blocked || !text.trim()} title={t("send")} aria-label={t("send")}><Icon name="arrow" size={18}/></button>
    </form>
  </section>;
}
