import type { OperatorSession, RiskLevel, TargetAnalysis } from "../types";
import type { BackendAdapterConfig, OperatorDataSource, OperatorSessionListener, SelectedVideo, ServerVideoOption, Unsubscribe } from "./contracts";
import { existingBackendCapabilities } from "./capabilities";
import { NativeBackendTransport, type BackendTransport, type SocketLike } from "./backend-transport";
import { parseBackendStatus, parseBackendTargets, parseServerVideos, parseTargetsEnvelope } from "./backend-parser";
import { resolveApiUrl, resolveWebSocketUrl, safeBasename } from "./backend-url";
import { DataSourceError, unsupported } from "./data-source-error";

export interface ExistingBackendAdapterOptions {
  transport?: BackendTransport;
  pollIntervalMs?: number;
  reconnectDelaysMs?: number[];
  now?: () => number;
}

const pendingFinal = { status: "pending" as const, summary: "Video geneli nihai analiz mevcut backend sürümünde henüz sağlanmıyor.", events: [], risk: "unknown" as const, actions: [] };
const riskOrder: Record<RiskLevel, number> = { critical: 5, high: 4, medium: 3, low: 2, info: 1, unknown: 0 };

function initialSession(localMode: boolean): OperatorSession {
  return { id: "backend-generation-1", status: "idle", connection: "connecting", localMode, currentSeconds: 0, frameNumber: 0, activeTargetCount: 0, criticalEventCount: 0, targets: [], events: [], finalOutput: pendingFinal };
}

function isLocalBackend(base: string): boolean {
  if (!base) return true;
  try { const host = new URL(base).hostname; return host === "127.0.0.1" || host === "localhost" || host === globalThis.location?.hostname; }
  catch { return false; }
}

function preferredTarget(targets: TargetAnalysis[]): number | undefined {
  return [...targets].sort((a, b) => riskOrder[b.risk] - riskOrder[a.risk] || a.id - b.id)[0]?.id;
}

export class ExistingBackendAdapter implements OperatorDataSource {
  readonly capabilities = existingBackendCapabilities;
  private readonly transport: BackendTransport;
  private readonly pollIntervalMs: number;
  private readonly reconnectDelaysMs: number[];
  private readonly now: () => number;
  private readonly listeners = new Set<OperatorSessionListener>();
  private session: OperatorSession;
  private pollTimer?: ReturnType<typeof setTimeout>;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private pollController?: AbortController;
  private socket?: SocketLike;
  private socketGeneration = 0;
  private reconnectAttempt = 0;
  private generation = 1;
  private streamToken = 1;
  private polling = false;
  private disposed = false;
  private stopping = false;
  private pendingServerPath?: string;

  constructor(private readonly config: BackendAdapterConfig, options: ExistingBackendAdapterOptions = {}) {
    this.transport = options.transport ?? new NativeBackendTransport();
    this.pollIntervalMs = options.pollIntervalMs ?? 1_500;
    this.reconnectDelaysMs = options.reconnectDelaysMs ?? [1_000, 2_000, 4_000, 8_000, 12_000];
    this.now = options.now ?? Date.now;
    this.session = initialSession(isLocalBackend(config.apiBaseUrl));
  }

  getSession(): Promise<OperatorSession> { return Promise.resolve(structuredClone(this.session)); }

  subscribe(listener: OperatorSessionListener): Unsubscribe {
    if (this.disposed) return () => undefined;
    this.listeners.add(listener); listener(structuredClone(this.session));
    if (this.listeners.size === 1) this.startResources();
    return () => { this.listeners.delete(listener); if (this.listeners.size === 0) this.stopResources(); };
  }

  selectVideo(video: SelectedVideo): Promise<OperatorSession> {
    this.pendingServerPath = video.serverPath;
    this.session = { ...this.session, status: "file-selected", sourceName: video.name, durationSeconds: video.durationSeconds };
    return Promise.resolve(this.publish());
  }

  async listServerVideos(): Promise<ServerVideoOption[]> {
    try {
      return parseServerVideos(await this.transport.getJson(resolveApiUrl(this.config.apiBaseUrl, "/videolar")));
    } catch {
      return [];
    }
  }

  async start(): Promise<OperatorSession> {
    const path = this.pendingServerPath;
    if (!path) throw new DataSourceError("UNSUPPORTED", "Analizi başlatmak için önce sunucudaki video dosya yolunu girin.", false);
    this.session = { ...this.session, status: "preparing" };
    this.publish();
    try {
      await this.transport.postJson(resolveApiUrl(this.config.apiBaseUrl, "/oturum/baslat"), { video_yolu: path });
      return this.getSession();
    } catch (error) {
      this.session = { ...this.session, status: "file-selected" };
      this.publish();
      throw error;
    }
  }
  pause(): Promise<OperatorSession> { return Promise.reject(unsupported("Duraklatma")); }
  resume(): Promise<OperatorSession> { return Promise.reject(unsupported("Devam ettirme")); }
  restart(): Promise<OperatorSession> { return Promise.reject(unsupported("Başa alma")); }

  async stop(): Promise<OperatorSession> {
    if (this.stopping) throw new DataSourceError("UNSUPPORTED", "Durdurma isteği zaten işleniyor.", true);
    this.stopping = true;
    try {
      await this.transport.postJson(resolveApiUrl(this.config.apiBaseUrl, "/oturum/durdur"));
      this.session = { ...this.session, status: "stopped" };
      return this.publish();
    } finally { this.stopping = false; }
  }

  selectTarget(targetId: number): Promise<OperatorSession> {
    if (targetId === -1 || !this.session.targets.some((target) => target.id === targetId)) return this.getSession();
    this.session = { ...this.session, selectedTargetId: targetId, targets: this.session.targets.map((target) => ({ ...target, selected: target.id === targetId })) };
    return Promise.resolve(this.publish());
  }

  dispose(): void { this.disposed = true; this.listeners.clear(); this.stopResources(); }

  private startResources() { this.disposed = false; void this.pollStatus(); this.connectSocket(); }
  private stopResources() {
    if (this.pollTimer) clearTimeout(this.pollTimer); if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.pollTimer = undefined; this.reconnectTimer = undefined; this.pollController?.abort(); this.pollController = undefined;
    this.socketGeneration += 1; const socket = this.socket; this.socket = undefined; socket?.close(1000, "cleanup");
  }

  private async pollStatus() {
    if (this.polling || this.disposed || this.listeners.size === 0) return;
    this.polling = true; const controller = new AbortController(); this.pollController = controller;
    try {
      const payload = parseBackendStatus(await this.transport.getJson(resolveApiUrl(this.config.apiBaseUrl, "/durum"), controller.signal));
      const sourceName = safeBasename(payload.kaynak); const sourceChanged = Boolean(sourceName && this.session.sourceName && sourceName !== this.session.sourceName);
      if (sourceChanged) { this.generation += 1; this.streamToken += 1; }
      const running = payload.calisiyor === true;
      this.session = {
        ...this.session, id: `backend-generation-${this.generation}`, sourceName: sourceName ?? this.session.sourceName,
        status: running ? "running" : this.session.status === "running" ? "stopped" : this.session.status,
        frameNumber: Math.max(this.session.frameNumber, payload.frame_no ?? 0),
        currentSeconds: payload.gecen_saniye ?? this.session.currentSeconds,
        durationSeconds: payload.sure_saniye ?? this.session.durationSeconds,
        streamUrl: running ? `${resolveApiUrl(this.config.apiBaseUrl, "/video")}?_=${this.streamToken}` : this.session.streamUrl,
        events: [], finalOutput: pendingFinal,
        ...(sourceChanged ? { targets: [], selectedTargetId: undefined, activeTargetCount: 0 } : {}),
      };
      this.publish();
    } catch {
      if (!controller.signal.aborted && this.session.connection !== "connected") { this.session = { ...this.session, connection: "disconnected" }; this.publish(); }
    } finally {
      this.polling = false; if (this.pollController === controller) this.pollController = undefined;
      if (!this.disposed && this.listeners.size) this.pollTimer = setTimeout(() => void this.pollStatus(), this.pollIntervalMs);
    }
  }

  private connectSocket() {
    if (this.disposed || this.listeners.size === 0 || this.socket) return;
    const generation = ++this.socketGeneration;
    this.session = { ...this.session, connection: this.reconnectAttempt ? "reconnecting" : "connecting" }; this.publish();
    const socket = this.transport.createSocket(resolveWebSocketUrl(this.config.wsBaseUrl, "/hedefler")); this.socket = socket;
    socket.onopen = () => { if (!this.isCurrentSocket(socket, generation)) return; this.reconnectAttempt = 0; this.session = { ...this.session, connection: "connected" }; this.publish(); };
    socket.onmessage = (event) => {
      if (!this.isCurrentSocket(socket, generation) || typeof event.data !== "string" || event.data.length > 2_000_000) return;
      let raw: unknown; try { raw = JSON.parse(event.data); } catch { return; }
      const envelope = parseTargetsEnvelope(raw); if (!envelope) return;
      const targets = parseBackendTargets(envelope.hedefler, this.config.apiBaseUrl);
      const selectedId = this.session.selectedTargetId && targets.some((target) => target.id === this.session.selectedTargetId) ? this.session.selectedTargetId : preferredTarget(targets);
      this.session = { ...this.session, frameNumber: Math.max(this.session.frameNumber, envelope.frame ?? 0), targets: targets.map((target) => ({ ...target, selected: target.id === selectedId })), selectedTargetId: selectedId, activeTargetCount: targets.length, lastMessageAt: new Date(this.now()).toISOString(), events: [], finalOutput: pendingFinal };
      this.publish();
    };
    socket.onclose = () => { if (!this.isCurrentSocket(socket, generation)) return; this.socket = undefined; if (this.disposed || this.listeners.size === 0) return; this.session = { ...this.session, connection: "reconnecting" }; this.publish(); this.scheduleReconnect(); };
    socket.onerror = () => undefined;
  }

  private scheduleReconnect() {
    if (this.reconnectTimer || this.disposed || this.listeners.size === 0) return;
    const delay = this.reconnectDelaysMs[Math.min(this.reconnectAttempt, this.reconnectDelaysMs.length - 1)] ?? 12_000;
    this.reconnectAttempt += 1; this.reconnectTimer = setTimeout(() => { this.reconnectTimer = undefined; this.connectSocket(); }, delay);
  }
  private isCurrentSocket(socket: SocketLike, generation: number) { return this.socket === socket && this.socketGeneration === generation; }
  private publish(): OperatorSession { const snapshot = structuredClone(this.session); this.listeners.forEach((listener) => listener(structuredClone(snapshot))); return snapshot; }
}
