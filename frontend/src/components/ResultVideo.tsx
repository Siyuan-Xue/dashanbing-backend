import { useCallback, useEffect, useRef, useState } from "react";
import type { SyntheticEvent } from "react";
import { Icon } from "./Icon";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";

export function ResultVideo({ src, title, seek }: { src: string; title: string; seek?: { id: number; seconds: number } | null }) {
  const wt = useWorkspaceCopy();
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const playRequested = useRef(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const appliedSeek = useRef<string | null>(null);
  const applySeek = useCallback((video: HTMLVideoElement) => {
    if (!seek || !Number.isFinite(seek.seconds) || seek.seconds < 0) return;
    const key = `${seek.id}:${seek.seconds}`;
    if (appliedSeek.current === key) return;
    try {
      video.currentTime = Number.isFinite(video.duration) ? Math.min(seek.seconds, video.duration) : seek.seconds;
      appliedSeek.current = key;
    } catch { /* Metadata can arrive before the media is seekable; retry on loadeddata/canplay */ }
  }, [seek]);
  useEffect(() => {
    if (videoRef.current && videoRef.current.readyState >= 1) applySeek(videoRef.current);
  }, [applySeek]);
  const prepareVideo = useCallback((video: HTMLVideoElement | null) => {
    videoRef.current = video;
    if (!video) return;
    appliedSeek.current = null;
    playRequested.current = false;
    // Set both the muted attribute and live property on every new media element
    video.defaultMuted = true;
    video.muted = true;
  }, []);
  const playWhenReady = (event: SyntheticEvent<HTMLVideoElement>) => {
    setState("ready");
    applySeek(event.currentTarget);
    if (playRequested.current) return;
    playRequested.current = true;
    // Browser policy or a rapid camera switch can reject play; native controls remain usable
    void event.currentTarget.play().catch(() => {});
  };

  return <>
    {state !== "error" && <video key={attempt} ref={prepareVideo} controls autoPlay muted playsInline preload="auto" src={src} title={title} onLoadedMetadata={event => { setState("ready"); applySeek(event.currentTarget); }} onLoadedData={event => { setState("ready"); applySeek(event.currentTarget); }} onCanPlay={playWhenReady} onPlay={() => { playRequested.current = true; }} onError={() => setState("error")}/>}
    {state === "loading" && <span className="media-loading" role="status">{wt("mediaLoading")}</span>}
    {state === "error" && <div className="media-placeholder" role="alert"><div><b>{wt("mediaError")}</b><button type="button" className="media-retry" aria-label={wt("reloadMedia")} title={wt("reloadMedia")} onClick={() => { setAttempt((value) => value + 1); setState("loading"); }}><Icon name="refresh"/></button></div></div>}
  </>;
}
