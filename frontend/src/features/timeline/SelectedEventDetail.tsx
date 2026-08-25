import type { TimelineEvent, TargetAnalysis } from "../../types";
import { RiskBadge } from "../../components/status/RiskBadge";
import type { AnalysisDrawerRequest } from "../analysis-process/analysis-drawer-context";
import { EventSnapshot } from "./EventSnapshot";
import { formatEventTime, getEventTimeLabel } from "./timeline-utils";
import styles from "./SelectedEventDetail.module.css";

const stepLabels = { detection: "Nesne Tespiti", vrag: "VRAG Model Eşleştirmesi", vlm: "VLM Görsel Doğrulama", llm: "LLM Karar Desteği", final: "Nihai Çıktı" } as const;

export function SelectedEventDetail({ event, targets, onOpenAnalysis }: { event?: TimelineEvent; targets: TargetAnalysis[]; onSelectTarget?: (id: number) => void; onOpenAnalysis: (request: AnalysisDrawerRequest) => void }) {
  if (!event) return <div className={styles.empty}>Detay için bir olay seçin.</div>;
  const selectedEvent = event;
  const validTarget = selectedEvent.targetId !== undefined && selectedEvent.targetId !== -1 && targets.some((target) => target.id === selectedEvent.targetId);
  const confidence = selectedEvent.confidence !== undefined && Number.isFinite(selectedEvent.confidence) ? `%${Math.round(Math.min(1, Math.max(0, selectedEvent.confidence)) * 100)}` : undefined;
  function openAnalysis() {
    if (validTarget) onOpenAnalysis({ scope: "target", targetId: selectedEvent.targetId, stepId: selectedEvent.relatedStep });
    else onOpenAnalysis({ scope: "video", stepId: selectedEvent.relatedStep ?? "final" });
  }
  return <div className={styles.detail} data-testid="selected-event-detail"><div className={styles.copy}><div className={styles.title}><strong>{getEventTimeLabel(event)} · {event.critical ? "Kritik Olay" : event.title}</strong><span>{event.targetId !== undefined && event.targetId !== -1 ? `Hedef #${event.targetId}` : "Video Geneli"}</span></div><p>{event.description}</p><dl><div><dt>Risk</dt><dd><RiskBadge risk={event.critical ? "critical" : event.risk} /></dd></div>{confidence && <div><dt>Güven</dt><dd>{confidence}</dd></div>}{event.startSeconds !== undefined && <div><dt>Başlangıç</dt><dd>{formatEventTime(event.startSeconds)}</dd></div>}{event.endSeconds !== undefined && <div><dt>Bitiş</dt><dd>{formatEventTime(event.endSeconds)}</dd></div>}<div><dt>Durum</dt><dd>{event.status === "active" ? "Devam ediyor" : "Tamamlandı"}</dd></div>{event.relatedStep && <div><dt>İlgili aşama</dt><dd>{stepLabels[event.relatedStep]}</dd></div>}</dl>{event.actions?.length ? <p className={styles.relatedActions}>Aksiyonlar: {event.actions.map((action) => action.label).join(" · ")}</p> : null}<div className={styles.actions}><button type="button" onClick={openAnalysis}>Analiz Ayrıntılarını Aç</button></div></div><EventSnapshot event={event} /></div>;
}
