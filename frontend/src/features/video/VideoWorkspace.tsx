import { useEffect, useState } from "react";
import type { OperatorDataSource } from "../../services/contracts";
import type { OperatorSession } from "../../types";
import { VideoDropzone } from "./VideoDropzone";
import { VideoViewport, type VideoSource } from "./VideoViewport";
import { TacticalOverlay } from "./TacticalOverlay";
import { Icon } from "../../components/ui/Icon";
import { isAcceptedVideo, type VideoMetadataState } from "./video-utils";
import styles from "./VideoWorkspace.module.css";

export function VideoWorkspace({ session, dataSource, onPlaybackTimeChange, onVideoEndedChange }: { session: OperatorSession; dataSource: OperatorDataSource; onPlaybackTimeChange?: (time: { currentSeconds: number; durationSeconds: number } | undefined) => void; onVideoEndedChange?: (ended: boolean) => void }) {
  const [source, setSource] = useState<VideoSource>({ type: "placeholder" });
  const [metadata, setMetadata] = useState<VideoMetadataState>();
  const [error, setError] = useState("");

  useEffect(() => () => { if (source.type === "local-preview") URL.revokeObjectURL(source.url); }, [source]);

  function selectFile(file: File) {
    if (!isAcceptedVideo(file)) {
      setError("Geçersiz dosya türü. Lütfen MP4, MOV, AVI veya MKV formatında bir video seçin.");
      return;
    }
    setError("");
    onPlaybackTimeChange?.(undefined);
    onVideoEndedChange?.(false);
    const url = URL.createObjectURL(file);
    const nextMetadata: VideoMetadataState = {
      name: file.name,
      sizeBytes: file.size,
      format: file.name.split(".").pop()?.toUpperCase() ?? "Video",
    };
    setSource({ type: "local-preview", url, name: file.name });
    setMetadata(nextMetadata);
    void dataSource.selectVideo({ name: file.name });
  }

  function readMetadata(event: React.SyntheticEvent<HTMLVideoElement>) {
    const video = event.currentTarget;
    setMetadata((current) => current ? { ...current, durationSeconds: video.duration, width: video.videoWidth, height: video.videoHeight } : current);
    if (metadata) void dataSource.selectVideo({ name: metadata.name, durationSeconds: video.duration });
  }

  // Oturum durdurulduktan/bitikten sonra streamUrl backend'de eski değerini korur
  // (bkz. existing-backend-adapter.ts pollStatus) — bu yüzden MJPEG'i sadece
  // gerçekten aktif bir oturumda gösteriyoruz, aksi halde dondurulmuş eski kare
  // yerine video seçim alanına (server listesi dahil) geri dönülür.
  const sessionActive = ["preparing", "running", "paused"].includes(session.status);
  const viewportSource = session.streamUrl && dataSource.capabilities.mjpegStream && sessionActive
    ? { type: "mjpeg" as const, url: session.streamUrl, name: session.sourceName ?? "Backend" }
    : session.sourceName && source.type === "local-preview" ? source : { type: "placeholder" } as const;

  return (
    <section className={styles.workspace} aria-label="Video analizi">
      <input
        id="video-file-input"
        className={styles.fileInput}
        type="file"
        aria-label="Analiz edilecek video dosyası"
        accept=".mp4,.mov,.avi,.mkv,video/mp4,video/quicktime,video/x-msvideo,video/x-matroska"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) selectFile(file);
          event.target.value = "";
        }}
      />
      <VideoViewport source={viewportSource} playbackStatus={session.status} onPlaybackTimeChange={onPlaybackTimeChange} onVideoEndedChange={onVideoEndedChange} overlay={viewportSource.type === "mjpeg" ? <TacticalOverlay session={session} aspectRatio={session.streamAspectRatio ?? (metadata?.width && metadata.height ? metadata.width / metadata.height : 16 / 9)} onSelectTarget={(id) => void dataSource.selectTarget(id)} /> : undefined}>
        <VideoDropzone onFile={dataSource.capabilities.videoUpload ? selectFile : undefined} />
      </VideoViewport>
      {source.type === "local-preview" && <video className={styles.metadataReader} src={source.url} onLoadedMetadata={readMetadata} aria-hidden="true" />}
      {error && <p className={styles.error} role="alert"><Icon name="warning" size={15} />{error}</p>}
    </section>
  );
}
