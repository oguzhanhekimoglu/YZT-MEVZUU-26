import type { AnalysisStep, VlmDetail, VragDetail } from "../../types";
import { RiskBadge } from "../../components/status/RiskBadge";
import { DetailRows, StepMeta } from "./DetailRows";
import { StepFeedback } from "./StepFeedback";
import { formatDuration, safeText } from "./analysis-utils";
import styles from "./VlmStepDetail.module.css";

export function VlmStepDetail({ step, vrag }: { step: AnalysisStep<VlmDetail>; vrag?: VragDetail }) {
  if (!step.detail || Object.keys(step.detail).length === 0) return <><StepFeedback step={step} />{step.status !== "error" && <p className={styles.empty}>Görsel doğrulama sonucu henüz mevcut değil.</p>}</>;
  const detail = step.detail;
  const conflict = Boolean(vrag?.model && detail.visualPrediction && vrag.model !== detail.visualPrediction);
  return <div>{!(step.status === "warning" && conflict) && <StepFeedback step={step} />}{conflict && <div className={styles.conflict}><strong>⚠ Görsel doğrulama çelişkisi</strong><p>VRAG sonucu: {vrag?.model}</p><p>VLM tahmini: {detail.visualPrediction}</p><small>Sonuç kesin kimlik olarak değerlendirilmemelidir.</small></div>}<DetailRows rows={[
    { label: "Görsel tahmin", value: safeText(detail.visualPrediction) }, { label: "Araç türü", value: safeText(detail.vehicleType) }, { label: "Araç sınıfı", value: safeText(detail.vehicleClass) }, { label: "Ülke hipotezi", value: safeText(detail.countryHypothesis) }, { label: "Tehdit hipotezi", value: detail.threatHypothesis ? <RiskBadge risk={detail.threatHypothesis} /> : "Henüz mevcut değil" }, { label: "VRAG tutarlılığı", value: safeText(detail.vragConsistency) }, { label: "Doğrulama", value: safeText(detail.verification) },
  ]} />{detail.visualAssessment && <section className={styles.assessment}><h4>Görsel Değerlendirme</h4><p>{detail.visualAssessment}</p></section>}<StepMeta duration={formatDuration(step.durationMs)} updatedAt={step.updatedAt} /></div>;
}
