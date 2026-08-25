import type { RiskLevel } from "../../types";
import styles from "./RiskBadge.module.css";

export const riskLabels: Record<RiskLevel, string> = { info: "Bilgi", low: "Düşük", medium: "Orta", high: "Yüksek", critical: "Kritik", unknown: "Bilinmiyor" };
const riskIcons: Record<RiskLevel, string> = { info: "●", low: "✓", medium: "!", high: "▲", critical: "◆", unknown: "?" };

export function RiskBadge({ risk, prefix }: { risk: RiskLevel; prefix?: string }) {
  return <span className={`${styles.badge} ${styles[risk]}`} data-risk={risk}><span aria-hidden="true">{riskIcons[risk]}</span>{prefix}{prefix ? ": " : ""}{riskLabels[risk]}</span>;
}
