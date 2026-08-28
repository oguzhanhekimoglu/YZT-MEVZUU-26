import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { OperatorSession, SystemPerformance, TargetAnalysis } from "../../types";
import { Icon } from "../../components/ui/Icon";
import styles from "./SystemPerformancePanel.module.css";

type Tab = "live" | "quality";

const healthLabels: Record<NonNullable<SystemPerformance["health"]>, string> = {
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

const connectionLabels: Record<OperatorSession["connection"], string> = {
  connecting: "Bağlanıyor",
  connected: "Bağlı",
  reconnecting: "Yeniden bağlanıyor",
  disconnected: "Bağlantı yok",
};

// BUG-FIX (mimari değişiklik — kullanıcı isteği): bu satırlar eskiden video
// karesine yakılan yeşil HUD metniydi (FPS/Slicer/Tracker/Ham/Onay), video
// artık temiz — aynı telemetri burada, gerçek backend verisiyle gösteriliyor.
// Backend henüz sağlamadığı alanlar (GPU/bellek/health) sahte veriyle
// doldurulmaz, sadece mevcut olanlar satır olarak eklenir.
function LiveMetrics({ performance, activeTargetCount, connection }: { performance: SystemPerformance; activeTargetCount?: number; connection?: OperatorSession["connection"] }) {
  const rows: [string, string][] = [];
  if (performance.framesPerSecond !== undefined) rows.push(["İşleme hızı", `${performance.framesPerSecond} FPS`]);
  if (performance.frameMs !== undefined) rows.push(["Kare süresi", `${performance.frameMs} ms`]);
  if (performance.slicerMs !== undefined) rows.push(["Slicer", `${performance.slicerMs} ms`]);
  if (performance.trackerMs !== undefined) rows.push(["Tracker", `${performance.trackerMs} ms`]);
  if (performance.processingSeconds !== undefined) rows.push(["İşlem süresi", formatDuration(performance.processingSeconds)]);
  if (performance.droppedFrameRate !== undefined) rows.push(["Kare kaybı", `%${performance.droppedFrameRate}`]);
  if (activeTargetCount !== undefined) rows.push(["Aktif hedef", `${activeTargetCount}`]);
  if (performance.rawDetectionCount !== undefined) rows.push(["Ham tespit", `${performance.rawDetectionCount}`]);
  if (performance.suspendedTargetCount !== undefined) rows.push(["Askıda hedef", `${performance.suspendedTargetCount}`]);
  const hasResources = performance.gpuUtilization !== undefined || performance.memoryGb !== undefined;
  const hasHealthRow = performance.health !== undefined || connection !== undefined || performance.queueDepth !== undefined;

  return <div className={styles.live}>
    {rows.length > 0
      ? <dl className={styles.metricGrid}>{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      : <p className={styles.empty}>Canlı performans verisi bekleniyor.</p>}
    {hasResources && <div className={styles.resources}>
      {performance.gpuUtilization !== undefined && <Meter label="GPU kullanımı" value={performance.gpuUtilization} />}
      {performance.memoryGb !== undefined && <Meter label="Bellek" value={performance.memoryGb} unit=" GB" max={8} />}
    </div>}
    {hasHealthRow && <div className={styles.health}>
      {performance.health !== undefined && <><span>Sistem durumu</span><strong data-health={performance.health}>{healthLabels[performance.health]}</strong></>}
      {connection !== undefined && <small>{connectionLabels[connection]}</small>}
      {performance.queueDepth !== undefined && <small>Kuyruk: {performance.queueDepth} kare</small>}
    </div>}
  </div>;
}

// BUG-FIX (kullanıcı isteği): "Hedef Kalite Skorları" artık TargetIdentityPanel
// (Operasyonel Karar'ın altında) DEĞİL, buradaki "Kalite KPI'ları" sekmesinde -
// sistem geneli doğrulama KPI'larından (aşağıdaki available bloğu) AYRI bir alt
// bölüm olarak gösteriliyor, birbirine karıştırılmıyor.
const unknown = "Henüz belirlenmedi";
function TargetQualityScores({ target }: { target?: TargetAnalysis }) {
  if (!target) return <div className={styles.targetQuality}><header className={styles.subHeading}><span>HEDEF KALİTE SKORLARI</span></header><p className={styles.empty}>Hedef seçildiğinde kalite skorları burada gösterilecek.</p></div>;
  const detection = target.detection.detail;
  const vrag = target.vrag.detail;
  return <div className={styles.targetQuality}>
    <header className={styles.subHeading}><span>HEDEF KALİTE SKORLARI</span><small>Hedef #{target.id}</small></header>
    <dl className={styles.metricGrid}>
      <div><dt>YOLO güveni</dt><dd>{detection ? `%${Math.round(detection.confidence * 100)}` : unknown}</dd></div>
      <div><dt>Takip kararlılığı</dt><dd>{detection ? `${detection.hits} vuruş` : unknown}</dd></div>
      <div><dt>VRAG/SigLIP benzerliği</dt><dd>{vrag?.score !== undefined ? vrag.score.toFixed(2) : unknown}</dd></div>
      <div><dt>Kimlik güveni</dt><dd>%{Math.round(target.detectionConfidence * 100)}</dd></div>
    </dl>
  </div>;
}

function QualityMetrics({ performance, target }: { performance: SystemPerformance; target?: TargetAnalysis }) {
  const metrics = [
    ["Olay tespit doğruluğu", performance.eventDetectionAccuracy],
    ["Kritik olay yakalama", performance.criticalEventRecall],
    ["Özet kalitesi", performance.summaryQuality],
    ["Aksiyon doğruluğu", performance.actionAccuracy],
  ] as const;
  const available = metrics.every(([, value]) => value !== undefined);

  return <div className={styles.quality}>
    {available
      ? <>
        <div className={styles.scoreGrid}>{metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>%{value}</strong><small>{value! >= 90 ? "Hedef üstü" : value! >= 80 ? "Kabul edilebilir" : "İnceleme gerekli"}</small></div>)}</div>
        {performance.loadTest && <section className={styles.loadTest}>
          <div><span>YÜK TESTİ</span><strong data-health={performance.loadTest.result}>{healthLabels[performance.loadTest.result]}</strong></div>
          <p>{performance.loadTest.parallelVideos} paralel video · {performance.loadTest.resolution} · {performance.loadTest.averageFramesPerSecond} FPS · %{performance.loadTest.droppedFrameRate} kare kaybı</p>
        </section>}
        <p className={styles.source}>Demo doğrulama seti · {performance.validationScenarioCount} senaryo{performance.measuredAt ? ` · ${new Date(performance.measuredAt).toLocaleDateString("tr-TR")}` : ""}</p>
      </>
      : <p className={styles.empty}>Kalite KPI'ları analiz tamamlandığında gösterilecek.</p>}
    <TargetQualityScores target={target} />
  </div>;
}

// BUG-FIX ("Kalite KPI'ları video panelinin altında kalıyor"): sayfa kabı
// (OperatorShell.module.css .shell) `overflow: hidden` kullanıyor — bu
// panel eskiden `position: absolute` ile o kabın İÇİNDE konumlandığı için
// video alanının üzerine taştığı an kırpılıp görünmez oluyordu. Header
// yerleşiminde artık bir React portal ile doğrudan document.body'ye,
// `position: fixed` ve butonun gerçek konumuna göre hesaplanmış
// koordinatlarla çiziliyor — hiçbir üst kapsayıcının overflow/stacking
// context'inden etkilenmiyor.
function useFixedPanelPosition(anchorRef: React.RefObject<HTMLElement | null>, active: boolean) {
  const [rect, setRect] = useState<{ top: number; right: number } | null>(null);
  useEffect(() => {
    if (!active) { setRect(null); return; }
    function update() {
      const node = anchorRef.current;
      if (!node) return;
      const box = node.getBoundingClientRect();
      setRect({ top: box.bottom + 8, right: window.innerWidth - box.right });
    }
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => { window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); };
  }, [active, anchorRef]);
  return rect;
}

export function SystemPerformancePanel({ session, placement = "sidebar" }: { session: OperatorSession; placement?: "sidebar" | "header" }) {
  const [expanded, setExpanded] = useState(false);
  const [tab, setTab] = useState<Tab>("live");
  const panelId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const fixedRect = useFixedPanelPosition(triggerRef, expanded && placement === "header");
  const performance = session.performance;
  const selectedTarget = session.targets.find((item) => item.id === session.selectedTargetId);
  const fpsText = performance?.framesPerSecond !== undefined ? `${performance.framesPerSecond} FPS` : undefined;
  const frameMsText = performance?.frameMs !== undefined ? `${performance.frameMs} ms` : undefined;
  const summary = placement === "header"
    ? <span className={styles.telemetrySummary}>{fpsText || frameMsText ? <>{performance?.health !== undefined && <strong>{healthLabels[performance.health]}</strong>}{fpsText && <span>{fpsText}</span>}{frameMsText && <span>{frameMsText}</span>}{performance?.gpuUtilization !== undefined && <span>GPU %{performance.gpuUtilization}</span>}</> : <span className={styles.waiting}>Veri bekleniyor</span>}</span>
    : <span className={styles.copy}><strong>Sistem Performansı</strong><small>{fpsText || frameMsText ? [fpsText, frameMsText].filter(Boolean).join(" · ") : "Telemetri verisi bekleniyor"}</small></span>;

  const panel = expanded && <div
    id={panelId}
    className={`${styles.panel} ${placement === "header" ? styles.headerPanel : ""}`}
    style={placement === "header" && fixedRect ? { top: fixedRect.top, right: fixedRect.right } : undefined}
  >
    <div className={styles.tabs} role="tablist" aria-label="Performans görünümü">
      <button type="button" role="tab" aria-selected={tab === "live"} onClick={() => setTab("live")}>Canlı Performans</button>
      <button type="button" role="tab" aria-selected={tab === "quality"} onClick={() => setTab("quality")}>Kalite KPI'ları</button>
    </div>
    <div role="tabpanel">{performance ? tab === "live" ? <LiveMetrics performance={performance} activeTargetCount={session.activeTargetCount} connection={session.connection} /> : <QualityMetrics performance={performance} target={selectedTarget} /> : <p className={styles.empty}>Backend telemetri verisi sağladığında performans ölçümleri burada gösterilecek.</p>}</div>
  </div>;

  return <section className={`${styles.shell} ${placement === "header" ? styles.headerPlacement : ""}`} aria-label="Sistem Performansı">
    <button ref={triggerRef} type="button" className={styles.trigger} aria-expanded={expanded} aria-controls={panelId} onClick={() => setExpanded((current) => !current)}>
      <span className={styles.pulse} data-health={performance?.health ?? "unknown"} aria-hidden="true" />
      {summary}
      <span className={styles.action}>{placement !== "header" && (expanded ? "Gizle" : "Görüntüle")}<Icon name={expanded ? "chevron-up" : "chevron-down"} size={14} /></span>
    </button>
    {placement === "header" ? (fixedRect && panel ? createPortal(panel, document.body) : null) : panel}
  </section>;
}
