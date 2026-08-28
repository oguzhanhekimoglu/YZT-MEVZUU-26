import { render, screen } from "@testing-library/react";
import { VideoDropzone } from "./VideoDropzone";

describe("VideoDropzone", () => {
  it("sürükle-bırak/dosya seç alanı olmadan sade 'Video bekleniyor' yer tutucusu gösterir", () => {
    render(<VideoDropzone />);
    expect(screen.getByText("Video bekleniyor")).toBeInTheDocument();
    expect(screen.queryByText("Videoyu buraya sürükleyin")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Dosya Seç/ })).not.toBeInTheDocument();
  });
});
