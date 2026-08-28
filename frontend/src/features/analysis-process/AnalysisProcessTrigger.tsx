import { forwardRef } from "react";
import type { OperatorSession, TargetAnalysis } from "../../types";
import type { AnalysisDrawerRequest } from "./analysis-drawer-context";
import { Icon } from "../../components/ui/Icon";
import styles from "./AnalysisProcessTrigger.module.css";

export interface AnalysisProcessTriggerProps {
  session: OperatorSession;
  target?: TargetAnalysis;
  expanded: boolean;
  onOpen: (request: AnalysisDrawerRequest) => void;
}

export const AnalysisProcessTrigger = forwardRef<HTMLButtonElement, AnalysisProcessTriggerProps>(
  function AnalysisProcessTrigger({ session, target, expanded, onOpen }, ref) {
    const steps = target ? [target.detection, target.vrag, target.vlm, target.llm] : [];
    const errorStep = steps.find((step) => step.status === "error");
    const warningStep = steps.find((step) => step.status === "warning");
    const runningStep = steps.find((step) => step.status === "running");
    const partial = session.finalOutput.status === "partial" || Boolean(errorStep);
    const completed = session.status === "completed";
    const title = partial ? "Analiz kısmi tamamlandı" : warningStep ? "Analiz tamamlandı" : completed ? "Analiz tamamlandı" : runningStep ? "Analiz sürüyor" : "Analiz Süreci";
    const detail = partial
      ? `${errorStep?.title ?? "Bir analiz aşaması"} sonucu alınamadı`
      : warningStep
        ? "Kimlik doğrulamasında belirsizlik var"
        : completed
          ? "Nihai çıktı hazır"
          : runningStep
            ? `${runningStep.title} çalışıyor`
            : "Analiz başladığında aşamalar burada izlenecek";
    const tone = partial ? styles.error : warningStep ? styles.warning : completed ? styles.completed : styles.running;

    return (
      <button
        ref={ref}
        type="button"
        className={styles.trigger}
        onClick={() => onOpen(target ? { scope: "target", targetId: target.id } : { scope: "video" })}
        aria-expanded={expanded}
        aria-controls="analysis-process-panel"
      >
        {completed
          ? <span className={`${styles.statusIcon} ${styles.statusIconDone} ${tone}`} aria-hidden="true"><Icon name="check" size={9} /></span>
          : <span className={`${styles.statusIcon} ${tone} ${runningStep ? styles.pulsing : ""}`} aria-hidden="true" />}
        <span className={styles.copy}><strong>{title}</strong><small>{detail}</small></span>
        <span className={styles.action}>{expanded ? "Ayrıntıları Gizle" : "Ayrıntıları Gör"}<Icon name={expanded ? "chevron-up" : "chevron-down"} size={14} /></span>
      </button>
    );
  },
);
