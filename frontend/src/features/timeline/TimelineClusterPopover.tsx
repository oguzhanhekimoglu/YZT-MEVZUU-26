import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { TimelineEvent } from "../../types";
import { RiskBadge } from "../../components/status/RiskBadge";
import { formatEventTime } from "./timeline-utils";
import styles from "./TimelineClusterPopover.module.css";

export function TimelineClusterPopover({ events, timeSeconds, trigger, onSelect, onClose }: { events: TimelineEvent[]; timeSeconds: number; trigger: HTMLButtonElement | null; onSelect: (event: TimelineEvent) => void; onClose: () => void }) {
  const popoverRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: window.innerWidth / 2, top: 16 });
  useEffect(() => {
    const rect = trigger?.getBoundingClientRect();
    if (rect) setPosition({ left: Math.min(window.innerWidth - 173, Math.max(173, rect.left + rect.width / 2)), top: Math.min(window.innerHeight - 236, rect.bottom + 8) });
    requestAnimationFrame(() => popoverRef.current?.querySelector<HTMLButtonElement>("ol button")?.focus());
    function keydown(event: KeyboardEvent) { if (event.key === "Escape") { event.preventDefault(); onClose(); trigger?.focus(); } }
    function pointer(event: MouseEvent) { if (!popoverRef.current?.contains(event.target as Node) && event.target !== trigger) onClose(); }
    document.addEventListener("keydown", keydown); document.addEventListener("mousedown", pointer);
    return () => { document.removeEventListener("keydown", keydown); document.removeEventListener("mousedown", pointer); };
  }, [onClose, trigger]);
  return createPortal(<div ref={popoverRef} className={styles.popover} style={position} role="dialog" aria-label={`${formatEventTime(timeSeconds)} civarındaki olaylar`}><header><strong>{formatEventTime(timeSeconds)} civarında {events.length} olay</strong><button type="button" onClick={() => { onClose(); trigger?.focus(); }} aria-label="Olay kümesini kapat">×</button></header><ol>{events.map((event) => <li key={event.id}><button type="button" data-event-id={event.id} onClick={() => { onSelect(event); onClose(); trigger?.focus(); }}><span>{event.title}</span><RiskBadge risk={event.critical ? "critical" : event.risk} /></button></li>)}</ol></div>, document.body);
}
