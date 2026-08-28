import { render, screen } from "@testing-library/react";
import { completedSessionFixture, runningSessionFixture } from "../../test/fixtures";
import { existingBackendCapabilities } from "../../services/capabilities";
import { testCapabilities } from "../../test/test-data-source";
import { SessionControls } from "./SessionControls";

const handlers = { onStart: vi.fn(), onPause: vi.fn(), onResume: vi.fn(), onStop: vi.fn(), onRestart: vi.fn(), onChangeVideo: vi.fn() };

describe("SessionControls capabilities", () => {
  it("tüm kontroller etkinken mevcut kontrolleri etkin tutar", () => {
    render(<SessionControls session={runningSessionFixture} capabilities={testCapabilities} {...handlers} />);
    expect(screen.getByRole("button", { name: "Duraklat" })).toBeEnabled(); expect(screen.getByRole("button", { name: "Durdur" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Analizi Başlat" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Devam Et" })).not.toBeInTheDocument();
  });
  it("tamamlanan yerel önizlemede video bitince baştan başlat eylemini gösterir ve durdur butonunu gizler", () => {
    render(<SessionControls session={completedSessionFixture} capabilities={testCapabilities} videoEnded {...handlers} />);
    expect(screen.queryByRole("button", { name: "Durdur" })).not.toBeInTheDocument(); expect(screen.getByRole("button", { name: "Baştan Başlat" })).toBeEnabled();
  });
  it("backend modunda desteklenmeyen komutları göstermez", () => {
    render(<SessionControls session={completedSessionFixture} capabilities={existingBackendCapabilities} {...handlers} />);
    expect(screen.queryByRole("button", { name: "Baştan Başlat" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Video Seç" })).not.toBeInTheDocument();
  });
  it("backend çalışan oturumunda stop ve fullscreen destekler", () => {
    render(<SessionControls session={runningSessionFixture} capabilities={existingBackendCapabilities} {...handlers} />);
    expect(screen.getByRole("button", { name: "Durdur" })).toBeEnabled(); expect(screen.queryByRole("button", { name: "Tam Ekran" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Duraklat" })).not.toBeInTheDocument();
  });
  it("videoUpload destekleyen backend'de durdurulmuş videoda Video Değiştir'i gösterir (yeni video yükleme/kamera özelliği)", () => {
    render(<SessionControls session={{ ...runningSessionFixture, status: "stopped", sourceName: "f15.mp4" }} capabilities={existingBackendCapabilities} {...handlers} />);
    expect(screen.getByRole("button", { name: /Video Değiştir/ })).toBeInTheDocument();
  });
  it("videoUpload desteklemeyen backend'de Video Değiştir'i gizler", () => {
    render(<SessionControls session={{ ...runningSessionFixture, status: "stopped", sourceName: "f15.mp4" }} capabilities={{ ...existingBackendCapabilities, videoUpload: false }} {...handlers} />);
    expect(screen.queryByRole("button", { name: /Video Değiştir/ })).not.toBeInTheDocument();
  });
  it("durdurulan yerel videoda baştan başlat eylemini gösterir", () => {
    render(<SessionControls session={{ ...runningSessionFixture, status: "stopped" }} capabilities={testCapabilities} {...handlers} />);
    expect(screen.getByRole("button", { name: "Baştan Başlat" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Devam Et" })).not.toBeInTheDocument();
  });
});
