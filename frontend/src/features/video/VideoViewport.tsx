import { useEffect, useRef, useState } from "react";
import type { SessionStatus } from "../../types";
import styles from "./VideoViewport.module.css";

export type VideoSource =
  | { type: "placeholder" }
  | { type: "local-preview"; url: string; name: string }
  | { type: "mjpeg"; url: string; name: string };

export function VideoViewport({ source, playbackStatus, children, overlay, onPlaybackTimeChange, onVideoEndedChange }: { source: VideoSource; playbackStatus?: SessionStatus; children?: React.ReactNode; overlay?: React.ReactNode; onPlaybackTimeChange?: (time: { currentSeconds: number; durationSeconds: number }) => void; onVideoEndedChange?: (ended: boolean) => void }) {
  const [streamError, setStreamError] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => setStreamError(false), [source]);
  useEffect(() => {
    const video = videoRef.current;
    if (!video || source.type !== "local-preview" || !playbackStatus) return;
    if (playbackStatus === "file-selected") video.currentTime = 0;
    if (["file-selected", "paused", "stopped", "error"].includes(playbackStatus)) video.pause();
    else if (["preparing", "running", "completed"].includes(playbackStatus)) void video.play()?.catch(() => undefined);
  }, [playbackStatus, source]);
  return (
    <div id="video-viewport" className={styles.viewport} data-source-type={source.type}>
      {source.type === "local-preview" && <video ref={videoRef} src={source.url} aria-label={`${source.name} yerel video önizlemesi`} muted playsInline disablePictureInPicture disableRemotePlayback preload="metadata" onLoadedMetadata={(event) => onPlaybackTimeChange?.({ currentSeconds: event.currentTarget.currentTime, durationSeconds: event.currentTarget.duration })} onPlaying={() => onVideoEndedChange?.(false)} onTimeUpdate={(event) => onPlaybackTimeChange?.({ currentSeconds: event.currentTarget.currentTime, durationSeconds: event.currentTarget.duration })} onEnded={(event) => { onPlaybackTimeChange?.({ currentSeconds: event.currentTarget.duration, durationSeconds: event.currentTarget.duration }); onVideoEndedChange?.(true); }} />}
      {source.type === "mjpeg" && !streamError && <img src={source.url} alt={`${source.name} canlı analiz görüntüsü`} onError={() => setStreamError(true)} />}
      {source.type === "mjpeg" && streamError && <div className={styles.streamError} role="alert"><strong>Canlı görüntü alınamadı</strong><span>Backend video akışı şu anda kullanılamıyor.</span><button type="button" onClick={() => setStreamError(false)}>Yeniden Dene</button></div>}
      {source.type === "placeholder" && children}
      {source.type !== "placeholder" && !streamError && overlay}
    </div>
  );
}
