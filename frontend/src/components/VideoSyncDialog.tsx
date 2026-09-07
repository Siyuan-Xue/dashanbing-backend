import { Check, Link2, LoaderCircle, Pause, Play, RefreshCw, SkipBack, SkipForward, X } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useLocale } from "../providers/LocaleProvider";
import { WorkspaceApiError } from "../workspace/api";
import { adjacentFrameTime, alignmentFor, nearestFrameTime, SYNC_CAMERAS, taskSyncApi } from "../lib/task-sync";
import type { CameraPreview, CameraValues, SyncCamera, SyncFrame, SyncPreview, TaskSync } from "../lib/task-sync";
import "../styles/video-sync.css";

const words = {
  zh: { title: "同步四个机位", hint: "找到同一瞬间，例如球触地，先选机位 3，再对齐其他画面", camera: "机位", anchor: "基准", close: "关闭同步", cancel: "取消", confirm: "确认同步", preparing: "正在准备同步预览…", retry: "重新加载", failed: "同步预览不可用，请重试", frameFailed: "无法读取当前帧，请重试", playFailed: "视频无法播放，请重新加载预览", previous: "上一帧", next: "下一帧", choose: "选定当前帧", chosen: "已选定", seek: "定位画面", play: "播放", pause: "暂停", link: "联动预览", align: "返回逐帧对齐", common: "共同时间", linkedPlay: "播放联动", linkedPause: "暂停联动", unconfirmed: "未确认同步", confirmed: "已确认同步", stale: "视频已更换，请重新同步", overlap: "所选画面没有共同播放区间，请重新选帧", frame: "当前帧", saving: "正在确认…" },
  en: { title: "Sync four cameras", hint: "Choose the same instant, such as the ball touching the floor. Start with Camera 3, then align the others.", camera: "Camera", anchor: "Reference", close: "Close sync", cancel: "Cancel", confirm: "Confirm sync", preparing: "Preparing sync previews…", retry: "Reload", failed: "Sync preview unavailable. Please retry.", frameFailed: "Could not read this frame. Please retry.", playFailed: "Video playback failed. Please reload the preview.", previous: "Previous frame", next: "Next frame", choose: "Select current frame", chosen: "Selected", seek: "Seek frame", play: "Play", pause: "Pause", link: "Linked preview", align: "Back to frame alignment", common: "Common time", linkedPlay: "Play linked", linkedPause: "Pause linked", unconfirmed: "Sync unconfirmed", confirmed: "Sync confirmed", stale: "Videos changed. Sync again", overlap: "The selected frames have no common playback interval. Select again.", frame: "Current frame", saving: "Confirming…" },
};
type Copy = typeof words["zh"] | typeof words["en"];
type VideoRefs = { current: Partial<CameraValues<HTMLVideoElement>> };
const seconds = (ms: number) => `${(ms / 1000).toFixed(3)} s`;
const cameraLabel = (camera: SyncCamera, copy: Copy) => `${copy.camera} ${Number(camera.slice(-2))}`;

function CameraPlayer({ taskId, camera, preview, initialTime, selectedTime, hidden, compact, linked, busy, videos, copy, onSelect, onReady, onEnded }: {
  taskId: string; camera: SyncCamera; preview: CameraPreview; initialTime: number; selectedTime?: number;
  hidden: boolean; compact: boolean; linked: boolean; busy: boolean; videos: VideoRefs; copy: Copy;
  onSelect: (camera: SyncCamera, time: number) => void; onReady: (camera: SyncCamera, ready: boolean) => void; onEnded: () => void;
}) {
  const [cursor, setCursor] = useState(initialTime);
  const [frame, setFrame] = useState<SyncFrame | null>(null);
  const [pending, setPending] = useState(true);
  const [playing, setPlaying] = useState(false);
  const playingRef = useRef(false);
  const mediaFailedRef = useRef(false);
  const [error, setError] = useState("");
  const requestRef = useRef<AbortController | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const liveRef = useRef(true);
  const label = cameraLabel(camera, copy) + (camera === "cam_03" ? ` · ${copy.anchor}` : "");
  const loadFrame = useCallback(async (time: number) => {
    requestRef.current?.abort();
    const controller = new AbortController(); requestRef.current = controller;
    const measuredTime = nearestFrameTime(preview.frame_timestamps_ms, time);
    setPending(true); setError(mediaFailedRef.current ? copy.playFailed : ""); onReady(camera, false);
    try {
      const result = await taskSyncApi.frame(taskId, camera, measuredTime, preview.source_version, controller.signal);
      if (controller.signal.aborted || !liveRef.current) return;
      if (result.camera !== camera || result.source_version !== preview.source_version || !Number.isFinite(result.actual_time_ms) || result.actual_time_ms !== preview.frame_timestamps_ms[result.frame_index] || !result.image_data_url.startsWith("data:image/jpeg;base64,")) throw new Error(copy.frameFailed);
      setFrame(result); setCursor(result.actual_time_ms);
      if (videoRef.current) videoRef.current.currentTime = result.actual_time_ms / 1000;
      onReady(camera, !mediaFailedRef.current);
    } catch (reason) {
      if (!controller.signal.aborted && liveRef.current) { setError(reason instanceof Error ? reason.message : copy.frameFailed); setFrame(null); }
    } finally { if (!controller.signal.aborted && liveRef.current) setPending(false); }
  }, [taskId, camera, preview, onReady, copy]);
  useEffect(() => {
    liveRef.current = true;
    void loadFrame(initialTime);
    return () => { liveRef.current = false; requestRef.current?.abort(); videoRef.current?.pause(); delete videos.current[camera]; };
  }, [loadFrame, initialTime, videos, camera]);
  const wasLinked = useRef(linked);
  useEffect(() => {
    if (wasLinked.current && !linked) void loadFrame((videoRef.current?.currentTime || 0) * 1000);
    wasLinked.current = linked;
  }, [linked, loadFrame]);
  const seek = (time: number) => {
    playingRef.current = false; setPlaying(false); videoRef.current?.pause();
    void loadFrame(time);
  };
  const togglePlay = async () => {
    const video = videoRef.current;
    if (!video) return;
    if (playingRef.current) { video.pause(); return; }
    try { await video.play(); }
    catch { if (liveRef.current) { mediaFailedRef.current = true; setError(copy.playFailed); onReady(camera, false); } }
  };
  return <section className={`video-sync-camera${camera === "cam_03" ? " is-anchor" : ""}`} role="region" aria-label={label} hidden={hidden}>
    <header><strong>{label}</strong><span className="video-sync-selection">{selectedTime !== undefined && <><Check size={14} aria-hidden="true"/><span>{seconds(selectedTime)}</span></>}</span></header>
    <div className="video-sync-media">
      <video ref={node => { videoRef.current = node; if (node) videos.current[camera] = node; }} src={preview.video_url} muted playsInline preload="metadata" aria-label={label}
        onLoadedMetadata={() => { if (videoRef.current && !linked) videoRef.current.currentTime = cursor / 1000; }}
        onPlay={() => { playingRef.current = true; setPlaying(true); }}
        onPause={() => { const wasPlaying = playingRef.current; playingRef.current = false; setPlaying(false); if (wasPlaying && !linked) void loadFrame((videoRef.current?.currentTime || 0) * 1000); }}
        onTimeUpdate={() => { if (playingRef.current || linked) setCursor((videoRef.current?.currentTime || 0) * 1000); }}
        onEnded={() => { if (linked) onEnded(); else { playingRef.current = false; setPlaying(false); void loadFrame(preview.frame_timestamps_ms.at(-1)!); } }}
        onError={() => { mediaFailedRef.current = true; setError(copy.playFailed); onReady(camera, false); if (linked) onEnded(); }}/>
      {!playing && !linked && frame && <img src={frame.image_data_url} alt={`${label} ${copy.frame}`} onError={() => { setError(copy.frameFailed); onReady(camera, false); }}/>}
      {pending && !linked && <span className="video-sync-frame-loading" role="status" aria-label={copy.preparing}><LoaderCircle size={18} aria-hidden="true"/></span>}
    </div>
    <div className="video-sync-seek"><input type="range" min="0" max={preview.frame_timestamps_ms.at(-1)} step="any" value={cursor} disabled={busy || linked} aria-label={copy.seek} onChange={event => seek(Number(event.target.value))}/><output>{seconds(cursor)}</output></div>
    <div className="video-sync-frame-controls">
      <button type="button" disabled={busy || linked || pending} onClick={() => void togglePlay()} aria-label={playing ? copy.pause : copy.play} title={playing ? copy.pause : copy.play}>{playing ? <Pause size={16}/> : <Play size={16}/>}<span>{playing ? copy.pause : copy.play}</span></button>
      <button type="button" aria-label={copy.previous} disabled={busy || linked || pending || cursor <= preview.frame_timestamps_ms[0]} onClick={() => seek(adjacentFrameTime(preview.frame_timestamps_ms, cursor, -1))}><SkipBack size={16}/><span>{compact && copy === words.en ? "Previous" : copy.previous}</span></button>
      <button type="button" aria-label={copy.next} disabled={busy || linked || pending || cursor >= preview.frame_timestamps_ms.at(-1)!} onClick={() => seek(adjacentFrameTime(preview.frame_timestamps_ms, cursor, 1))}><SkipForward size={16}/><span>{compact && copy === words.en ? "Next" : copy.next}</span></button>
      <button className="video-sync-select" type="button" aria-label={copy.choose} disabled={busy || linked || pending || playing || !frame || Boolean(error)} aria-pressed={selectedTime !== undefined && selectedTime === frame?.actual_time_ms} onClick={() => { if (frame) onSelect(camera, frame.actual_time_ms); }}><Check size={16}/><span>{compact && copy === words.en ? "Select frame" : copy.choose}</span></button>
    </div>
    {error && <div className="video-sync-camera-error" role="alert">{error}<button type="button" disabled={busy || linked} onClick={() => void loadFrame(cursor)}><RefreshCw size={14}/>{copy.retry}</button></div>}
  </section>;
}

export function VideoSyncDialog({ taskId, onClose, onConfirmed }: { taskId: string; onClose: () => void; onConfirmed: (sync: TaskSync) => void }) {
  const { locale } = useLocale(); const copy = words[locale];
  const titleId = useId(), hintId = useId();
  const dialogRef = useRef<HTMLElement>(null), closeRef = useRef<HTMLButtonElement>(null);
  const videos = useRef<Partial<CameraValues<HTMLVideoElement>>>({});
  const [preview, setPreview] = useState<SyncPreview | null>(null);
  const [sync, setSync] = useState<TaskSync | null>(null);
  const [initial, setInitial] = useState<Partial<CameraValues<number>>>({});
  const [selected, setSelected] = useState<Partial<CameraValues<number>>>({});
  const [ready, setReady] = useState<Partial<CameraValues<boolean>>>({});
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [playbackFailed, setPlaybackFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const savingRef = useRef(false), liveRef = useRef(true);
  const [revision, setRevision] = useState(0);
  const [mobile, setMobile] = useState(() => matchMedia("(max-width: 640px)").matches);
  const [activeCamera, setActiveCamera] = useState<SyncCamera>("cam_01");
  const [linked, setLinked] = useState(false), [linkedPlaying, setLinkedPlaying] = useState(false);
  const [commonTime, setCommonTime] = useState(0);
  const linkedPlayingRef = useRef(false);
  const stopLinked = useCallback(() => { linkedPlayingRef.current = false; setLinkedPlaying(false); for (const video of Object.values(videos.current)) video?.pause(); }, []);
  const onReady = useCallback((camera: SyncCamera, value: boolean) => setReady(previous => ({ ...previous, [camera]: value })), []);
  const onSelect = useCallback((camera: SyncCamera, time: number) => setSelected(previous => ({ ...previous, [camera]: time })), []);
  const allSelected = SYNC_CAMERAS.every(camera => selected[camera] !== undefined);
  const durations = Object.fromEntries(SYNC_CAMERAS.map(camera => [camera, preview?.cameras[camera]?.duration_ms])) as CameraValues<number>;
  const alignment = allSelected ? alignmentFor(selected as CameraValues<number>, durations) : null;
  const allReady = preview?.status === "ready" && SYNC_CAMERAS.every(camera => ready[camera]);
  const canConfirm = allReady && Boolean(alignment) && !stale && !playbackFailed && !busy;
  const lastCommonTime = alignment ? Math.max(alignment.start, alignment.end - .001) : 0;

  useEffect(() => {
    const query = matchMedia("(max-width: 640px)");
    const change = () => setMobile(query.matches); query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  // Match the existing ConfirmDialog's scroll lock, Escape handling and focus restoration.
  useEffect(() => {
    liveRef.current = true;
    const returnTarget = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const overflow = document.body.style.overflow; document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => { liveRef.current = false; for (const video of Object.values(videos.current)) video?.pause(); document.body.style.overflow = overflow; if (returnTarget?.isConnected) returnTarget.focus(); };
  }, []);
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !savingRef.current) { event.preventDefault(); onClose(); return; }
      if (event.key !== "Tab") return;
      const focusable = [...(dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), [tabindex]:not([tabindex="-1"])') || [])].filter(node => !node.closest("[hidden]"));
      const first = focusable[0], last = focusable.at(-1);
      if (!first || !last) { event.preventDefault(); dialogRef.current?.focus(); }
      else if (!dialogRef.current?.contains(document.activeElement) || (!event.shiftKey && document.activeElement === last)) { event.preventDefault(); (event.shiftKey ? last : first).focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    };
    window.addEventListener("keydown", keydown); return () => window.removeEventListener("keydown", keydown);
  }, [onClose]);
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    setPreview(null); setSync(null); setSelected({}); setInitial({}); setReady({}); setError(""); setStale(false); setPlaybackFailed(false); setLinked(false); stopLinked();
    const acceptPreview = (result: SyncPreview, saved: TaskSync) => {
      if (controller.signal.aborted) return;
      setPreview(result);
      if (result.status === "failed") { setError(typeof result.error === "string" ? result.error : result.error?.message || copy.failed); return; }
      if (result.status === "ready") {
        if (SYNC_CAMERAS.some(camera => {
          const media = result.cameras[camera];
          return !media || media.source_version !== result.source_versions[camera] || !media.frame_timestamps_ms.length || !media.video_url;
        })) { setError(copy.failed); setPreview(null); return; }
        if (saved.status === "confirmed" && saved.config?.selected_timestamps_ms && SYNC_CAMERAS.every(camera => saved.config!.input_versions[camera] === result.source_versions[camera])) {
          setSelected(saved.config.selected_timestamps_ms); setInitial(saved.config.selected_timestamps_ms);
        }
      } else timer = setTimeout(() => void poll(saved), 1500);
    };
    const fail = (reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : copy.failed); };
    const poll = async (saved: TaskSync) => {
      try { acceptPreview(await taskSyncApi.preview(taskId, controller.signal), saved); } catch (reason) { fail(reason); }
    };
    void Promise.all([taskSyncApi.get(taskId, controller.signal), taskSyncApi.prepare(taskId, controller.signal)]).then(([saved, result]) => {
      if (controller.signal.aborted) return; setSync(saved); acceptPreview(result, saved);
    }).catch(fail);
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [taskId, revision, copy, stopLinked]);

  const seekLinked = (time: number) => {
    if (!alignment) return;
    const common = Math.max(alignment.start, Math.min(lastCommonTime, time)); setCommonTime(common);
    for (const camera of SYNC_CAMERAS) { const video = videos.current[camera]; if (video) video.currentTime = (common + alignment.offsets[camera]) / 1000; }
  };
  // cam_03 supplies the common clock; correct drift and stop every camera at the overlap boundary.
  useEffect(() => {
    if (!linkedPlaying || !alignment) return;
    let handle: number;
    const tick = () => {
      if (!linkedPlayingRef.current) return;
      const common = (videos.current.cam_03?.currentTime || 0) * 1000;
      if (common >= lastCommonTime) { stopLinked(); seekLinked(lastCommonTime); return; }
      setCommonTime(common);
      for (const camera of SYNC_CAMERAS) {
        const video = videos.current[camera], target = (common + alignment.offsets[camera]) / 1000;
        if (video && Math.abs(video.currentTime - target) > .08) video.currentTime = target;
      }
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick); return () => cancelAnimationFrame(handle);
  }, [linkedPlaying, selected, preview, lastCommonTime, stopLinked]);
  const toggleLinkedPlayback = async () => {
    if (linkedPlayingRef.current) { stopLinked(); return; }
    if (!alignment) return;
    if (commonTime >= lastCommonTime) seekLinked(alignment.start);
    linkedPlayingRef.current = true; setLinkedPlaying(true);
    try {
      await Promise.all(SYNC_CAMERAS.map(camera => {
        const video = videos.current[camera];
        if (!video) throw new Error(copy.playFailed);
        return video.play().then(() => { if (!linkedPlayingRef.current || !liveRef.current) video.pause(); });
      }));
    } catch { if (liveRef.current) { stopLinked(); setPlaybackFailed(true); setError(copy.playFailed); } }
  };
  const confirm = async () => {
    if (!canConfirm || !preview || savingRef.current) return;
    stopLinked(); savingRef.current = true; setBusy(true); setError("");
    try {
      const saved = await taskSyncApi.confirm(taskId, preview.source_versions, selected as CameraValues<number>);
      if (!liveRef.current) return;
      if (saved.status !== "confirmed" || !saved.config) throw new Error(copy.failed);
      onConfirmed(saved);
    } catch (reason) {
      if (liveRef.current) { setError(reason instanceof Error ? reason.message : copy.failed); if (reason instanceof WorkspaceApiError && reason.status === 409) setStale(true); }
    } finally { savingRef.current = false; if (liveRef.current) setBusy(false); }
  };
  const matchesSaved = sync?.status === "confirmed" && SYNC_CAMERAS.every(camera => selected[camera] !== undefined && selected[camera] === sync.config?.selected_timestamps_ms?.[camera]);
  const status = stale || sync?.status === "stale" ? copy.stale : matchesSaved ? copy.confirmed : copy.unconfirmed;
  const otherCameras = SYNC_CAMERAS.filter(camera => camera !== "cam_03");
  return <div className="dialog-backdrop video-sync-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !savingRef.current) onClose(); }}>
    <section ref={dialogRef} className="video-sync-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={hintId} aria-busy={busy || undefined} tabIndex={-1}>
      <header className="video-sync-heading"><div><h2 id={titleId}>{copy.title}</h2><p id={hintId}>{copy.hint}</p></div><button type="button" ref={closeRef} disabled={busy} className="video-sync-close" aria-label={copy.close} onClick={onClose}><X size={20}/></button></header>
      <div className="video-sync-content">
        {error && <div className="video-sync-error" role="alert"><span>{error}</span><button type="button" disabled={busy} onClick={() => setRevision(value => value + 1)}><RefreshCw size={16}/>{copy.retry}</button></div>}
        {!error && preview?.status !== "ready" && <p className="video-sync-loading" role="status"><LoaderCircle size={20}/>{copy.preparing}</p>}
        {preview?.status === "ready" && <>
          {mobile && <div role="tablist" className="video-sync-tabs" aria-label={copy.title}>{otherCameras.map((camera, index) => <button type="button" key={camera} role="tab" disabled={busy} tabIndex={activeCamera === camera ? 0 : -1} aria-label={`${cameraLabel(camera, copy)}${selected[camera] !== undefined ? ` ${copy.chosen}` : ""}`} aria-selected={activeCamera === camera} onClick={() => setActiveCamera(camera)} onKeyDown={event => {
            const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
            if (!step) return; event.preventDefault(); const next = otherCameras[(index + step + otherCameras.length) % otherCameras.length]; setActiveCamera(next);
            const tabs = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("button"); tabs?.[(index + step + otherCameras.length) % otherCameras.length].focus();
          }}>{cameraLabel(camera, copy)}{selected[camera] !== undefined && <><Check size={14} aria-hidden="true"/><span className="sr-only"> {copy.chosen}</span></>}</button>)}</div>}
          <div className="video-sync-grid">{(mobile ? ["cam_03" as const, ...otherCameras] : SYNC_CAMERAS).map(camera => <CameraPlayer key={`${camera}-${revision}`} taskId={taskId} camera={camera} preview={preview.cameras[camera]!} initialTime={initial[camera] ?? 0} selectedTime={selected[camera]} hidden={mobile && camera !== "cam_03" && camera !== activeCamera} compact={mobile} linked={linked} busy={busy} videos={videos} copy={copy} onSelect={onSelect} onReady={onReady} onEnded={stopLinked}/>)}</div>
          <div className="video-sync-linked"><button type="button" className="button button-outline" disabled={!allReady || !alignment || busy || stale} aria-pressed={linked} onClick={() => { stopLinked(); setLinked(value => !value); if (!linked) seekLinked(selected.cam_03!); }}><Link2 size={16}/>{linked ? copy.align : copy.link}</button>
            {linked && alignment && <><button type="button" disabled={busy || stale || playbackFailed} onClick={() => void toggleLinkedPlayback()}>{linkedPlaying ? <Pause size={16}/> : <Play size={16}/>}<span>{linkedPlaying ? copy.linkedPause : copy.linkedPlay}</span></button><input type="range" min={alignment.start} max={lastCommonTime} step="any" value={commonTime} aria-label={copy.common} disabled={busy || stale} onChange={event => { stopLinked(); seekLinked(Number(event.target.value)); }}/><output>{seconds(commonTime)}</output></>}
          </div>
          {allSelected && !alignment && <p role="alert" className="video-sync-error">{copy.overlap}</p>}
        </>}
      </div>
      <footer className="video-sync-footer"><span role="status">{status} · {Object.keys(selected).length}/4</span><div><button type="button" className="button button-outline" disabled={busy} onClick={onClose}>{copy.cancel}</button><button type="button" className="button button-primary" disabled={!canConfirm} onClick={() => void confirm()}>{busy ? copy.saving : copy.confirm}</button></div></footer>
    </section>
  </div>;
}
