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
  // BUG-FIX (yeni özellik — sürükle-bırak video yükleme): postJson her zaman
  // content-type: application/json + JSON.stringify kullanıyor, bir dosyanın
  // ham baytlarını (multipart/form-data) göndermeye uygun değil - ayrı bir
  // metod olarak eklendi.
  postFile(url: string, file: File, fieldName?: string, signal?: AbortSignal, timeoutMs?: number): Promise<unknown>;
  createSocket(url: string): SocketLike;
}

export class NativeBackendTransport implements BackendTransport {
  constructor(private readonly timeoutMs = 8_000) {}

  getJson(url: string, signal?: AbortSignal, timeoutMs?: number): Promise<unknown> { return this.request(url, { method: "GET", signal }, timeoutMs); }
  postJson(url: string, body?: unknown, signal?: AbortSignal, timeoutMs?: number): Promise<unknown> {
    return this.request(url, { method: "POST", headers: { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body), signal }, timeoutMs);
  }
  postFile(url: string, file: File, fieldName = "dosya", signal?: AbortSignal, timeoutMs?: number): Promise<unknown> {
    const form = new FormData();
    form.append(fieldName, file);
    // content-type kasıtlı olarak BELİRTİLMİYOR - tarayıcı FormData body için
    // kendi multipart/form-data; boundary=... başlığını otomatik ekler.
    return this.request(url, { method: "POST", body: form, signal }, timeoutMs);
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
