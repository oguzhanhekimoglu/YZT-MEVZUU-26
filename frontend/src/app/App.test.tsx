import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AppProviders } from "./providers";
import { TestOperatorDataSource } from "../test/test-data-source";
import { App } from "./App";

function renderApp(dataSource = new TestOperatorDataSource()) {
  return { dataSource, ...render(<AppProviders dataSource={dataSource}><App /></AppProviders>) };
}

beforeEach(() => {
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock-video");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
});

afterEach(() => vi.restoreAllMocks());

describe("App", () => {
  it("ürün adını, alt başlığı ve video dropzone alanını gösterir", () => {
    renderApp();
    expect(screen.getByRole("heading", { level: 1, name: "MEVZUU" })).toBeInTheDocument();
    expect(screen.getByText("Hava Sahası Karar Destek Sistemi")).toBeInTheDocument();
    expect(screen.getByText("Videoyu buraya sürükleyin")).toBeInTheDocument();
  });

  it("geçerli video seçilince metadata ve başlat butonunu gösterir", async () => {
    renderApp();
    const file = new File(["video"], "gorev.mp4", { type: "video/mp4" });
    fireEvent.change(document.getElementById("video-file-input")!, { target: { files: [file] } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Analizi Başlat" })).toBeEnabled());
    expect(screen.getByRole("button", { name: /Analizi Başlat/ })).toBeEnabled();
  });

  it("geçersiz dosya türü için Türkçe hata gösterir", () => {
    renderApp();
    fireEvent.change(document.getElementById("video-file-input")!, { target: { files: [new File(["x"], "not.txt", { type: "text/plain" })] } });
    expect(screen.getByRole("alert")).toHaveTextContent("Geçersiz dosya türü");
  });

  it("oturum durumuna göre kontrolleri etkinleştirir", async () => {
    const { dataSource } = renderApp();
    expect(screen.queryByRole("button", { name: "Analizi Başlat" })).not.toBeInTheDocument();
    fireEvent.change(document.getElementById("video-file-input")!, { target: { files: [new File(["x"], "gorev.mp4", { type: "video/mp4" })] } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Analizi Başlat" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Analizi Başlat" }));
    act(() => dataSource.advance());
    await waitFor(() => expect(screen.getByRole("button", { name: /Duraklat/ })).toBeEnabled());
    expect(screen.getByRole("button", { name: /Durdur/ })).toBeEnabled();
  });

  it("Baştan Başlat onay modalını açar", async () => {
    renderApp();
    fireEvent.change(document.getElementById("video-file-input")!, { target: { files: [new File(["x"], "gorev.mp4", { type: "video/mp4" })] } });
    fireEvent.click(await screen.findByRole("button", { name: "Analizi Başlat" }));
    fireEvent.ended(await screen.findByLabelText("gorev.mp4 yerel video önizlemesi"));
    fireEvent.click(await screen.findByRole("button", { name: /Baştan Başlat/ }));
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

  it("object URL bileşen kaldırıldığında temizlenir", async () => {
    const { unmount } = renderApp();
    fireEvent.change(document.getElementById("video-file-input")!, { target: { files: [new File(["x"], "gorev.mp4", { type: "video/mp4" })] } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Analizi Başlat" })).toBeEnabled());
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-video");
  });

  it("önizleme açıldıktan sonra video seçiciyi erişilebilir tutar", async () => {
    renderApp();
    const input = document.getElementById("video-file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "gorev.mp4", { type: "video/mp4" })] } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Analizi Başlat" })).toBeEnabled());
    expect(document.getElementById("video-file-input")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Video Değiştir/ })).toBeEnabled();
  });
});
