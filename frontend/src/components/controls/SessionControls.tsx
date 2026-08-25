import type { OperatorSession } from "../../types";
import type { OperatorCapabilities } from "../../services/contracts";
import { Icon } from "../ui/Icon";
import styles from "./SessionControls.module.css";

interface Props {
  session: OperatorSession;
  capabilities: OperatorCapabilities;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onRestart: () => void;
  onChangeVideo: () => void;
  videoEnded?: boolean;
}

export function SessionControls({ session, capabilities, onStart, onPause, onResume, onStop, onRestart, onChangeVideo, videoEnded = false }: Props) {
  const status = session.status;
  const hasVideo = Boolean(session.sourceName);
  // Yerel dosya yüklemesi olmayan backend'lerde (ör. sunucu video listesinden
  // seçim) bu buton gerçek bir dosya seçici açmaya çalışıp kilitli kalırdı —
  // seçim alanı zaten aynı durumlarda (file-selected/stopped/completed) kendisi
  // görünür oluyor, ayrı bir "değiştir" butonuna gerek kalmıyor.
  const showVideoSelect = capabilities.videoUpload && hasVideo && ["file-selected", "stopped", "completed"].includes(status);
  const showStart = capabilities.start && status === "file-selected";
  const showPause = capabilities.pause && status === "running";
  const showResume = capabilities.resume && status === "paused";
  const showStop = capabilities.stop && !videoEnded && (["preparing", "running", "paused"].includes(status) || (status === "completed" && capabilities.localFilePreview));
  const showRestart = capabilities.restart && (capabilities.localFilePreview ? videoEnded || status === "stopped" : ["paused", "stopped", "completed"].includes(status));

  if (!showVideoSelect && !showStart && !showPause && !showResume && !showStop && !showRestart) return null;

  return (
    <nav className={styles.controls} aria-label="Video ve oturum kontrolleri">
      {showVideoSelect && <button type="button" className={styles.button} onClick={onChangeVideo}><Icon name="upload" />{hasVideo ? "Video Değiştir" : "Video Seç"}</button>}
      {showStart && <button type="button" className={styles.primary} onClick={onStart}><Icon name="play" />Analizi Başlat</button>}
      {showPause && <button type="button" className={styles.button} onClick={onPause}><Icon name="pause" />Duraklat</button>}
      {showResume && <button type="button" className={styles.button} onClick={onResume}><Icon name="play" />Devam Et</button>}
      {showStop && <button type="button" className={styles.button} onClick={onStop}><Icon name="stop" />Durdur</button>}
      {showRestart && <button type="button" className={styles.button} onClick={onRestart}><Icon name="restart" />Baştan Başlat</button>}
    </nav>
  );
}
