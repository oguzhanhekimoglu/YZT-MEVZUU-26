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
});
