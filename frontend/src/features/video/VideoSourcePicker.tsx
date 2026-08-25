import { useEffect, useState } from "react";
import type { OperatorDataSource, ServerVideoOption } from "../../services/contracts";
import styles from "./VideoSourcePicker.module.css";

/**
 * Sistem başlığının hemen altında, tam genişlikte sabit bir bölüm — sunucudaki
 * (data/videos/) mevcut videoları doğrudan seçilebilir yapar. Yalnızca
 * `serverPathStart` kabiliyetine sahip backend'lerde (bizim gerçek backend)
 * render edilir; video çerçevesinin içindeki eski konumundan buraya taşındı.
 */
export function VideoSourcePicker({ dataSource }: { dataSource: OperatorDataSource }) {
  const [videos, setVideos] = useState<ServerVideoOption[]>([]);

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
    </section>
  );
}
