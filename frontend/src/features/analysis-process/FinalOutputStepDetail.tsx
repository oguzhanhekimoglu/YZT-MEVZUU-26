import { useState } from "react";
import type { FinalOutput } from "../../types";
import { RiskBadge } from "../../components/status/RiskBadge";
import { ActionList } from "../final-result/ActionList";
import { DetailRows } from "./DetailRows";
import { JsonOutputDialog } from "./JsonOutputDialog";
import { downloadFinalOutput, formatFinalOutputJson } from "./json-output";
import { percent, safeText } from "./analysis-utils";
import styles from "./FinalOutputStepDetail.module.css";

const labels: Record<FinalOutput["status"], string> = { pending: "Bekliyor", provisional: "Geçici", final: "Nihai", partial: "Kısmi" };

export function FinalOutputStepDetail({ output, sessionId }: { output: FinalOutput; sessionId: string }) {
  const [jsonOpen, setJsonOpen] = useState(false);
  const [message, setMessage] = useState("");
  if (output.status === "pending") return <p className={styles.empty}>Nihai çıktı önceki analiz aşamalarını bekliyor.</p>;
  async function copy() {
    try { await navigator.clipboard.writeText(formatFinalOutputJson(output)); setMessage("JSON panoya kopyalandı."); }
    catch { setMessage("JSON panoya kopyalanamadı."); }
  }
  return <div><span className={styles.status} data-status={output.status}>{labels[output.status]} sonuç</span>{output.status === "partial" && <p className={styles.partial}>⚠ Bazı analiz aşamaları tamamlanamadı. Bu çıktı kısmi sonuçtur.</p>}<DetailRows rows={[
    { label: "Hava aracı modeli", value: safeText(output.aircraft?.model) }, { label: "Ülke orijini", value: safeText(output.aircraft?.countryOrigin) }, { label: "Üretici", value: safeText(output.aircraft?.manufacturer) }, { label: "Rol", value: safeText(output.aircraft?.role) }, { label: "Araç sınıfı", value: safeText(output.aircraft?.vehicleClass) }, { label: "Kimlik güveni", value: percent(output.aircraft?.identityConfidence) },
  ]} /><section><h4>Genel Video Özeti</h4><p>{output.summary || "Henüz mevcut değil"}</p></section><section><h4>Önemli Zaman Damgalı Olaylar</h4><ul className={styles.events}>{output.events.slice(0,3).map((event) => <li key={event.id}><time>{event.timeLabel}</time><span>{event.title}</span></li>)}</ul></section><section><h4>Genel Risk</h4><RiskBadge risk={output.risk} /><p>{output.riskReason ?? "Risk gerekçesi henüz mevcut değil."}</p></section><section><h4>Önerilen Aksiyonlar</h4><ActionList actions={output.actions} /></section>{output.generatedAt && <p className={styles.generated}>Üretim zamanı: <time dateTime={output.generatedAt}>{new Date(output.generatedAt).toLocaleString("tr-TR")}</time></p>}<div className={styles.actions}><button type="button" onClick={() => setJsonOpen(true)}>JSON'u Görüntüle</button><button type="button" onClick={() => void copy()}>Panoya Kopyala</button><button type="button" onClick={() => downloadFinalOutput(output, sessionId)}>JSON İndir</button></div>{message && <p className={styles.message} role="status">{message}</p>}{jsonOpen && <JsonOutputDialog output={output} onClose={() => setJsonOpen(false)} />}</div>;
}
