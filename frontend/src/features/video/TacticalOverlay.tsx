import type { OperatorSession, TimelineEvent } from "../../types";
import { riskLabels } from "../../components/status/RiskBadge";
import { Icon } from "../../components/ui/Icon";
import styles from "./TacticalOverlay.module.css";

const statusLabels: Partial<Record<OperatorSession["status"], string>> = {
  preparing: "MODELLER HAZIRLANIYOR",
  running: "ANALİZ AKTİF",
  paused: "ANALİZ DURAKLATILDI",
  stopped: "ANALİZ DURDURULDU",
  completed: "ANALİZ TAMAMLANDI",
};

function CriticalAlert({ event, onInspect }: { event: TimelineEvent; onInspect: () => void }) {
  return <div className={styles.criticalAlert} role="status">
    <Icon name="warning" size={15} />
    <span><strong>KRİTİK OLAY · {event.timeLabel}</strong><small>{event.title}</small></span>
    <button type="button" onClick={onInspect}>Hedefi İncele</button>
  </div>;
}

export function TacticalOverlay({ session, aspectRatio = 16 / 9, onSelectTarget }: { session: OperatorSession; aspectRatio?: number; onSelectTarget: (id: number) => void }) {
  const targets = session.targets.filter((target) => target.id !== -1 && target.trackingBox);
  const criticalEvent = [...session.events].reverse().find((event) => event.critical && event.status === "active");
  const viewportRatio = 16 / 9;
  const frameStyle = aspectRatio >= viewportRatio
    ? { width: "100%", height: `${(viewportRatio / aspectRatio) * 100}%` }
    : { width: `${(aspectRatio / viewportRatio) * 100}%`, height: "100%" };

  function inspect(event: TimelineEvent) {
    if (event.targetId !== undefined && event.targetId !== -1) onSelectTarget(event.targetId);
    document.querySelector('[aria-label="Zaman Damgalı Olaylar"]')?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }

  return <div className={styles.overlay} aria-label="Taktik analiz katmanı">
    <div className={styles.telemetry}><span>FRAME {session.frameNumber}</span><span>{statusLabels[session.status] ?? "VİDEO HAZIR"}</span></div>
    {criticalEvent && <CriticalAlert event={criticalEvent} onInspect={() => inspect(criticalEvent)} />}
    <div className={styles.frame} style={frameStyle}>
      {targets.map((target) => {
        const box = target.trackingBox!;
        // BUG-FIX (kullanıcı isteği): sade etiket — kimlik yoksa "Hedef #0 ·
        // İHA · %78", kimlik bulunduğunda "Hedef #0 · Bayraktar TB2 · %87".
        // Teknik debug (conf/spd/zz/thr) ve risk sözcüğü artık kutunun
        // üzerinde YAZI olarak yok — risk yalnızca kutunun rengiyle (data-risk) gösterilir.
        const identityLabel = target.vrag.detail?.model ?? target.className;
        const boxLabel = `Hedef #${target.id} · ${identityLabel} · %${Math.round(target.detectionConfidence * 100)}`;
        return <button key={target.id} type="button" className={styles.targetBox} data-risk={target.risk} data-selected={target.id === session.selectedTargetId} style={{ left: `${box.x * 100}%`, top: `${box.y * 100}%`, width: `${box.width * 100}%`, height: `${box.height * 100}%` }} onClick={() => onSelectTarget(target.id)} aria-label={`${boxLabel}, Risk ${riskLabels[target.risk]}`}>
          <span className={styles.targetLabel}><Icon name="target" size={12} /><strong>{boxLabel}</strong></span>
        </button>;
      })}
    </div>
  </div>;
}
