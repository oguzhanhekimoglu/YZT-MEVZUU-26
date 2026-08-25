import { useEffect, useMemo, useRef, useState } from "react";
import type { AnalysisStep, OperatorSession } from "../../types";
import { useAnalysisDrawer } from "./analysis-drawer-context";
import { AnalysisStepList } from "./AnalysisStepList";
import { defaultOpenStep, finalStatus, targetSteps } from "./analysis-utils";
import styles from "./AnalysisProcessDrawer.module.css";

export function AnalysisProcessDrawer({ session }: { session: OperatorSession; onSelectTarget: (id: number) => void }) {
  const { isOpen, request } = useAnalysisDrawer();
  const targets = useMemo(() => session.targets.filter((target) => target.id !== -1), [session.targets]);
  const requestedTarget = request?.scope === "target" ? targets.find((target) => target.id === request.targetId) : undefined;
  const requestedTargetMissing = request?.scope === "target" && request.targetId !== undefined && !requestedTarget;
  const selectedTarget = requestedTarget ?? targets.find((target) => target.id === session.selectedTargetId) ?? targets[0];
  const videoSteps: AnalysisStep[] = useMemo(() => [{ id: "final", title: "Nihai Çıktı", status: finalStatus(session.finalOutput), statusText: session.finalOutput.status, summary: session.finalOutput.summary, detail: session.finalOutput }], [session.finalOutput]);
  const videoScope = request?.scope === "video" || requestedTargetMissing || !selectedTarget;
  const steps = videoScope ? videoSteps : targetSteps(selectedTarget, session.finalOutput);
  const [openStepId, setOpenStepId] = useState<AnalysisStep["id"]>();
  const [manualStep, setManualStep] = useState(false);
  const panelRef = useRef<HTMLElement>(null);
  const requestRef = useRef(request);

  useEffect(() => {
    if (!isOpen) { setManualStep(false); return; }
    if (requestRef.current !== request) {
      requestRef.current = request;
      setManualStep(Boolean(request?.stepId));
      setOpenStepId(request?.stepId ?? defaultOpenStep(steps));
      requestAnimationFrame(() => panelRef.current?.scrollIntoView?.({ block: "nearest" }));
    }
  }, [isOpen, request, steps]);

  useEffect(() => {
    if (isOpen && !manualStep && !request?.stepId) setOpenStepId(defaultOpenStep(steps));
  }, [isOpen, manualStep, request?.stepId, steps]);

  if (!isOpen) return null;

  function toggleStep(id: AnalysisStep["id"]) {
    setOpenStepId((current) => current === id ? undefined : id);
    setManualStep(true);
  }

  return (
    <section ref={panelRef} id="analysis-process-panel" className={styles.panel} aria-label="Analiz Süreci ayrıntıları">
      <header className={styles.header}>
        <div><p>ANALİZ AŞAMALARI</p><h2>{!videoScope && selectedTarget ? `Hedef #${selectedTarget.id}` : "Video Geneli"}</h2></div>
      </header>
      <div className={styles.body}>
        <AnalysisStepList steps={steps} openStepId={openStepId} requestedStepId={request?.stepId} target={videoScope ? undefined : selectedTarget} output={session.finalOutput} sessionId={session.id} onToggle={toggleStep} />
      </div>
    </section>
  );
}
