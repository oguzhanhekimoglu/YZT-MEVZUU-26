import type { AnalysisStep } from "../../types";
import { statusIcons, statusLabels } from "./analysis-utils";
import styles from "./AnalysisSubsteps.module.css";

export function AnalysisSubsteps({ substeps }: { substeps: NonNullable<AnalysisStep["substeps"]> }) {
  const unique = [...new Map(substeps.map((step) => [step.id, step])).values()];
  return <ul className={styles.list}>{unique.map((step) => <li key={step.id} data-status={step.status}><span aria-hidden="true">{statusIcons[step.status]}</span><span>{step.label}</span><small>{statusLabels[step.status]}</small></li>)}</ul>;
}
