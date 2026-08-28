import type {
  OperatorCapabilities,
  OperatorDataSource,
  OperatorSessionListener,
  SelectedVideo,
  ServerVideoOption,
  Unsubscribe,
} from "../services/contracts";
import type { OperatorSession, SessionStatus } from "../types";
import { idleSessionFixture, preparingSessionFixture, detectionSessionFixture, vragRunningSessionFixture, vlmRunningSessionFixture, runningSessionFixture, completedSessionFixture } from "./fixtures";

export const testCapabilities: OperatorCapabilities = {
  localFilePreview: true, videoUpload: true, liveCamera: true, serverPathStart: false, start: true,
  pause: true, resume: true, stop: true, restart: true, mjpegStream: false,
  liveTargets: true, persistentEvents: true, finalOutput: true, referenceImages: false,
  metrics: false, eventSnapshots: true, seekToEvent: false,
};

export interface TestScenario {
  readonly id: string;
  readonly label: string;
  readonly snapshots: readonly OperatorSession[];
}

export const basicPipelineScenario: TestScenario = {
  id: "basic-pipeline",
  label: "Temel pipeline",
  snapshots: [idleSessionFixture, preparingSessionFixture, detectionSessionFixture, vragRunningSessionFixture, vlmRunningSessionFixture, runningSessionFixture, completedSessionFixture],
};

function cloneSession(session: OperatorSession): OperatorSession {
  return structuredClone(session);
}

/**
 * Controllable in-memory `OperatorDataSource` double used only by component/unit tests
 * (vitest + React Testing Library). Not wired into `src/services/data-source.ts` and never
 * shipped as a selectable production data source.
 */
export class TestOperatorDataSource implements OperatorDataSource {
  readonly capabilities = testCapabilities;
  private index = 0;
  private session: OperatorSession = cloneSession(idleSessionFixture);
  private timer: ReturnType<typeof setInterval> | undefined;
  private readonly listeners = new Set<OperatorSessionListener>();

  constructor(private readonly scenario: TestScenario = basicPipelineScenario) {
    if (scenario.snapshots.length < 2) {
      throw new Error("Test senaryosu en az iki oturum anlık görüntüsü içermelidir.");
    }
  }

  getSession(): Promise<OperatorSession> { return Promise.resolve(cloneSession(this.session)); }

  subscribe(listener: OperatorSessionListener): Unsubscribe {
    this.listeners.add(listener);
    listener(cloneSession(this.session));
    return () => this.listeners.delete(listener);
  }

  selectVideo(video: SelectedVideo): Promise<OperatorSession> {
    this.clearTimer();
    this.index = 0;
    this.session = {
      ...cloneSession(idleSessionFixture),
      id: "test-selected-session",
      status: "file-selected",
      sourceName: video.name,
      durationSeconds: video.durationSeconds,
    };
    return Promise.resolve(this.publish());
  }

  listServerVideos(): Promise<ServerVideoOption[]> { return Promise.resolve([]); }

  uploadVideo(file: File): Promise<SelectedVideo> {
    const video: SelectedVideo = { name: file.name };
    void this.selectVideo(video);
    return Promise.resolve(video);
  }

  startCamera(index = 0): Promise<OperatorSession> {
    this.clearTimer();
    this.index = 1;
    this.applySnapshot();
    this.session = { ...this.session, sourceName: `Kamera ${index}`, durationSeconds: undefined };
    this.startTimer();
    return Promise.resolve(this.publish());
  }

  start(): Promise<OperatorSession> {
    this.index = 1;
    this.applySnapshot();
    this.startTimer();
    return Promise.resolve(this.publish());
  }

  pause(): Promise<OperatorSession> { return Promise.resolve(this.setStatus("paused", true)); }
  resume(): Promise<OperatorSession> {
    const session = this.setStatus("running", false);
    this.startTimer();
    return Promise.resolve(session);
  }
  stop(): Promise<OperatorSession> { return Promise.resolve(this.setStatus("stopped", true)); }

  restart(): Promise<OperatorSession> {
    this.clearTimer();
    this.index = 0;
    this.session = {
      ...cloneSession(idleSessionFixture),
      id: "test-restarted-session",
      status: "file-selected",
      sourceName: this.session.sourceName,
      durationSeconds: this.session.durationSeconds,
    };
    return Promise.resolve(this.publish());
  }

  selectTarget(targetId: number): Promise<OperatorSession> {
    if (targetId === -1 || !this.session.targets.some((target) => target.id === targetId)) {
      return Promise.resolve(cloneSession(this.session));
    }
    this.session = {
      ...this.session,
      selectedTargetId: targetId,
      targets: this.session.targets.map((target) => ({ ...target, selected: target.id === targetId })),
    };
    return Promise.resolve(this.publish());
  }

  advance(): OperatorSession {
    this.index = Math.min(this.index + 1, this.scenario.snapshots.length - 1);
    this.applySnapshot();
    return this.publish();
  }

  reset(): OperatorSession {
    this.clearTimer();
    this.index = 0;
    this.session = cloneSession(idleSessionFixture);
    return this.publish();
  }

  dispose(): void { this.clearTimer(); this.listeners.clear(); }

  private startTimer(): void {
    this.clearTimer();
    this.timer = setInterval(() => {
      if (this.index >= this.scenario.snapshots.length - 1) {
        this.clearTimer();
        return;
      }
      this.advance();
    }, 1400);
  }

  private applySnapshot(): void {
    const snapshot = this.scenario.snapshots[this.index];
    if (!snapshot) throw new Error("Test senaryosu anlık görüntüsü bulunamadı.");
    const durationSeconds = this.session.durationSeconds ?? snapshot.durationSeconds;
    const scale = durationSeconds && snapshot.durationSeconds ? durationSeconds / snapshot.durationSeconds : 1;
    const currentSeconds = Math.min(snapshot.currentSeconds * scale, durationSeconds ?? Number.POSITIVE_INFINITY);
    const scaleEvent = (event: OperatorSession["events"][number]) => {
      const timeSeconds = event.timeSeconds * scale;
      return {
        ...event,
        timeSeconds,
        timeLabel: `${String(Math.floor(timeSeconds / 60)).padStart(2, "0")}:${String(Math.floor(timeSeconds % 60)).padStart(2, "0")}`,
        startSeconds: event.startSeconds === undefined ? undefined : event.startSeconds * scale,
        endSeconds: event.endSeconds === undefined ? undefined : event.endSeconds * scale,
      };
    };
    const events = snapshot.events.map(scaleEvent);
    this.session = {
      ...cloneSession(snapshot),
      sourceName: this.session.sourceName,
      durationSeconds,
      currentSeconds,
      progress: durationSeconds ? currentSeconds / durationSeconds : snapshot.progress,
      events,
      finalOutput: { ...cloneSession(snapshot).finalOutput, events: snapshot.finalOutput.events.map(scaleEvent) },
    };
  }

  private setStatus(status: SessionStatus, clearTimer: boolean): OperatorSession {
    if (clearTimer) this.clearTimer();
    this.session = { ...this.session, status };
    return this.publish();
  }

  private publish(): OperatorSession {
    const session = cloneSession(this.session);
    this.listeners.forEach((listener) => listener(cloneSession(session)));
    return session;
  }

  private clearTimer(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
  }
}
