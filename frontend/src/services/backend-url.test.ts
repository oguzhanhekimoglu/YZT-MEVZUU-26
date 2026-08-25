import { normalizeBaseUrl, referenceImageUrl, resolveApiUrl, resolveWebSocketUrl, safeBasename } from "./backend-url";

describe("backend URL helpers", () => {
  it("API base URL ve slash değerlerini normalize eder", () => {
    expect(normalizeBaseUrl(" http://127.0.0.1:8000/// ")).toBe("http://127.0.0.1:8000");
    expect(resolveApiUrl("http://127.0.0.1:8000/", "/durum")).toBe("http://127.0.0.1:8000/durum");
  });
  it("aynı origin API yolunu kökten çözer ve goruntule prefix eklemez", () => {
    expect(resolveApiUrl("", "/durum", "http://localhost:4173/goruntule/")).toBe("http://localhost:4173/durum");
  });
  it("HTTP ve HTTPS için doğru socket protokolünü üretir", () => {
    expect(resolveWebSocketUrl("", "/hedefler", { protocol: "http:", host: "localhost:8000" } as Location)).toBe("ws://localhost:8000/hedefler");
    expect(resolveWebSocketUrl("", "/hedefler", { protocol: "https:", host: "example.test" } as Location)).toBe("wss://example.test/hedefler");
  });
  it("explicit websocket base değerini korur", () => { expect(resolveWebSocketUrl("ws://127.0.0.1:8000/", "hedefler")).toBe("ws://127.0.0.1:8000/hedefler"); });
  it("referans modelini encode eder", () => { expect(referenceImageUrl("http://localhost:8000", "F-16 Fighting Falcon")).toBe("http://localhost:8000/referans?model=F-16%20Fighting%20Falcon"); });
  it("Windows ve POSIX path değerlerinden yalnız basename döndürür", () => { expect(safeBasename("C:\\secret\\gorev.mp4")).toBe("gorev.mp4"); expect(safeBasename("/srv/video/test.mov")).toBe("test.mov"); });
});
