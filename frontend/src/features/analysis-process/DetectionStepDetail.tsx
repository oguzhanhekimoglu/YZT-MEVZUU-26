import type { AnalysisStep, DetectionDetail } from "../../types";
import { DetailRows, StepMeta } from "./DetailRows";
import { StepFeedback } from "./StepFeedback";
import { formatDuration, percent } from "./analysis-utils";

const trackingLabels: Record<DetectionDetail["trackingStatus"], string> = { active: "Aktif", lost: "Kayboldu", completed: "Tamamlandı" };

export function DetectionStepDetail({ step }: { step: AnalysisStep<DetectionDetail> }) {
  if (!step.detail) return <StepFeedback step={step} />;
  const detail = step.detail;
  return <div><StepFeedback step={step} /><DetailRows rows={[
    { label: "Hedef ID", value: `#${detail.targetId}` },
    { label: "Tespit sınıfı", value: detail.className || "Henüz mevcut değil" },
    { label: "Tespit güveni", value: percent(detail.confidence) },
    { label: "Takip durumu", value: trackingLabels[detail.trackingStatus] },
    { label: "Takip kararlılığı", value: Number.isFinite(detail.hits) ? `${Math.max(0, detail.hits)} eşleşme` : "Henüz mevcut değil" },
    { label: "Hareket hızı", value: detail.speedPxS !== undefined && Number.isFinite(detail.speedPxS) ? `${Math.max(0, detail.speedPxS).toFixed(1)} px/sn` : "Henüz mevcut değil" },
    { label: "Zigzag skoru", value: detail.zigzagScore !== undefined && Number.isFinite(detail.zigzagScore) ? Math.max(0, detail.zigzagScore).toFixed(2) : "Henüz mevcut değil" },
  ]} /><StepMeta duration={formatDuration(step.durationMs)} updatedAt={step.updatedAt} /></div>;
}
