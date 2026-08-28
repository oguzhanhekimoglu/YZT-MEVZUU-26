import { fireEvent, render, screen } from "@testing-library/react";
import type { OperatorDataSource } from "../../services/contracts";
import { existingBackendCapabilities } from "../../services/capabilities";
import { testCapabilities } from "../../test/test-data-source";
import { VideoSourcePicker } from "./VideoSourcePicker";

function dataSource(overrides: Partial<OperatorDataSource> = {}): OperatorDataSource {
  return {
    capabilities: existingBackendCapabilities,
    getSession: vi.fn(),
    subscribe: vi.fn(() => () => undefined),
    selectVideo: vi.fn(),
    listServerVideos: vi.fn().mockResolvedValue([]),
    uploadVideo: vi.fn(),
    startCamera: vi.fn(),
    start: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    stop: vi.fn(),
    restart: vi.fn(),
    selectTarget: vi.fn(),
    dispose: vi.fn(),
    ...overrides,
  };
}

describe("VideoSourcePicker", () => {
  it("serverPathStart desteklemeyen backend'de hiçbir şey render etmez", () => {
    const { container } = render(<VideoSourcePicker dataSource={dataSource({ capabilities: testCapabilities })} />);
    expect(container).toBeEmptyDOMElement();
  });
  it("liste boşken uyarı gösterir, select render etmez", async () => {
    render(<VideoSourcePicker dataSource={dataSource({ listServerVideos: vi.fn().mockResolvedValue([]) })} />);
    expect(await screen.findByText("Sunucuda seçilebilir video bulunamadı")).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
  it("videoları listeler ve seçilince selectVideo'yu doğru serverPath ile çağırır", async () => {
    const selectVideo = vi.fn();
    render(<VideoSourcePicker dataSource={dataSource({ listServerVideos: vi.fn().mockResolvedValue([{ name: "f15.mp4", path: "/data/videos/f15.mp4" }]), selectVideo })} />);
    const select = await screen.findByRole("combobox", { name: "Sunucudaki mevcut videolardan seç" });
    fireEvent.change(select, { target: { value: "/data/videos/f15.mp4" } });
    expect(selectVideo).toHaveBeenCalledWith({ name: "f15.mp4", serverPath: "/data/videos/f15.mp4" });
  });
  it("dosya seçilince uploadVideo'yu çağırır", async () => {
    const uploadVideo = vi.fn().mockResolvedValue({ name: "f16.mp4", serverPath: "/data/videos/yuklenenler/f16.mp4" });
    const { container } = render(<VideoSourcePicker dataSource={dataSource({ uploadVideo })} />);
    const input = container.querySelector('input[type="file"]')!;
    const file = new File(["veri"], "f16.mp4", { type: "video/mp4" });
    fireEvent.change(input, { target: { files: [file] } });
    await screen.findByText("Video Yükle / Sürükle");
    expect(uploadVideo).toHaveBeenCalledWith(file);
  });
  it("desteklenmeyen dosya türünde uploadVideo çağırmaz, hata gösterir", () => {
    const uploadVideo = vi.fn();
    const { container } = render(<VideoSourcePicker dataSource={dataSource({ uploadVideo })} />);
    const input = container.querySelector('input[type="file"]')!;
    const file = new File(["veri"], "belge.pdf", { type: "application/pdf" });
    fireEvent.change(input, { target: { files: [file] } });
    expect(uploadVideo).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/Geçersiz dosya türü/);
  });
  it("Canlı Kamera Aç'a tıklayınca startCamera'yı çağırır", async () => {
    const startCamera = vi.fn().mockResolvedValue(undefined);
    render(<VideoSourcePicker dataSource={dataSource({ startCamera })} />);
    fireEvent.click(screen.getByRole("button", { name: /Canlı Kamera Aç/ }));
    expect(startCamera).toHaveBeenCalled();
  });
  it("videoUpload/liveCamera desteklemeyen backend'de bu kontrolleri göstermez", () => {
    render(<VideoSourcePicker dataSource={dataSource({ capabilities: { ...existingBackendCapabilities, videoUpload: false, liveCamera: false } })} />);
    expect(screen.queryByRole("button", { name: /Canlı Kamera Aç/ })).not.toBeInTheDocument();
    expect(screen.queryByText("Video Yükle / Sürükle")).not.toBeInTheDocument();
  });
});
