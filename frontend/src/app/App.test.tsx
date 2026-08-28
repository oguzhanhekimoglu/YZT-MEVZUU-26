import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AppProviders } from "./providers";
import { TestOperatorDataSource } from "../test/test-data-source";
import { App } from "./App";

function renderApp(dataSource = new TestOperatorDataSource()) {
  return { dataSource, ...render(<AppProviders dataSource={dataSource}><App /></AppProviders>) };
}

describe("App", () => {
  it("ürün adını, alt başlığı ve video yer tutucusunu gösterir", () => {
    renderApp();
    expect(screen.getByRole("heading", { level: 1, name: "MEVZUU" })).toBeInTheDocument();
    expect(screen.getByText("Hava Sahası Karar Destek Sistemi")).toBeInTheDocument();
    expect(screen.getByText("Video bekleniyor")).toBeInTheDocument();
  });

  it("geçerli video seçilince metadata ve başlat butonunu gösterir", async () => {
    const { dataSource } = renderApp();
    await act(async () => { await dataSource.selectVideo({ name: "gorev.mp4" }); });
    await waitFor(() => expect(screen.getByRole("button", { name: "Analizi Başlat" })).toBeEnabled());
    expect(screen.getByRole("button", { name: /Analizi Başlat/ })).toBeEnabled();
  });

  it("oturum durumuna göre kontrolleri etkinleştirir", async () => {
    const { dataSource } = renderApp();
    expect(screen.queryByRole("button", { name: "Analizi Başlat" })).not.toBeInTheDocument();
    await act(async () => { await dataSource.selectVideo({ name: "gorev.mp4" }); });
    await waitFor(() => expect(screen.getByRole("button", { name: "Analizi Başlat" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Analizi Başlat" }));
    act(() => dataSource.advance());
    await waitFor(() => expect(screen.getByRole("button", { name: /Duraklat/ })).toBeEnabled());
    expect(screen.getByRole("button", { name: /Durdur/ })).toBeEnabled();
  });

  it("Baştan Başlat onay modalını açar", async () => {
    const { dataSource } = renderApp();
    await act(async () => { await dataSource.selectVideo({ name: "gorev.mp4" }); });
    fireEvent.click(await screen.findByRole("button", { name: "Analizi Başlat" }));
    // Video bitince gerçek backend'de durum "stopped" olur (bkz.
    // existing-backend-adapter.ts pollStatus) - eskiden burada yerel <video>
    // elementinin "ended" olayı simüle ediliyordu, o mekanizma sürükle-bırak/
    // yerel önizleme kaldırılınca tamamen kalktı.
    await act(async () => { await dataSource.stop(); });
    await waitFor(() => expect(screen.getByRole("button", { name: /Baştan Başlat/ })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /Baştan Başlat/ }));
    expect(screen.getByRole("alertdialog", { name: "Analizi baştan başlat" })).toBeInTheDocument();
  });

  it("seçili hedef değişince kimlik panelini günceller ve id -1 hedefini gizler", async () => {
    const { dataSource } = renderApp();
    await act(async () => { await dataSource.selectVideo({ name: "gorev.mp4" }); await dataSource.start(); dataSource.advance(); });
    expect(await screen.findByRole("heading", { name: "F-16 Fighting Falcon" })).toBeInTheDocument();
    expect(screen.queryByText(/Hedef #-1/)).not.toBeInTheDocument();
    await act(async () => { await dataSource.selectTarget(7); });
    expect(await screen.findByRole("heading", { name: "Bilinmeyen hava aracı" })).toBeInTheDocument();
  });

  it("timeline olayı seçilince ayrıntıyı gösterir", async () => {
    const { dataSource } = renderApp();
    await act(async () => { await dataSource.selectVideo({ name: "gorev.mp4" }); await dataSource.start(); dataSource.advance(); });
    fireEvent.click(await screen.findByRole("button", { name: /00:18, Hedef ilk kez görüldü, Bilgi, Hedef #4/ }));
    expect(screen.getByText("Hedef #4 görüntü alanında tespit edildi.")).toBeInTheDocument();
  });

  it("yasaklı yön terminolojisini render etmez", async () => {
    const { dataSource } = renderApp();
    await act(async () => { await dataSource.selectVideo({ name: "gorev.mp4" }); await dataSource.start(); dataSource.advance(); });
    expect(document.body.textContent).not.toMatch(/gidiş yönü/i);
  });

  it("video seçildikten sonra video seçiciyi (Video Değiştir) erişilebilir tutar", async () => {
    const { dataSource } = renderApp();
    await act(async () => { await dataSource.selectVideo({ name: "gorev.mp4" }); });
    await waitFor(() => expect(screen.getByRole("button", { name: "Analizi Başlat" })).toBeEnabled());
    expect(screen.getByRole("button", { name: /Video Değiştir/ })).toBeEnabled();
  });
});
