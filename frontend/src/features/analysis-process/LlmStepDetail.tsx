import type { AnalysisStep, LlmDetail } from "../../types";
import { RiskBadge } from "../../components/status/RiskBadge";
import { ActionList } from "../final-result/ActionList";
import { AnalysisSubsteps } from "./AnalysisSubsteps";
import { DetailRows, StepMeta } from "./DetailRows";
import { RiskFactors } from "./RiskFactors";
import { StepFeedback } from "./StepFeedback";
import { formatDuration, safeText } from "./analysis-utils";
import styles from "./LlmStepDetail.module.css";

export function LlmStepDetail({ step }: { step: AnalysisStep<LlmDetail> }) {
  if (step.status === "running" && step.substeps?.length) return <div><AnalysisSubsteps substeps={step.substeps} /><StepMeta duration={formatDuration(step.durationMs)} updatedAt={step.updatedAt} /></div>;
  if (!step.detail || step.status === "waiting" || step.status === "error") return <><StepFeedback step={step} />{step.status !== "error" && <p className={styles.empty}>Nihai risk henüz belirlenmedi.</p>}</>;
  const detail = step.detail;
  return <div><StepFeedback step={step} /><DetailRows rows={[
    { label: "Nihai risk", value: detail.risk === "unknown" ? "Nihai risk henüz belirlenmedi" : <RiskBadge risk={detail.risk} /> }, { label: "Karar", value: safeText(detail.decision) }, { label: "Envanter", value: safeText(detail.inventoryStatus) }, { label: "Uçuş izni", value: safeText(detail.permissionStatus) }, { label: "Uçuş planı", value: safeText(detail.flightPlanStatus) }, { label: "NOTAM", value: safeText(detail.notamStatus) }, { label: "Operatör teyidi", value: detail.humanReviewRequired === undefined ? "Henüz mevcut değil" : detail.humanReviewRequired ? "Gerekli" : "Gerekli değil" },
  ]} />{detail.summary && <section className={styles.summary}><h4>Operasyonel Değerlendirme</h4><p>{detail.summary}</p></section>}<RiskFactors increasing={detail.riskIncreasingFactors} reducing={detail.riskReducingFactors} /><section className={styles.actions}><h4>Önerilen Aksiyonlar</h4><ActionList actions={detail.actions} /></section><StepMeta duration={formatDuration(step.durationMs)} updatedAt={step.updatedAt} /></div>;
}
