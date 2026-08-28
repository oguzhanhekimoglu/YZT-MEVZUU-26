import type { OperatorSession } from "../types";
import type {
  BackendAdapterConfig,
  OperatorDataSource,
  OperatorSessionListener,
  SelectedVideo,
  ServerVideoOption,
  Unsubscribe,
} from "./contracts";
import { existingBackendCapabilities } from "./capabilities";

export abstract class UnavailableBackendAdapter implements OperatorDataSource {
  readonly capabilities = existingBackendCapabilities;
  protected constructor(protected readonly config: BackendAdapterConfig) {}

  abstract readonly adapterName: string;

  getSession(): Promise<OperatorSession> {
    return this.unavailable();
  }

  selectVideo(_video: SelectedVideo): Promise<OperatorSession> { return this.unavailable(); }
  listServerVideos(): Promise<ServerVideoOption[]> { return Promise.resolve([]); }
  uploadVideo(_file: File): Promise<SelectedVideo> { return Promise.reject(new Error(`${this.adapterName} henüz etkin değil.`)); }
  startCamera(_index?: number): Promise<OperatorSession> { return this.unavailable(); }
  start(): Promise<OperatorSession> { return this.unavailable(); }
  pause(): Promise<OperatorSession> { return this.unavailable(); }
  resume(): Promise<OperatorSession> { return this.unavailable(); }
  stop(): Promise<OperatorSession> { return this.unavailable(); }
  restart(): Promise<OperatorSession> { return this.unavailable(); }
  selectTarget(_targetId: number): Promise<OperatorSession> { return this.unavailable(); }

  subscribe(_listener: OperatorSessionListener): Unsubscribe {
    return () => undefined;
  }

  dispose(): void {}

  private unavailable(): Promise<OperatorSession> {
    return Promise.reject(new Error(`${this.adapterName} henüz etkin değil.`));
  }
}
