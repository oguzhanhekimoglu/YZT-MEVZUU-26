import type { OperatorSession } from "../types";

export type OperatorSessionListener = (session: OperatorSession) => void;
export type Unsubscribe = () => void;

export interface SelectedVideo {
  name: string;
  durationSeconds?: number;
  /** Sunucudaki gerçek dosya yolu — tarayıcı gerçek yerel yolu veremediği için
   * sürükle-bırak/dosya seçiminden gelmez, ayrı bir yol girişinden gelir.
   * Mevcut backend'de oturum başlatmak (`POST /oturum/baslat`) için zorunludur. */
  serverPath?: string;
}

export interface ServerVideoOption {
  name: string;
  path: string;
}

export interface OperatorCapabilities {
  localFilePreview: boolean;
  videoUpload: boolean;
  serverPathStart: boolean;
  start: boolean;
  pause: boolean;
  resume: boolean;
  stop: boolean;
  restart: boolean;
  mjpegStream: boolean;
  liveTargets: boolean;
  persistentEvents: boolean;
  finalOutput: boolean;
  referenceImages: boolean;
  metrics: boolean;
  eventSnapshots: boolean;
  seekToEvent: boolean;
}

export interface OperatorDataSource {
  readonly capabilities: OperatorCapabilities;
  getSession(): Promise<OperatorSession>;
  subscribe(listener: OperatorSessionListener): Unsubscribe;
  selectVideo(video: SelectedVideo): Promise<OperatorSession>;
  /** Sunucudaki data/videos/ altında seçilebilir video listesi. Desteklenmeyen
   * adaptörlerde boş dizi döner (hata fırlatmaz). */
  listServerVideos(): Promise<ServerVideoOption[]>;
  start(): Promise<OperatorSession>;
  pause(): Promise<OperatorSession>;
  resume(): Promise<OperatorSession>;
  stop(): Promise<OperatorSession>;
  restart(): Promise<OperatorSession>;
  selectTarget(targetId: number): Promise<OperatorSession>;
  dispose(): void;
}

export interface BackendAdapterConfig {
  apiBaseUrl: string;
  wsBaseUrl: string;
}
