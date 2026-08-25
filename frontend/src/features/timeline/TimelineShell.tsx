import { useEffect, useRef, useState } from "react";
import type { OperatorDataSource } from "../../services/contracts";
import type { OperatorSession, TimelineEvent } from "../../types";
import { TimelineCluster } from "./TimelineCluster";
import { TimelineClusterPopover } from "./TimelineClusterPopover";
import { TimelineFilters } from "./TimelineFilters";
import { TimelineMarker } from "./TimelineMarker";
import { filterTimelineEvents, formatEventTime, getEventPosition, getTimelineScale, groupTimelineEvents, sortTimelineEvents, type TimelineFilter } from "./timeline-utils";
import styles from "./TimelineShell.module.css";

export function TimelineShell({ session, dataSource, playbackTime, onSelectEvent }: { session: OperatorSession; dataSource: OperatorDataSource; playbackTime?: { currentSeconds: number; durationSeconds: number }; onSelectEvent?: (event?: TimelineEvent) => void }) {
  const [filter, setFilter] = useState<TimelineFilter>("all");
  const [selectedId, setSelectedId] = useState<string>();
  const [openClusterId, setOpenClusterId] = useState<string>();
  const markerRefs = useRef(new Map<string, HTMLButtonElement>());
  const clusterRefs = useRef(new Map<string, HTMLButtonElement>());
  const previousSessionId = useRef(session.id);
  const sorted = sortTimelineEvents(session.events);
  const visible = filterTimelineEvents(sorted, filter);
  const groups = groupTimelineEvents(visible);
  const scale = getTimelineScale(visible.length ? visible : sorted, playbackTime?.durationSeconds ?? session.durationSeconds);

  useEffect(() => {
    if (previousSessionId.current !== session.id) {
      previousSessionId.current = session.id;
      setFilter("all"); setSelectedId(undefined); setOpenClusterId(undefined);
      onSelectEvent?.(undefined);
    }
  }, [onSelectEvent, session.id]);

  useEffect(() => {
    if (selectedId && !visible.some((event) => event.id === selectedId)) { setSelectedId(undefined); onSelectEvent?.(undefined); }
  }, [onSelectEvent, selectedId, visible]);

  function select(event: TimelineEvent) {
    setSelectedId(event.id); setOpenClusterId(undefined); onSelectEvent?.(event);
    if (event.targetId !== undefined && event.targetId !== -1) void dataSource.selectTarget(event.targetId);
    const video = document.querySelector<HTMLVideoElement>("#video-viewport video");
    if (video && Number.isFinite(event.timeSeconds)) video.currentTime = Math.min(event.timeSeconds, Number.isFinite(video.duration) ? video.duration : event.timeSeconds);
  }
  function markerKey(event: TimelineEvent, key: string) {
    const index = visible.findIndex((item) => item.id === event.id);
    let next: number;
    if (key === "ArrowRight") next = Math.min(visible.length - 1, index + 1);
    else if (key === "ArrowLeft") next = Math.max(0, index - 1);
    else if (key === "Home") next = 0;
    else if (key === "End") next = visible.length - 1;
    else return;
    markerRefs.current.get(visible[next]?.id ?? "")?.focus();
  }

  return <section className={styles.shell} aria-labelledby="timeline-title" data-layout="fixed-timeline">
    <header className={styles.header}>
      <div><h2 id="timeline-title">Zaman Damgalı Olaylar</h2><span>{visible.length === sorted.length ? `${sorted.length} olay` : `${visible.length}/${sorted.length} olay`}</span>{scale.provisional && <small>Süre bekleniyor</small>}</div>
      <TimelineFilters filter={filter} targets={session.targets} onChange={(next) => { setFilter(next); setOpenClusterId(undefined); }} />
    </header>
    <div className={styles.trackViewport} tabIndex={0} aria-label="Yatay kaydırılabilir timeline">
      <div className={styles.track} role="group" aria-label="Timeline olay işaretleri">
        <span className={styles.start}>00:00</span><div className={styles.line} aria-hidden="true" />
        <span className={styles.end}>{scale.provisional ? "Süre bilinmiyor" : formatEventTime(scale.seconds)}</span>
        {!scale.provisional && <span className={styles.playhead} style={{ left: `${getEventPosition(playbackTime?.currentSeconds ?? session.currentSeconds, scale.seconds)}%` }} aria-hidden="true"><b>ŞU AN</b></span>}
        {visible.length === 0 ? <p className={styles.trackEmpty}>{!dataSource.capabilities.persistentEvents && filter === "all" ? "Zaman damgalı olaylar mevcut backend sürümünde henüz sağlanmıyor." : "Bu filtreyle eşleşen olay bulunamadı."}</p> : groups.map((group) => {
          if (group.events.length > 1) return <div key={group.id} className={styles.clusterSlot}>
            <TimelineCluster ref={(node) => { if (node) clusterRefs.current.set(group.id, node); }} group={group} position={getEventPosition(group.timeSeconds, scale.seconds)} open={openClusterId === group.id} onOpen={() => setOpenClusterId((current) => current === group.id ? undefined : group.id)} />
            {openClusterId === group.id && <TimelineClusterPopover events={group.events} timeSeconds={group.timeSeconds} trigger={clusterRefs.current.get(group.id) ?? null} onSelect={select} onClose={() => setOpenClusterId(undefined)} />}
          </div>;
          const event = group.events[0]!;
          const index = visible.findIndex((item) => item.id === event.id);
          return <TimelineMarker key={event.id} ref={(node) => { if (node) markerRefs.current.set(event.id, node); }} event={event} index={index} total={visible.length} selected={event.id === selectedId} position={getEventPosition(event.timeSeconds, scale.seconds)} onSelect={() => select(event)} onKeyDown={(keyboardEvent) => markerKey(event, keyboardEvent.key)} />;
        })}
      </div>
    </div>
  </section>;
}
