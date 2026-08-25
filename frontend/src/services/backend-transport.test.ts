import { DataSourceError } from "./data-source-error";
import { NativeBackendTransport } from "./backend-transport";

describe("NativeBackendTransport", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("GET JSON yanıtını döndürür", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } })));
    await expect(new NativeBackendTransport().getJson("/durum")).resolves.toEqual({ ok: true });
    expect(fetch).toHaveBeenCalledWith("/durum", expect.objectContaining({ method: "GET" }));
  });

  it("HTTP hatasını status ve recoverable bilgisiyle normalize eder", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("error", { status: 503 })));
    await expect(new NativeBackendTransport().getJson("/durum")).rejects.toMatchObject({ code: "HTTP_ERROR", status: 503, recoverable: true } satisfies Partial<DataSourceError>);
  });

  it("bozuk JSON yanıtını normalize eder", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not-json", { status: 200 })));
    await expect(new NativeBackendTransport().getJson("/durum")).rejects.toMatchObject({ code: "INVALID_RESPONSE", recoverable: true } satisfies Partial<DataSourceError>);
  });

  it("bağlantı hatasını normalize eder", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")));
    await expect(new NativeBackendTransport().getJson("/durum")).rejects.toMatchObject({ code: "CONNECTION_ERROR", recoverable: true } satisfies Partial<DataSourceError>);
  });

  it("timeout durumunu normalize eder", async () => {
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => new Promise((_resolve, reject) => init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))))));
    await expect(new NativeBackendTransport(1).getJson("/durum")).rejects.toMatchObject({ code: "TIMEOUT", recoverable: true } satisfies Partial<DataSourceError>);
  });

  it("POST gövdesini JSON olarak gönderir", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 200 })));
    await new NativeBackendTransport().postJson("/stop", { reason: "operator" });
    expect(fetch).toHaveBeenCalledWith("/stop", expect.objectContaining({ method: "POST", body: '{"reason":"operator"}', headers: { "content-type": "application/json" } }));
  });
});
