import { forwardRef } from "react";
import type { TimelineGroup } from "./timeline-utils";
import { formatEventTime } from "./timeline-utils";
import styles from "./TimelineCluster.module.css";

export const TimelineCluster = forwardRef<HTMLButtonElement, { group: TimelineGroup; position: number; open: boolean; onOpen: () => void }>(function TimelineCluster({ group, position, open, onOpen }, ref) {
  const critical = group.events.some((event) => event.critical);
  return <button ref={ref} type="button" className={styles.cluster} style={{ left: `${position}%` }} data-critical={critical} aria-expanded={open} aria-label={`${formatEventTime(group.timeSeconds)} civarında ${group.events.length} olay`} onClick={onOpen}><span className={styles.symbol} aria-hidden="true">{critical ? "◆" : "●"}<strong>{group.events.length}</strong></span><time>{formatEventTime(group.timeSeconds)}</time><small>{group.events.length} olay</small></button>;
});
