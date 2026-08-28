import { DataSourceError } from "./data-source-error";

export interface SocketLike {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  close(code?: number, reason?: string): void;
}

export interface BackendTransport {
  // timeoutMs: cagiran taraf, bu istek icin varsayilan (8sn) yerine daha
  // uzun bir zaman asimi istiyorsa gecebilir - ör. video-geneli özet gibi
  // uzun suren LLM sentezleri icin (bkz. existing-backend-adapter.ts).
  getJson(url: string, signal?: AbortSignal, timeoutMs?: number): Promise<unknown>;
  postJson(url: string, body?: unknown, signal?: AbortSignal, timeoutMs?: number): Promise<unknown>;
  createSocket(url: string): SocketLike;
}

export class NativeBackendTransport implements BackendTransport {
  constructor(private readonly timeoutMs = 8_000) {}

  getJson(url: string, signal?: AbortSignal, timeoutMs?: number): Promise<unknown> { return this.request(url, { method: "GET", signal }, timeoutMs); }
  postJson(url: string, body?: unknown, signal?: AbortSignal, timeoutMs?: number): Promise<unknown> {
    return this.request(url, { method: "POST", headers: { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body), signal }, timeoutMs);
  }
  createSocket(url: string): SocketLike { return new WebSocket(url); }

  private async request(url: string, init: RequestInit, timeoutMs?: number): Promise<unknown> {
    const timeout = AbortSignal.timeout(timeoutMs ?? this.timeoutMs);
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
