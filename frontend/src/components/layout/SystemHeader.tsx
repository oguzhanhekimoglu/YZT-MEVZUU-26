import { Brand } from "../brand/Brand";
import { SystemPerformancePanel } from "../../features/system-performance/SystemPerformancePanel";
import type { OperatorSession } from "../../types";
import { Icon } from "../ui/Icon";
import { ThemeToggle } from "../ui/ThemeToggle";
import styles from "./SystemHeader.module.css";

function formatTime(seconds = 0): string {
  const safe = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

export function SystemHeader({ session, playbackTime }: { session: OperatorSession; playbackTime?: { currentSeconds: number; durationSeconds: number } }) {
  const currentSeconds = playbackTime?.currentSeconds ?? session.currentSeconds;
  const durationSeconds = playbackTime?.durationSeconds ?? session.durationSeconds;
  return (
    <header className={styles.header}>
      <div className={styles.brandZone}>
        <Brand />
      </div>
      <div className={styles.telemetry} aria-label="Sistem telemetrisi">
        <SystemPerformancePanel session={session} placement="header" />
        <div className={styles.metrics}>
          <div className={styles.timeMetric} aria-label={`Video süresi ${formatTime(currentSeconds)} / ${formatTime(durationSeconds)}`}><Icon name="clock" size={15} /><strong>{formatTime(currentSeconds)}</strong><small>/ {formatTime(durationSeconds)}</small></div>
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
