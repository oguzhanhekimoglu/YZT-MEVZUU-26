import { useEffect, useState } from "react";
import type { OperatorDataSource, ServerVideoOption } from "../../services/contracts";
import { Icon } from "../../components/ui/Icon";
import { isAcceptedVideo } from "./video-utils";
import styles from "./VideoSourcePicker.module.css";

/**
 * Sistem başlığının hemen altında, tam genişlikte sabit bir bölüm — sunucudaki
 * (data/videos/) mevcut videoları doğrudan seçilebilir yapar. Yalnızca
 * `serverPathStart` kabiliyetine sahip backend'lerde (bizim gerçek backend)
 * render edilir; video çerçevesinin içindeki eski konumundan buraya taşındı.
 *
 * BUG-FIX (yeni özellik — kullanıcı isteği): sürükle-bırak video yükleme ve
 * canlı kamera açma kontrolleri de bu barda, sunucu video seçiminin hemen
 * yanında (aynı hizada) render ediliyor.
 */
export function VideoSourcePicker({ dataSource }: { dataSource: OperatorDataSource }) {
  const [videos, setVideos] = useState<ServerVideoOption[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [cameraStarting, setCameraStarting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!dataSource.capabilities.serverPathStart) return;
    let cancelled = false;
    void dataSource.listServerVideos().then((list) => { if (!cancelled) setVideos(list); });
    return () => { cancelled = true; };
  }, [dataSource]);

  if (!dataSource.capabilities.serverPathStart) return null;

  function selectPath(path: string) {
    const name = path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
    void dataSource.selectVideo({ name, serverPath: path });
  }

  async function uploadFile(file: File) {
    if (!isAcceptedVideo(file)) {
      setError("Geçersiz dosya türü. MP4, MOV, AVI veya MKV yükleyin.");
      return;
    }
    setError("");
    setUploading(true);
    try {
      await dataSource.uploadVideo(file);
    } catch (uploadError) {
      setError(`Video yüklenemedi: ${uploadError instanceof Error ? uploadError.message : "bilinmeyen hata"}`);
    } finally {
      setUploading(false);
    }
  }

  async function openCamera() {
    setError("");
    setCameraStarting(true);
    try {
      await dataSource.startCamera();
    } catch (cameraError) {
      setError(`Kamera açılamadı: ${cameraError instanceof Error ? cameraError.message : "bilinmeyen hata"}`);
    } finally {
      setCameraStarting(false);
    }
  }

  return (
    <section className={styles.bar} aria-label="Sunucudaki video seçimi">
      <span className={styles.label}>{videos.length ? "Analiz edilecek videoyu seçin" : "Sunucuda seçilebilir video bulunamadı"}</span>
      {videos.length > 0 && (
        <select
          className={styles.select}
          aria-label="Sunucudaki mevcut videolardan seç"
          defaultValue=""
          onChange={(event) => { const path = event.target.value; if (path) selectPath(path); event.target.value = ""; }}
        >
          <option value="" disabled>Video seçin ({videos.length})</option>
          {videos.map((video) => <option key={video.path} value={video.path}>{video.name}</option>)}
        </select>
      )}
      {dataSource.capabilities.videoUpload && (
        <label
          className={`${styles.upload} ${dragging ? styles.dragging : ""}`}
          aria-label="Video yükle veya sürükle bırak"
          onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const file = event.dataTransfer.files[0];
            if (file) void uploadFile(file);
          }}
        >
          <Icon name="upload" size={14} />
          <span>{uploading ? "Yükleniyor…" : "Video Yükle / Sürükle"}</span>
          <input
            type="file"
            className={styles.hiddenInput}
            accept=".mp4,.mov,.avi,.mkv,video/mp4,video/quicktime,video/x-msvideo,video/x-matroska"
            disabled={uploading}
            onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadFile(file); event.target.value = ""; }}
          />
        </label>
      )}
      {dataSource.capabilities.liveCamera && (
        <button type="button" className={styles.cameraButton} onClick={() => void openCamera()} disabled={cameraStarting}>
          <Icon name="camera" size={14} />
          <span>{cameraStarting ? "Açılıyor…" : "Canlı Kamera Aç"}</span>
        </button>
      )}
      {error && <span className={styles.error} role="alert">{error}</span>}
    </section>
  );
}
