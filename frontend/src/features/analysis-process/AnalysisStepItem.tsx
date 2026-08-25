import type { AnalysisStep, FinalOutput, TargetAnalysis } from "../../types";
import { DetectionStepDetail } from "./DetectionStepDetail";
import { FinalOutputStepDetail } from "./FinalOutputStepDetail";
import { LlmStepDetail } from "./LlmStepDetail";
import { VlmStepDetail } from "./VlmStepDetail";
import { VragStepDetail } from "./VragStepDetail";
import { StepFeedback } from "./StepFeedback";
import { Icon } from "../../components/ui/Icon";
import { formatDuration, statusIcons, statusLabels } from "./analysis-utils";
import styles from "./AnalysisStepItem.module.css";

interface Props {
  step: AnalysisStep;
  open: boolean;
  target?: TargetAnalysis;
  output: FinalOutput;
  sessionId: string;
  onToggle: () => void;
}

export function AnalysisStepItem({ step, open, target, output, sessionId, onToggle }: Props) {
  const duration = formatDuration(step.durationMs);
  const contentId = `analysis-step-${step.id}-content`;
  const buttonId = `analysis-step-${step.id}-button`;
  return (
    <article className={styles.item} data-status={step.status} data-open={open}>
      <button id={buttonId} type="button" className={styles.header} aria-expanded={open} aria-controls={contentId} onClick={onToggle}>
        <span className={styles.icon} aria-hidden="true">{statusIcons[step.status]}</span>
        <span className={styles.title}><strong>{step.title}</strong><small>{step.summary ?? (step.status === "waiting" ? "Önceki aşamalar bekleniyor" : step.statusText)}</small></span>
        <span className={styles.meta}>{statusLabels[step.status]}{duration ? ` · ${duration}` : ""}</span>
        <Icon name={open ? "chevron-up" : "chevron-down"} size={15} />
      </button>
      <div id={contentId} className={styles.content} role="region" aria-labelledby={buttonId} hidden={!open}>
        {open && renderDetail(step, target, output, sessionId)}
      </div>
    </article>
  );
}

function renderDetail(step: AnalysisStep, target: TargetAnalysis | undefined, output: FinalOutput, sessionId: string) {
  if (step.id === "detection") return target ? <DetectionStepDetail step={target.detection} /> : <StepFeedback step={step} />;
  if (step.id === "vrag") return target ? <VragStepDetail step={target.vrag} /> : <StepFeedback step={step} />;
  if (step.id === "vlm") return target ? <VlmStepDetail step={target.vlm} vrag={target.vrag.detail} /> : <StepFeedback step={step} />;
  if (step.id === "llm") return target ? <LlmStepDetail step={target.llm} /> : <StepFeedback step={step} />;
  return <FinalOutputStepDetail output={output} sessionId={sessionId} />;
}
