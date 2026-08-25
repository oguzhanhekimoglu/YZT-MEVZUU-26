import type { AnalysisStep, VragDetail } from "../../types";
import { CandidateList } from "./CandidateList";
import { DetailRows, StepMeta } from "./DetailRows";
import { StepFeedback } from "./StepFeedback";
import { formatDuration, percent, safeText } from "./analysis-utils";
import styles from "./VragStepDetail.module.css";

export function VragStepDetail({ step }: { step: AnalysisStep<VragDetail> }) {
  if (!step.detail || (!step.detail.model && !step.detail.candidates.length)) return <><StepFeedback step={step} />{step.status !== "error" && <p className={styles.empty}>Model eşleştirmesi henüz tamamlanmadı.</p>}</>;
  const detail = step.detail;
  return <div>{!(step.status === "warning" && detail.lowConfidence) && <StepFeedback step={step} />}<div className={styles.match}><div className={styles.reference} role="img" aria-label="Referans görsel mevcut değil">▧<small>Referans görsel yok</small></div><div><strong>{safeText(detail.model)}</strong><span>Benzerlik {percent(detail.score)}</span></div></div><DetailRows rows={[
    { label: "Ülke", value: safeText(detail.country) }, { label: "Üretici", value: safeText(detail.manufacturer) }, { label: "Rol", value: safeText(detail.role) }, { label: "Kategori", value: safeText(detail.category) }, { label: "Kimlik güveni", value: percent(detail.score) },
  ]} />{detail.lowConfidence && <div className={styles.lowConfidence}><strong>⚠ Düşük kimlik güveni</strong><p>İlk iki aday birbirine yakın. Operatör doğrulaması önerilir.</p></div>}{detail.margin !== undefined && <p className={styles.margin}>İlk iki aday farkı: {percent(detail.margin)}</p>}<h4>Benzer Adaylar</h4><CandidateList candidates={detail.candidates} /><StepMeta duration={formatDuration(step.durationMs)} updatedAt={step.updatedAt} /></div>;
}
