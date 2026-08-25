import type { TargetAnalysis } from "../../types";
import type { TimelineFilter } from "./timeline-utils";
import styles from "./TimelineFilters.module.css";

export function TimelineFilters({ filter, targets, onChange }: { filter: TimelineFilter; targets: TargetAnalysis[]; onChange: (filter: TimelineFilter) => void }) {
  const items: Array<{ id: TimelineFilter; label: string }> = [
    { id: "all", label: "Tümü" }, { id: "critical", label: "Kritik" }, { id: "high", label: "Yüksek" },
    ...targets.filter((target) => target.id !== -1).map((target) => ({ id: `target:${target.id}` as TimelineFilter, label: `Hedef #${target.id}` })),
  ];
  return <div className={styles.filters} aria-label="Olay filtreleri">{items.map((item) => <button key={item.id} type="button" aria-pressed={filter === item.id} onClick={() => onChange(item.id)}>{item.label}</button>)}</div>;
}
