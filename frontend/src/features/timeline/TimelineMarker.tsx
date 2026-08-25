import { forwardRef, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { TimelineEvent } from "../../types";
import { riskLabels } from "../../components/status/RiskBadge";
import { getEventAriaLabel, getEventTimeLabel } from "./timeline-utils";
import styles from "./TimelineMarker.module.css";

const icons = { info: "●", low: "●", medium: "●", high: "▲", critical: "◆", unknown: "○" } as const;
const tooltipWidth = 190;

interface Props { event: TimelineEvent; index: number; total: number; selected: boolean; position: number; onSelect: () => void; onKeyDown: (event: React.KeyboardEvent<HTMLButtonElement>) => void; }

export const TimelineMarker = forwardRef<HTMLButtonElement, Props>(function TimelineMarker({ event, index, total, selected, position, onSelect, onKeyDown }, forwardedRef) {
  const risk = event.critical ? "critical" : event.risk;
  const markerRef = useRef<HTMLButtonElement | null>(null);
  const [tooltip, setTooltip] = useState<{ left: number; top: number }>();
  function setRef(node: HTMLButtonElement | null) {
    markerRef.current = node;
    if (typeof forwardedRef === "function") forwardedRef(node);
    else if (forwardedRef) forwardedRef.current = node;
  }
  function showTooltip() {
    const rect = markerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const left = Math.min(window.innerWidth - tooltipWidth / 2 - 8, Math.max(tooltipWidth / 2 + 8, rect.left + rect.width / 2));
    const top = rect.top > 100 ? rect.top - 8 : rect.bottom + 8;
    setTooltip({ left, top });
  }
  return <><button ref={setRef} type="button" className={`${styles.marker} timeline-marker`} style={{ left: `${position}%` }} data-risk={risk} data-event-id={event.id} aria-current={selected ? "true" : undefined} aria-label={getEventAriaLabel(event, index, total, riskLabels[risk])} onClick={onSelect} onKeyDown={onKeyDown} onMouseEnter={showTooltip} onMouseLeave={() => setTooltip(undefined)} onFocus={showTooltip} onBlur={() => setTooltip(undefined)}><span className={styles.symbol} aria-hidden="true">{icons[risk]}</span><time>{getEventTimeLabel(event)}</time><span className={styles.title} aria-hidden="true">{event.title}</span></button>{tooltip && createPortal(<span className={styles.tooltip} role="tooltip" data-testid="timeline-tooltip" data-placement={tooltip.top < (markerRef.current?.getBoundingClientRect().top ?? 0) ? "top" : "bottom"} style={{ left: tooltip.left, top: tooltip.top }}><strong>{getEventTimeLabel(event)}</strong><span>{event.title}</span><span>{riskLabels[risk]} · {event.targetId !== undefined && event.targetId !== -1 ? `Hedef #${event.targetId}` : "Video Geneli"}</span></span>, document.body)}</>;
});
