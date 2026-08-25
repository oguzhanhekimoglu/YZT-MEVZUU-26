import { useState } from "react";
import type { TargetAnalysis } from "../../types";
import { riskLabels } from "../../components/status/RiskBadge";
import { Icon } from "../../components/ui/Icon";
import styles from "./TargetIdentityPanel.module.css";

const unknown = "Henüz belirlenmedi";

export function TargetIdentityPanel({ target }: { target?: TargetAnalysis }) {
  const [failedReference, setFailedReference] = useState<string>();
  if (!target) return <section className={styles.panel}><p className={styles.empty}>Hedef kimliği analiz başladığında burada gösterilecek.</p></section>;
  const vrag = target.vrag.detail;
  const vehicleClass = target.vlm.detail?.vehicleClass;
  const decision = target.llm.detail;
  const primaryAction = decision?.actions[0];
  const rationale = decision?.summary ?? target.llm.summary ?? "Operasyonel karar hazırlanıyor.";
  return (
    <section className={styles.panel} aria-label="Seçili hedef karar ve kimlik bilgileri">
      <article className={styles.identityCard} aria-labelledby="target-title">
        <header className={styles.sectionHeading}><span>SEÇİLİ HEDEF KİMLİĞİ</span></header>
        <div className={styles.identityBody}>
          {vrag?.referenceImageUrl && failedReference !== vrag.referenceImageUrl
            ? <div className={styles.reference}><img src={vrag.referenceImageUrl} alt={`${target.displayName} referans görseli`} onError={() => setFailedReference(vrag.referenceImageUrl)} /></div>
            : <div className={styles.reference} role="img" aria-label={`${target.displayName} referans görseli mevcut değil`}><Icon name="image" size={24} /><small>Referans görsel yok</small></div>}
          <div className={styles.identity}>
            <h2 id="target-title">{vrag?.model ?? target.displayName ?? unknown}</h2>
            <dl>
              <div><dt>Ülke</dt><dd>{vrag?.country ?? unknown}</dd></div>
              <div><dt>Üretici</dt><dd>{vrag?.manufacturer ?? unknown}</dd></div>
              <div><dt>Rol</dt><dd>{vrag?.role ?? unknown}</dd></div>
              <div><dt>Araç sınıfı</dt><dd>{vehicleClass ?? target.className ?? unknown}</dd></div>
              <div><dt>Kimlik güveni</dt><dd>%{Math.round(target.detectionConfidence * 100)}</dd></div>
              <div><dt>Takip kimliği</dt><dd>Hedef #{target.id}</dd></div>
            </dl>
          </div>
        </div>
      </article>
      <article className={styles.decision} data-risk={target.risk}>
        <header className={styles.sectionHeading}><Icon name="target" size={15} /><span>OPERASYONEL KARAR</span></header>
        <div className={styles.decisionBody}>
          <div className={styles.decisionCopy}>
            <h2>{primaryAction ? primaryAction.label : target.llm.status === "running" ? "Karar desteği üretiliyor" : "Operatör değerlendirmesi bekleniyor"}</h2>
            <p>{rationale}</p>
          </div>
          <div className={styles.decisionMeta}>
            <div className={styles.riskBox}><span>HEDEF RİSKİ</span><strong data-risk={target.risk}>{riskLabels[target.risk]}</strong></div>
            {decision?.humanReviewRequired && <span className={styles.review}><Icon name="warning" size={13} />İnsan doğrulaması gerekli</span>}
          </div>
        </div>
      </article>
    </section>
  );
}
