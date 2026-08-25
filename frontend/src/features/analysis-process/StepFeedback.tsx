import type { AnalysisStep } from "../../types";
import styles from "./StepFeedback.module.css";

export function StepFeedback({ step }: { step: AnalysisStep }) {
  if (step.status === "waiting") return <p className={styles.waiting}>○ Bu aşama önceki analiz sonuçlarını bekliyor. Sonuç henüz üretilmedi.</p>;
  if (step.status === "error") return <div className={styles.error} role="status"><strong>× {step.error ?? "Bu aşamada sonuç üretilemedi."}</strong><p>Mevcut doğrulanmış sonuçlar korunarak analiz kısmi olarak devam edebilir.</p></div>;
  if (step.status === "warning" && step.warning) return <div className={styles.warning}><strong>⚠ {step.warning}</strong><p>Bu durum hata değildir; operatör doğrulaması önerilir.</p></div>;
  return null;
}
