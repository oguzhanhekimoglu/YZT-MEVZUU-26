import styles from "./VideoDropzone.module.css";

// BUG-FIX (kullanıcı isteği): video yükleme/sürükle-bırak artık SADECE üst
// paneldeki VideoSourcePicker'dan yapılıyor - burada ikinci bir yükleme yolu
// istenmiyor. Bu bileşen artık salt bir durum yer tutucusu.
export function VideoDropzone() {
  return (
    <div className={styles.dropzone}>
      <p>Video bekleniyor</p>
    </div>
  );
}
