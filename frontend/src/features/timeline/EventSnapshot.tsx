import { useState } from "react";
import type { TimelineEvent } from "../../types";
import { getEventTimeLabel } from "./timeline-utils";
import styles from "./EventSnapshot.module.css";

export function EventSnapshot({ event }: { event: TimelineEvent }) {
  const [failed, setFailed] = useState(false);
  if (!event.snapshotUrl) return null;
  return <div className={styles.snapshot}>{failed ? <span role="img" aria-label="Olay görseli yüklenemedi">▧ Görsel yüklenemedi</span> : <img src={event.snapshotUrl} alt={`${event.title}, ${getEventTimeLabel(event)} olay görüntüsü`} onError={() => setFailed(true)} />}</div>;
}
