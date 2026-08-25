import { render, screen } from "@testing-library/react";
import { VideoDropzone } from "./VideoDropzone";

describe("VideoDropzone", () => {
  it("onFile verilmezse sürükle-bırak/dosya seç alanı render edilmez, basit yer tutucu görünür", () => {
    render(<VideoDropzone />);
    expect(screen.queryByText("Videoyu buraya sürükleyin")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Dosya Seç/ })).not.toBeInTheDocument();
    expect(screen.getByText("Üstteki listeden bir video seçin")).toBeInTheDocument();
  });
  it("onFile verilirse sürükle-bırak alanı görünür", () => {
    render(<VideoDropzone onFile={vi.fn()} />);
    expect(screen.getByText("Videoyu buraya sürükleyin")).toBeInTheDocument();
  });
});
