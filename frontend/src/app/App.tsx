import { useEffect, useState } from "react";
import { OperatorShell } from "../components/layout/OperatorShell";
import { ConfirmationDialog } from "../components/ui/ConfirmationDialog";
import { useOperatorDataSource } from "./providers";
import type { OperatorSession } from "../types";

const emptySession: OperatorSession = {
  id: "uninitialized",
  status: "idle",
  connection: "connecting",
  localMode: true,
  currentSeconds: 0,
  frameNumber: 0,
  activeTargetCount: 0,
  criticalEventCount: 0,
  targets: [],
  events: [],
  finalOutput: { status: "pending", summary: "", events: [], risk: "unknown", actions: [] },
};

type Confirmation = "restart" | "change-video" | null;

export function App() {
  const dataSource = useOperatorDataSource();
  const [session, setSession] = useState<OperatorSession>(emptySession);
  const [confirmation, setConfirmation] = useState<Confirmation>(null);

  useEffect(() => dataSource.subscribe(setSession), [dataSource]);

  const hasAnalysis = !["idle", "file-selected"].includes(session.status);

  function requestVideoChange() {
    if (hasAnalysis) setConfirmation("change-video");
    else document.getElementById("video-file-input")?.click();
  }

  async function confirmAction() {
    if (confirmation === "restart") await dataSource.restart();
    if (confirmation === "change-video") document.getElementById("video-file-input")?.click();
    setConfirmation(null);
  }

  return (
    <>
      <OperatorShell
        session={session}
        dataSource={dataSource}
        onChangeVideo={requestVideoChange}
        onRestart={() => setConfirmation("restart")}
      />
      {confirmation && (
        <ConfirmationDialog
          title={confirmation === "restart" ? "Analizi baştan başlat" : "Videoyu değiştir"}
          description={confirmation === "restart"
            ? "Mevcut analiz sonuçları temizlenecek ve aynı video yeniden hazırlanacak."
            : "Mevcut analiz durumu korunmayacak. Başka bir video seçmek istiyor musunuz?"}
          confirmLabel={confirmation === "restart" ? "Baştan Başlat" : "Video Seç"}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => void confirmAction()}
        />
      )}
    </>
  );
}
