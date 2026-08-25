import { useState } from "react";
import type { FinalOutput, TimelineEvent } from "../../types";
import { RiskBadge } from "../../components/status/RiskBadge";
import { JsonOutputDialog } from "../analysis-process/JsonOutputDialog";
import { downloadFinalOutput, formatFinalOutputJson } from "../analysis-process/json-output";
import styles from "./FinalResultPanel.module.css";

const statusLabels: Record<FinalOutput["status"], string> = { pending: "Sonuç bekleniyor", provisional: "Geçici sonuç", final: "Nihai sonuç", partial: "Kısmi sonuç" };
type EventFilter = "all" | "critical" | "high";

export function FinalResultPanel({ output, sessionId = "oturum", onSelectEvent }: { output: FinalOutput; sessionId?: string; onSelectEvent?: (event: TimelineEvent) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [jsonOpen, setJsonOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [eventFilter, setEventFilter] = useState<EventFilter>("all");
  if (output.status === "pending") return <section className={styles.panel} aria-labelledby="result-title"><header className={styles.heading}><h2 id="result-title">Nihai Analiz Sonucu</h2><div className={styles.headerActions}><span data-status="pending">{statusLabels.pending}</span></div></header><p className={styles.empty}>{output.summary || "Analiz sonucu üretildiğinde genel özet, risk ve aksiyonlar burada gösterilecek."}</p></section>;

  const summaryIsLong = output.summary.length > 180;
  const visibleEvents = output.events.filter((event) => eventFilter === "all" ? true : eventFilter === "critical" ? event.critical : event.risk === "high" && !event.critical);
  async function copyJson() {
    try { await navigator.clipboard.writeText(formatFinalOutputJson(output)); setMessage("JSON panoya kopyalandı."); }
    catch { setMessage("JSON panoya kopyalanamadı."); }
  }
  return (
    <section className={styles.panel} aria-labelledby="result-title">
      <header className={styles.heading}>
        <h2 id="result-title">Nihai Analiz Sonucu</h2>
        <div className={styles.headerActions}>
          <span data-status={output.status}>{statusLabels[output.status]}</span>
          <button type="button" aria-label="JSON'u Görüntüle" onClick={() => setJsonOpen(true)}>JSON</button>
          <button type="button" aria-label="Panoya Kopyala" onClick={() => void copyJson()}>Kopyala</button>
          <button type="button" aria-label="JSON İndir" onClick={() => downloadFinalOutput(output, sessionId)}>İndir</button>
        </div>
      </header>
      <div className={styles.resultGrid}>
        <section className={styles.summary}>
          <h3>Genel Video Özeti</h3>
          <p className={!expanded ? styles.clamped : undefined}>{output.summary}</p>
          {summaryIsLong && <button type="button" className={styles.more} onClick={() => setExpanded((value) => !value)}>{expanded ? "Daha az göster" : "Devamını göster"}</button>}
          <div className={styles.riskLine}><RiskBadge risk={output.risk} prefix="Genel risk" /><small>{output.riskReason ?? "Risk gerekçesi henüz belirlenmedi."}</small></div>
        </section>
        <section>
          <div className={styles.eventHeader}><h3>Zaman Damgalı Olaylar</h3><span>{visibleEvents.length}/{output.events.length}</span></div>
          <div className={styles.eventFilters} aria-label="Nihai sonuç olay filtreleri">
            <button type="button" aria-pressed={eventFilter === "all"} onClick={() => setEventFilter("all")}>Tümü</button>
            <button type="button" aria-pressed={eventFilter === "critical"} onClick={() => setEventFilter("critical")}>Kritik</button>
            <button type="button" aria-pressed={eventFilter === "high"} onClick={() => setEventFilter("high")}>Yüksek</button>
          </div>
          {visibleEvents.length ? <ul className={styles.events}>{visibleEvents.map((event) => <li key={event.id}><button type="button" aria-label={`${event.timeLabel}, ${event.title}, videoda göster`} onClick={() => onSelectEvent?.(event)}><time>{event.timeLabel}</time><span>{event.title}</span><RiskBadge risk={event.risk} /></button></li>)}</ul> : <p className={styles.empty}>Bu filtreyle eşleşen olay bulunamadı.</p>}
        </section>
        <section>
          <h3>Önerilen Aksiyonlar</h3>
          {output.actions.length ? <ol className={styles.actions}>{output.actions.slice(0, 3).map((action, index) => <li key={action.id}><b data-priority={action.priority}>{index + 1}</b><span>{action.label}</span></li>)}</ol> : <p className={styles.empty}>Aksiyon önerisi bekleniyor.</p>}
        </section>
      </div>
      {message && <p role="status" className={styles.jsonMessage}>{message}</p>}
      {jsonOpen && <JsonOutputDialog output={output} onClose={() => setJsonOpen(false)} />}
    </section>
  );
}
