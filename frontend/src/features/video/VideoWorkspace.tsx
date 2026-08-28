import type { OperatorDataSource } from "../../services/contracts";
import type { OperatorSession } from "../../types";
import { VideoDropzone } from "./VideoDropzone";
import { VideoViewport, type VideoSource } from "./VideoViewport";
import { TacticalOverlay } from "./TacticalOverlay";
import styles from "./VideoWorkspace.module.css";

// BUG-FIX (kullanıcı isteği): video sürükle-bırak/yükleme artık SADECE üst
// paneldeki VideoSourcePicker'dan yapılıyor - burada (video alanının kendi
// yer tutucusunda) ikinci bir yükleme yolu istenmiyor. VideoDropzone artık
// prop almıyor, hep sade "Video bekleniyor" yer tutucusunu gösteriyor; bu
// bileşendeki eski selectFile/yerel-önizleme akışı bu yüzden kaldırıldı.
export function VideoWorkspace({ session, dataSource, onPlaybackTimeChange, onVideoEndedChange }: { session: OperatorSession; dataSource: OperatorDataSource; onPlaybackTimeChange?: (time: { currentSeconds: number; durationSeconds: number } | undefined) => void; onVideoEndedChange?: (ended: boolean) => void }) {
  // Oturum durdurulduktan/bitikten sonra streamUrl backend'de eski değerini korur
  // (bkz. existing-backend-adapter.ts pollStatus) — bu yüzden MJPEG'i sadece
  // gerçekten aktif bir oturumda gösteriyoruz, aksi halde dondurulmuş eski kare
  // yerine video seçim alanına (server listesi dahil) geri dönülür.
  const sessionActive = ["preparing", "running", "paused"].includes(session.status);
  const viewportSource: VideoSource = session.streamUrl && dataSource.capabilities.mjpegStream && sessionActive
    ? { type: "mjpeg", url: session.streamUrl, name: session.sourceName ?? "Backend" }
    : { type: "placeholder" };

  return (
    <section className={styles.workspace} aria-label="Video analizi">
      <VideoViewport source={viewportSource} playbackStatus={session.status} onPlaybackTimeChange={onPlaybackTimeChange} onVideoEndedChange={onVideoEndedChange} overlay={viewportSource.type === "mjpeg" ? <TacticalOverlay session={session} aspectRatio={session.streamAspectRatio ?? 16 / 9} onSelectTarget={(id) => void dataSource.selectTarget(id)} /> : undefined}>
        <VideoDropzone />
      </VideoViewport>
    </section>
  );
}
