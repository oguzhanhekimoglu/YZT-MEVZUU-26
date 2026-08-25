import styles from "./StatusBadge.module.css";

export type StatusTone = "neutral" | "accent" | "success" | "warning" | "danger";

export function StatusBadge({ icon, label, tone = "neutral" }: { icon: string; label: string; tone?: StatusTone }) {
  return <span className={`${styles.badge} ${styles[tone]}`}><span aria-hidden="true">{icon}</span>{label}</span>;
}
