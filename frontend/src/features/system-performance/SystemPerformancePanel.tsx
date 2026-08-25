import { useId, useState } from "react";
import type { OperatorSession, SystemPerformance } from "../../types";
import { Icon } from "../../components/ui/Icon";
import styles from "./SystemPerformancePanel.module.css";

type Tab = "live" | "quality";

const healthLabels: Record<SystemPerformance["health"], string> = {
  stable: "Stabil",
  strained: "Yük altında",
  critical: "Kritik",
};

function formatDuration(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

function Meter({ label, value, unit = "%", max = 100 }: { label: string; value: number; unit?: string; max?: number }) {
  const width = Math.min(100, Math.max(0, (value / max) * 100));
  return <div className={styles.meter}><div><span>{label}</span><strong>{value.toFixed(value % 1 ? 1 : 0)}{unit}</strong></div><span className={styles.track}><span style={{ width: `${width}%` }} /></span></div>;
}

function LiveMetrics({ performance }: { performance: SystemPerformance }) {
  return <div className={styles.live}>
    <dl className={styles.metricGrid}>
      <div><dt>İşlem süresi</dt><dd>{formatDuration(performance.processingSeconds)}</dd></div>
      <div><dt>Inference</dt><dd>{performance.inferenceMs} <small>ms</small></dd></div>
      <div><dt>İşleme hızı</dt><dd>{performance.framesPerSecond} <small>FPS</small></dd></div>
      <div><dt>Kare kaybı</dt><dd>{performance.droppedFrameRate}%</dd></div>
    </dl>
    <div className={styles.resources}>
      <Meter label="GPU kullanımı" value={performance.gpuUtilization} />
      <Meter label="Bellek" value={performance.memoryGb} unit=" GB" max={8} />
    </div>
    <div className={styles.health}><span>Sistem durumu</span><strong data-health={performance.health}>{healthLabels[performance.health]}</strong><small>Kuyruk: {performance.queueDepth} kare</small></div>
  </div>;
}

function QualityMetrics({ performance }: { performance: SystemPerformance }) {
  const metrics = [
    ["Olay tespit doğruluğu", performance.eventDetectionAccuracy],
    ["Kritik olay yakalama", performance.criticalEventRecall],
    ["Özet kalitesi", performance.summaryQuality],
    ["Aksiyon doğruluğu", performance.actionAccuracy],
  ] as const;
  const available = metrics.every(([, value]) => value !== undefined);

  if (!available) return <p className={styles.empty}>Kalite KPI'ları analiz tamamlandığında gösterilecek.</p>;

  return <div className={styles.quality}>
    <div className={styles.scoreGrid}>{metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>%{value}</strong><small>{value! >= 90 ? "Hedef üstü" : value! >= 80 ? "Kabul edilebilir" : "İnceleme gerekli"}</small></div>)}</div>
    {performance.loadTest && <section className={styles.loadTest}>
      <div><span>YÜK TESTİ</span><strong data-health={performance.loadTest.result}>{healthLabels[performance.loadTest.result]}</strong></div>
      <p>{performance.loadTest.parallelVideos} paralel video · {performance.loadTest.resolution} · {performance.loadTest.averageFramesPerSecond} FPS · %{performance.loadTest.droppedFrameRate} kare kaybı</p>
    </section>}
    <p className={styles.source}>Demo doğrulama seti · {performance.validationScenarioCount} senaryo{performance.measuredAt ? ` · ${new Date(performance.measuredAt).toLocaleDateString("tr-TR")}` : ""}</p>
  </div>;
}

export function SystemPerformancePanel({ session, placement = "sidebar" }: { session: OperatorSession; placement?: "sidebar" | "header" }) {
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState<Tab>("live");
  const panelId = useId();
  const performance = session.performance;
  const summary = placement === "header"
    ? <span className={styles.telemetrySummary}>{performance ? <><strong>{healthLabels[performance.health]}</strong><span>{performance.framesPerSecond} FPS</span><span>{performance.inferenceMs} ms</span><span>GPU %{performance.gpuUtilization}</span></> : <span className={styles.waiting}>Veri bekleniyor</span>}</span>
    : <span className={styles.copy}><strong>Sistem Performansı</strong><small>{performance ? `${performance.framesPerSecond} FPS · ${performance.inferenceMs} ms inference` : "Telemetri verisi bekleniyor"}</small></span>;

  return <section className={`${styles.shell} ${placement === "header" ? styles.headerPlacement : ""}`} aria-label="Sistem Performansı">
    <button type="button" className={styles.trigger} aria-expanded={expanded} aria-controls={panelId} onClick={() => setExpanded((current) => !current)}>
      <span className={styles.pulse} data-health={performance?.health ?? "unknown"} aria-hidden="true" />
      {summary}
      <span className={styles.action}>{placement !== "header" && (expanded ? "Gizle" : "Görüntüle")}<Icon name={expanded ? "chevron-up" : "chevron-down"} size={14} /></span>
    </button>
    {expanded && <div id={panelId} className={styles.panel}>
      <div className={styles.tabs} role="tablist" aria-label="Performans görünümü">
        <button type="button" role="tab" aria-selected={tab === "live"} onClick={() => setTab("live")}>Canlı Performans</button>
        <button type="button" role="tab" aria-selected={tab === "quality"} onClick={() => setTab("quality")}>Kalite KPI'ları</button>
      </div>
      <div role="tabpanel">{performance ? tab === "live" ? <LiveMetrics performance={performance} /> : <QualityMetrics performance={performance} /> : <p className={styles.empty}>Backend telemetri verisi sağladığında performans ölçümleri burada gösterilecek.</p>}</div>
    </div>}
  </section>;
}
