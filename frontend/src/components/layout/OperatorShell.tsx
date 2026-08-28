import { useCallback, useEffect, useRef, useState } from "react";
import type { OperatorDataSource } from "../../services/contracts";
import type { OperatorSession, TargetAnalysis, TimelineEvent } from "../../types";
import { SystemHeader } from "./SystemHeader";
import { SessionControls } from "../controls/SessionControls";
import { VideoWorkspace } from "../../features/video/VideoWorkspace";
import { VideoSourcePicker } from "../../features/video/VideoSourcePicker";
import { TargetIdentityPanel } from "../../features/targets/TargetIdentityPanel";
import { AnalysisProcessTrigger } from "../../features/analysis-process/AnalysisProcessTrigger";
import { AnalysisProcessDrawer } from "../../features/analysis-process/AnalysisProcessDrawer";
import { useAnalysisDrawer } from "../../features/analysis-process/analysis-drawer-context";
import { FinalResultPanel } from "../../features/final-result/FinalResultPanel";
import { SelectedEventPanel } from "../../features/timeline/SelectedEventPanel";
import { TimelineShell } from "../../features/timeline/TimelineShell";
import styles from "./OperatorShell.module.css";

interface OperatorShellProps {
  session: OperatorSession;
  dataSource: OperatorDataSource;
  onChangeVideo: () => void;
  onRestart: () => void;
}

// BUG-FIX (kullanıcı isteği — "sağ taraftaki panel bounding box gidince
// sürekli gidip geliyor"): hedef kısa süreliğine ekrandan/algılamadan
// kaybolduğunda (oklüzyon, tek karelik kayıp vb.) backend'in o karedeki
// hedef listesi geçici olarak boş dönebiliyor - eskiden bu, seçili hedefin
// ANINDA `undefined`'a (ya da yanlışlıkla başka bir hedefe) düşüp sağ
// paneli boşaltmasına/titremesine yol açıyordu. Artık aynı oturumda ve aynı
// selectedTargetId'de kalındığı sürece SON BİLİNEN hedef nesnesi saklanıp
// gösteriliyor - bounding box'ın kendisi (TacticalOverlay) hâlâ doğru
// şekilde kayboluyor, sadece bilgi paneli gereksiz yere titremiyor.
function useStableSelectedTarget(targets: TargetAnalysis[], selectedTargetId: number | undefined, sessionId: string): TargetAnalysis | undefined {
  const cache = useRef<{ sessionId: string; selectedTargetId: number | undefined; target: TargetAnalysis | undefined }>({ sessionId, selectedTargetId, target: undefined });
  const resolved = targets.find((target) => target.id === selectedTargetId) ?? (selectedTargetId === undefined ? targets[0] : undefined);

  if (cache.current.sessionId !== sessionId || cache.current.selectedTargetId !== selectedTargetId) {
    cache.current = { sessionId, selectedTargetId, target: resolved };
  } else if (resolved) {
    cache.current.target = resolved;
  }

  return cache.current.target;
}

export function OperatorShell({ session, dataSource, onChangeVideo, onRestart }: OperatorShellProps) {
  const { isOpen, openAnalysis, closeAnalysis } = useAnalysisDrawer();
  const [playbackTime, setPlaybackTime] = useState<{ currentSeconds: number; durationSeconds: number }>();
  const [videoEnded, setVideoEnded] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<TimelineEvent>();
  const targets = session.targets.filter((target) => target.id !== -1);
  const selectedTarget = useStableSelectedTarget(targets, session.selectedTargetId, session.id);

  useEffect(() => {
    if (session.status === "file-selected") setVideoEnded(false);
  }, [session.id, session.status]);

  const closeSelectedEvent = useCallback(() => {
    setSelectedEvent(undefined);
    if (isOpen) closeAnalysis();
  }, [isOpen, closeAnalysis]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && selectedEvent) {
        closeSelectedEvent();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedEvent, closeSelectedEvent]);

  return (
    <main className={styles.shell}>
      <SystemHeader session={session} playbackTime={dataSource.capabilities.localFilePreview ? playbackTime : undefined} />
      <VideoSourcePicker dataSource={dataSource} />
      <SessionControls
        session={session}
        capabilities={dataSource.capabilities}
        onStart={() => void dataSource.start()}
        onPause={() => void dataSource.pause()}
        onResume={() => void dataSource.resume()}
        onStop={() => void dataSource.stop()}
        onRestart={onRestart}
        onChangeVideo={onChangeVideo}
        videoEnded={videoEnded}
      />
      <div className={styles.workspace}>
        <section className={styles.leftColumn} aria-label="Video çalışma alanı">
          <VideoWorkspace session={session} dataSource={dataSource} onPlaybackTimeChange={setPlaybackTime} onVideoEndedChange={setVideoEnded} />
          <TimelineShell session={session} dataSource={dataSource} playbackTime={playbackTime} onSelectEvent={setSelectedEvent} />
        </section>
        <aside className={styles.rightColumn} aria-label="Operatör karar paneli">
          <AnalysisProcessTrigger session={session} target={selectedTarget} expanded={isOpen} onOpen={(request) => isOpen ? closeAnalysis() : openAnalysis(request)} />
          <AnalysisProcessDrawer session={session} onSelectTarget={(id) => void dataSource.selectTarget(id)} />
          <TargetIdentityPanel target={selectedTarget} />
          <SelectedEventPanel event={selectedEvent} session={session} dataSource={dataSource} onClose={closeSelectedEvent} />
          <FinalResultPanel output={session.finalOutput} sessionId={session.id} onSelectEvent={(event) => {
            setSelectedEvent(event);
            if (event.targetId !== undefined && event.targetId !== -1) void dataSource.selectTarget(event.targetId);
            const video = document.querySelector<HTMLVideoElement>("#video-viewport video");
            if (video && Number.isFinite(event.timeSeconds)) video.currentTime = Math.min(event.timeSeconds, Number.isFinite(video.duration) ? video.duration : event.timeSeconds);
          }} />
        </aside>
      </div>
    </main>
  );
}
