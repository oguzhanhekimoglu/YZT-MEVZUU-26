import type { BackendTransport, SocketLike } from "./backend-transport";
import { ExistingBackendAdapter } from "./existing-backend-adapter";
import { DataSourceError } from "./data-source-error";

class FakeSocket implements SocketLike {
  onopen: ((event: Event) => void) | null = null; onmessage: ((event: MessageEvent) => void) | null = null; onclose: ((event: CloseEvent) => void) | null = null; onerror: ((event: Event) => void) | null = null;
  closed = false; close() { this.closed = true; }
  open() { this.onopen?.(new Event("open")); }
  message(data: unknown) { this.onmessage?.(new MessageEvent("message", { data: typeof data === "string" ? data : JSON.stringify(data) })); }
  drop() { this.onclose?.(new CloseEvent("close")); }
}

class FakeTransport implements BackendTransport {
  gets: string[] = []; posts: string[] = []; postBodies: unknown[] = []; sockets: FakeSocket[] = [];
  status: unknown = { calisiyor: true, kaynak: "C:\\secret\\gorev.mp4", frame_no: 5 };
  videos: unknown = { videolar: [] };
  getJson(url: string) { this.gets.push(url); return Promise.resolve(url.endsWith("/videolar") ? this.videos : this.status); }
  postJson(url: string, body?: unknown) { this.posts.push(url); this.postBodies.push(body); return Promise.resolve({ ok: true }); }
  createSocket() { const socket = new FakeSocket(); this.sockets.push(socket); return socket; }
}

const target = { id: 4, sinif: "aircraft", guven: .9, model: "F-16", model_skor: .8, vlm: { tehdit_seviyesi: "yüksek" }, llm: { risk: "orta", summary: "Hedef özeti" } };

describe("ExistingBackendAdapter", () => {
  beforeEach(() => vi.useFakeTimers()); afterEach(() => vi.useRealTimers());
  function setup() { const transport = new FakeTransport(); const adapter = new ExistingBackendAdapter({ apiBaseUrl: "http://127.0.0.1:8000", wsBaseUrl: "ws://127.0.0.1:8000" }, { transport, pollIntervalMs: 1000, reconnectDelaysMs: [100, 200], now: () => 1_000 }); const snapshots: Awaited<ReturnType<typeof adapter.getSession>>[] = []; const unsubscribe = adapter.subscribe((session) => snapshots.push(session)); return { adapter, transport, snapshots, unsubscribe }; }

  it("doğru backend capability değerlerini sunar", () => { const { adapter } = setup(); expect(adapter.capabilities.start).toBe(true); expect(adapter.capabilities.stop).toBe(true); expect(adapter.capabilities.pause).toBe(false); adapter.dispose(); });
  it("subscribe ile hemen polling ve tek socket başlatır", async () => { const { adapter, transport } = setup(); await vi.runAllTicks(); expect(transport.gets[0]).toBe("http://127.0.0.1:8000/durum"); expect(transport.sockets).toHaveLength(1); adapter.subscribe(() => undefined); expect(transport.sockets).toHaveLength(1); adapter.dispose(); });
  it("status path bilgisini basename yapar ve MJPEG kök URL üretir", async () => { const { adapter } = setup(); await vi.runAllTicks(); const session = await adapter.getSession(); expect(session.sourceName).toBe("gorev.mp4"); expect(session.streamUrl).toBe("http://127.0.0.1:8000/video?_=1"); expect(session.streamUrl).not.toContain("goruntule"); adapter.dispose(); });
  it("socket durumunu ve geçerli hedef snapshotını yayınlar", async () => { const { adapter, transport } = setup(); transport.sockets[0]!.open(); expect((await adapter.getSession()).connection).toBe("connected"); transport.sockets[0]!.message({ frame: 12, hedefler: [target, { id: -1 }] }); const session = await adapter.getSession(); expect(session.targets.map((item) => item.id)).toEqual([4]); expect(session.frameNumber).toBe(12); expect(session.lastMessageAt).toBe("1970-01-01T00:00:01.000Z"); expect(session.events).toEqual([]); expect(session.finalOutput.status).toBe("pending"); adapter.dispose(); });
  it("bozuk mesajı atlar ve sonraki geçerli mesajı işler", async () => { const { adapter, transport } = setup(); transport.sockets[0]!.open(); transport.sockets[0]!.message("{bad"); expect((await adapter.getSession()).lastMessageAt).toBeUndefined(); transport.sockets[0]!.message({ frame: 9, hedefler: [target] }); expect((await adapter.getSession()).activeTargetCount).toBe(1); adapter.dispose(); });
  it("beklenmedik kapanmada hedefleri korur ve backoff ile reconnect eder", async () => { const { adapter, transport } = setup(); transport.sockets[0]!.open(); transport.sockets[0]!.message({ frame: 9, hedefler: [target] }); transport.sockets[0]!.drop(); expect((await adapter.getSession()).connection).toBe("reconnecting"); expect((await adapter.getSession()).targets).toHaveLength(1); await vi.advanceTimersByTimeAsync(99); expect(transport.sockets).toHaveLength(1); await vi.advanceTimersByTimeAsync(1); expect(transport.sockets).toHaveLength(2); adapter.dispose(); });
  it("dispose reconnect ve polling kaynaklarını temizler", async () => { const { adapter, transport } = setup(); transport.sockets[0]!.drop(); adapter.dispose(); await vi.advanceTimersByTimeAsync(5_000); expect(transport.sockets).toHaveLength(1); expect(transport.gets).toHaveLength(1); });
  it("manuel seçimi yeni hedefte korur ve kaybolunca risk fallback uygular", async () => { const { adapter, transport } = setup(); transport.sockets[0]!.open(); transport.sockets[0]!.message({ frame: 1, hedefler: [target, { ...target, id: 7, llm: { risk: "kritik" } }] }); await adapter.selectTarget(4); transport.sockets[0]!.message({ frame: 2, hedefler: [target, { ...target, id: 7, llm: { risk: "kritik" } }] }); expect((await adapter.getSession()).selectedTargetId).toBe(4); transport.sockets[0]!.message({ frame: 3, hedefler: [{ ...target, id: 7, llm: { risk: "kritik" } }] }); expect((await adapter.getSession()).selectedTargetId).toBe(7); adapter.dispose(); });
  it("eski status frame değeriyle socket frame değerini geriletmez", async () => { const { adapter, transport } = setup(); transport.sockets[0]!.message({ frame: 50, hedefler: [target] }); transport.status = { calisiyor: true, frame_no: 2 }; await vi.advanceTimersByTimeAsync(1000); expect((await adapter.getSession()).frameNumber).toBe(50); adapter.dispose(); });
  it("stop endpointini çağırır ve hedefleri korur", async () => { const { adapter, transport } = setup(); transport.sockets[0]!.message({ frame: 1, hedefler: [target] }); await adapter.stop(); const session = await adapter.getSession(); expect(transport.posts).toEqual(["http://127.0.0.1:8000/oturum/durdur"]); expect(session.status).toBe("stopped"); expect(session.targets).toHaveLength(1); adapter.dispose(); });
  it("unsupported komutlarda endpoint çağırmaz", async () => { const { adapter, transport } = setup(); await expect(adapter.pause()).rejects.toMatchObject({ code: "UNSUPPORTED" } satisfies Partial<DataSourceError>); await expect(adapter.restart()).rejects.toMatchObject({ code: "UNSUPPORTED" }); expect(transport.posts).toEqual([]); adapter.dispose(); });
  it("browser dosyası seçilince start endpointine ad veya yol göndermez", async () => { const { adapter, transport } = setup(); await adapter.selectVideo({ name: "yerel.mp4" }); expect((await adapter.getSession()).sourceName).toMatch(/yerel\.mp4|gorev\.mp4/); expect(transport.posts).toEqual([]); adapter.dispose(); });
  it("sunucu yolu girilmeden start çağrılırsa endpoint çağırmadan reddeder", async () => { const { adapter, transport } = setup(); await adapter.selectVideo({ name: "yerel.mp4" }); await expect(adapter.start()).rejects.toMatchObject({ code: "UNSUPPORTED" } satisfies Partial<DataSourceError>); expect(transport.posts).toEqual([]); adapter.dispose(); });
  it("sunucu yolu ile start çağrılırsa /oturum/baslat'a doğru gövdeyi POST eder", async () => {
    const { adapter, transport } = setup();
    await adapter.selectVideo({ name: "video.mp4", serverPath: "C:\\videos\\video.mp4" });
    await adapter.start();
    expect(transport.posts).toEqual(["http://127.0.0.1:8000/oturum/baslat"]);
    expect(transport.postBodies).toEqual([{ video_yolu: "C:\\videos\\video.mp4" }]);
    adapter.dispose();
  });
  it("video-özeti iki denemede de başarısız olursa görünür bir hata durumu yayınlar (sessizce pending kalmaz)", async () => {
    const { adapter, transport } = setup();
    transport.sockets[0]!.message({ frame: 1, hedefler: [target] });
    transport.getJson = (url: string) => (url.endsWith("/video/ozet") ? Promise.reject(new Error("network")) : Promise.resolve(transport.status));
    await adapter.stop();
    expect((await adapter.getSession()).finalOutput.status).toBe("pending");
    await vi.advanceTimersByTimeAsync(3_000);
    const session = await adapter.getSession();
    expect(session.finalOutput.status).toBe("partial");
    expect(session.finalOutput.summary).toContain("Video geneli özet alınamadı");
    adapter.dispose();
  });

  it("listServerVideos /videolar'ı çağırıp parse eder, hatada boş dizi döner", async () => {
    const { adapter, transport } = setup();
    transport.videos = { videolar: [{ ad: "f15.mp4", yol: "/data/videos/f15.mp4" }] };
    expect(await adapter.listServerVideos()).toEqual([{ name: "f15.mp4", path: "/data/videos/f15.mp4" }]);
    transport.getJson = () => Promise.reject(new Error("network"));
    expect(await adapter.listServerVideos()).toEqual([]);
    adapter.dispose();
  });
});
