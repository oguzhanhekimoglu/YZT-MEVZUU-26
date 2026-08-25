import type { ActionRecommendation } from "../../types";
import styles from "./ActionList.module.css";

const labels: Record<ActionRecommendation["priority"], string> = { urgent: "Acil", high: "Yüksek", normal: "Normal" };

export function ActionList({ actions }: { actions: ActionRecommendation[] }) {
  if (actions.length === 0) return <p className={styles.empty}>Aksiyon önerisi bekleniyor.</p>;
  return <ol className={styles.list}>{actions.map((action) => <li key={action.id}><span>{action.label}</span><strong data-priority={action.priority}>{labels[action.priority]}</strong></li>)}</ol>;
}
