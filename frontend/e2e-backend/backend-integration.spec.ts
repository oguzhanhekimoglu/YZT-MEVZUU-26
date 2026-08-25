import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";

const target = {
  id: 4,
  sinif: "aircraft",
  guven: 0.91,
  hits: 12,
  model: "F-16 Fighting Falcon",
  model_skor: 0.88,
  ulke: "ABD",
  uretici: "Lockheed Martin",
  rol: "Çok rollü savaş uçağı",
  adaylar: [{ model: "F-16 Fighting Falcon", skor: 0.88 }],
  vlm: { gercek_tahmin: "F-16", arac_sinifi: "Sabit kanat", tehdit_seviyesi: "yüksek", dogrulama: "onaylandı" },
  llm: { summary: "Yakın takip gerekli", risk: "orta", actions: ["Takibi sürdür"] },
};

async function mockBackend(page: Page, onSocket?: (socket: WebSocketRoute) => void) {
  await page.route("**/durum", (route) => route.fulfill({ json: { calisiyor: true, kaynak: "C:\\gorev\\backend.mp4", frame_no: 42, hedef_sayisi: 1 } }));
  await page.route("**/video?**", (route) => route.abort("failed"));
  await page.routeWebSocket("**/hedefler", (socket) => {
    onSocket?.(socket);
    socket.send(JSON.stringify({ frame: 43, hedefler: [target] }));
  });
}

test("backend status, canlı hedef ve dürüst eksik özellikler", async ({ page }) => {
  await mockBackend(page);
  await page.goto("./");

  await expect(page.getByText("backend.mp4", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "F-16 Fighting Falcon" })).toBeVisible();
  await expect(page.getByText(/Son veri \d{2}:\d{2}:\d{2}/)).toBeVisible();
  await expect(page.getByText("Zaman damgalı olaylar mevcut backend sürümünde henüz sağlanmıyor.")).toBeVisible();
  await expect(page.getByText("Video geneli nihai analiz mevcut backend sürümünde henüz sağlanmıyor.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Duraklat" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Başa Al" })).toHaveCount(0);
});

test("stop komutunu doğru endpointe POST eder", async ({ page }) => {
  let stopMethod = "";
  let running = true;
  await page.route("**/durum", (route) => route.fulfill({ json: { calisiyor: running, kaynak: "backend.mp4", frame_no: 42 } }));
  await page.route("**/video?**", (route) => route.abort("failed"));
  await page.routeWebSocket("**/hedefler", (socket) => socket.send(JSON.stringify({ frame: 43, hedefler: [target] })));
  await page.route("**/oturum/durdur", async (route) => { stopMethod = route.request().method(); running = false; await route.fulfill({ json: { ok: true } }); });
  await page.goto("./");
  await page.getByRole("button", { name: "Durdur" }).click();
  await expect.poll(() => stopMethod).toBe("POST");
  await expect(page.getByRole("main")).toContainText("Durduruldu");
});

test("bozuk WebSocket payloadını yoksayar ve yeniden bağlanır", async ({ page }) => {
  let connections = 0;
  await page.route("**/durum", (route) => route.fulfill({ json: { calisiyor: true, kaynak: "backend.mp4", frame_no: 2 } }));
  await page.route("**/video?**", (route) => route.abort("failed"));
  await page.routeWebSocket("**/hedefler", (socket) => {
    connections += 1;
    if (connections === 1) {
      socket.send("bozuk-json");
      setTimeout(() => void socket.close({ code: 1011, reason: "test" }), 50);
      return;
    }
    socket.send(JSON.stringify({ frame: 9, hedefler: [target] }));
  });
  await page.goto("./");
  await expect.poll(() => connections).toBeGreaterThanOrEqual(2);
  await expect(page.getByRole("heading", { name: "F-16 Fighting Falcon" })).toBeVisible({ timeout: 5_000 });
});

test("MJPEG hatasını görünür kılar ve retry sunar", async ({ page }) => {
  await mockBackend(page);
  await page.goto("./");
  await page.waitForFunction(() => document.querySelector('[role="alert"]') || document.querySelector('img[alt$="canlı analiz görüntüsü"]'));
  await page.evaluate(() => document.querySelector('img[alt$="canlı analiz görüntüsü"]')?.dispatchEvent(new Event("error")));
  await expect(page.getByRole("alert")).toContainText("Canlı görüntü alınamadı");
  await expect(page.getByRole("button", { name: "Yeniden Dene" })).toBeVisible();
});
