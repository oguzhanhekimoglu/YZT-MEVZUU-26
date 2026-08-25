import { useState } from "react";
import styles from "./VideoDropzone.module.css";

export function VideoDropzone({ onFile }: { onFile?: (file: File) => void }) {
  const [dragging, setDragging] = useState(false);

  if (!onFile) {
    return (
      <div className={styles.dropzone}>
        <p className={styles.title}>Video Analizi</p>
        <p>Üstteki listeden bir video seçin</p>
      </div>
    );
  }

  return (
    <div
      className={`${styles.dropzone} ${dragging ? styles.dragging : ""}`}
      onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
      onDrop={(event) => { event.preventDefault(); setDragging(false); const file = event.dataTransfer.files[0]; if (file) onFile(file); }}
    >
      <p className={styles.title}>Video Analizi</p>
      <p>Videoyu buraya sürükleyin</p>
      <span>veya</span>
      <button type="button" onClick={() => document.getElementById("video-file-input")?.click()}>▣ Dosya Seç</button>
      <small>MP4, MOV, AVI, MKV</small>
    </div>
  );
}
