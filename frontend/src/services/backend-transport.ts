import { DataSourceError } from "./data-source-error";

export interface SocketLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  close(code?: number, reason?: string): void;
}

export interface BackendTransport {
  getJson(url: string, signal?: AbortSignal): Promise<unknown>;
  postJson(url: string, body?: unknown, signal?: AbortSignal): Promise<unknown>;
  createSocket(url: string): SocketLike;
}

export class NativeBackendTransport implements BackendTransport {
  constructor(private readonly timeoutMs = 8_000) {}

  getJson(url: string, signal?: AbortSignal): Promise<unknown> { return this.request(url, { method: "GET", signal }); }
  postJson(url: string, body?: unknown, signal?: AbortSignal): Promise<unknown> {
    return this.request(url, { method: "POST", headers: { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body), signal });
  }
  createSocket(url: string): SocketLike { return new WebSocket(url); }

  private async request(url: string, init: RequestInit): Promise<unknown> {
    const timeout = AbortSignal.timeout(this.timeoutMs);
    const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
    try {
      const response = await fetch(url, { ...init, signal });
      if (!response.ok) throw new DataSourceError("HTTP_ERROR", "Backend isteği tamamlanamadı.", response.status >= 500, response.status);
      try { return await response.json(); }
      catch { throw new DataSourceError("INVALID_RESPONSE", "Backend geçerli JSON döndürmedi.", true); }
    } catch (error) {
      if (error instanceof DataSourceError) throw error;
      if (signal.aborted) throw new DataSourceError("TIMEOUT", "Backend yanıtı zaman aşımına uğradı.", true);
      throw new DataSourceError("CONNECTION_ERROR", "Backend bağlantısı kurulamadı.", true);
    }
  }
}
