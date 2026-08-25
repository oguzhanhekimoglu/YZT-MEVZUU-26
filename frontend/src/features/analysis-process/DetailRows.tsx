import type { ReactNode } from "react";
import styles from "./DetailRows.module.css";

export interface DetailRow { label: string; value: ReactNode; }

export function DetailRows({ rows }: { rows: DetailRow[] }) {
  return <dl className={styles.rows}>{rows.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl>;
}

export function StepMeta({ duration, updatedAt }: { duration?: string; updatedAt?: string }) {
  if (!duration && !updatedAt) return null;
  return <dl className={styles.meta}>{duration && <div><dt>İşlem süresi</dt><dd>{duration}</dd></div>}{updatedAt && <div><dt>Son güncelleme</dt><dd><time dateTime={updatedAt}>{new Date(updatedAt).toLocaleString("tr-TR")}</time></dd></div>}</dl>;
}
