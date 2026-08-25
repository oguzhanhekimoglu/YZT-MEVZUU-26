import { useEffect, useState } from "react";
import type { AnalysisStep, TargetAnalysis } from "../../types";
import { Icon } from "../../components/ui/Icon";
import { formatDuration, statusLabels } from "./analysis-utils";
import { VragStepDetail } from "./VragStepDetail";
import { VlmStepDetail } from "./VlmStepDetail";
import { LlmStepDetail } from "./LlmStepDetail";
import styles from "./DecisionChainPanel.module.css";

type ChainStep = "vrag" | "vlm" | "llm";

const titles: Record<ChainStep, string> = {
  vrag: "VRAG · Model Tanıma",
  vlm: "VLM · Görsel Doğrulama",
  llm: "LLM · Operasyonel Karar",
};

const accessibleTitles: Record<ChainStep, string> = {
  vrag: "VRAG Model Eşleştirmesi",
  vlm: "VLM Görsel Doğrulama",
  llm: "LLM Karar Desteği",
};

export function DecisionChainPanel({ target, requestedStepId }: { target: TargetAnalysis; requestedStepId?: AnalysisStep["id"] }) {
  const [expanded, setExpanded] = useState<Record<ChainStep, boolean>>({
    vrag: requestedStepId === "vrag",
    vlm: requestedStepId === "vlm",
    llm: requestedStepId === "llm",
  });

  useEffect(() => {
    if (requestedStepId === "vrag" || requestedStepId === "vlm" || requestedStepId === "llm") {
      setExpanded((current) => ({ ...current, [requestedStepId]: true }));
    }
  }, [requestedStepId]);

  const steps: Array<{ id: ChainStep; step: AnalysisStep; content: React.ReactNode }> = [
    { id: "vrag", step: target.vrag, content: <VragStepDetail step={target.vrag} /> },
    { id: "vlm", step: target.vlm, content: <VlmStepDetail step={target.vlm} vrag={target.vrag.detail} /> },
    { id: "llm", step: target.llm, content: <LlmStepDetail step={target.llm} /> },
  ];

  return <article className={styles.chain} aria-label="VRAG VLM LLM karar zinciri">
    <header className={styles.overview}>
      <span>KARAR ZİNCİRİ</span>
      <strong>{target.displayName}</strong>
      <small>H{target.id} · Kimlik güveni %{Math.round(target.detectionConfidence * 100)}</small>
    </header>
    {steps.map(({ id, step, content }) => {
      const contentId = `decision-chain-${target.id}-${id}`;
      const duration = formatDuration(step.durationMs);
      return <section key={id} className={styles.section} data-status={step.status}>
        <button type="button" className={styles.heading} aria-label={`${accessibleTitles[id]} · ${statusLabels[step.status]}${duration ? ` · ${duration}` : ""}`} aria-expanded={expanded[id]} aria-controls={contentId} onClick={() => setExpanded((current) => ({ ...current, [id]: !current[id] }))}>
          <span className={styles.signal} aria-hidden="true" />
          <strong>{titles[id]}</strong>
          <span className={styles.status}>{statusLabels[step.status]}{duration ? ` · ${duration}` : ""}</span>
          <Icon name={expanded[id] ? "chevron-up" : "chevron-down"} size={14} />
        </button>
        <div id={contentId} className={styles.content} hidden={!expanded[id]}>{expanded[id] && content}</div>
      </section>;
    })}
  </article>;
}
