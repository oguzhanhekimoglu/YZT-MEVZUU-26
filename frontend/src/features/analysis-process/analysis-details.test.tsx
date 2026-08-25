import { fireEvent, render, screen } from "@testing-library/react";
import { CandidateList, uniqueCandidates } from "./CandidateList";
import { FinalOutputStepDetail } from "./FinalOutputStepDetail";
import { finalOutput } from "../../test/fixtures";
import { safeSessionFileName } from "./json-output";

afterEach(() => vi.restoreAllMocks());

describe("analysis detail utilities", () => {
  it("adayları model bazında birleştirip en yüksek skoru korur", () => {
    const candidates = uniqueCandidates([{ model: "A", score: .4 }, { model: "A", score: .9 }, { model: "B", score: .7 }]);
    expect(candidates).toEqual([{ model: "A", score: .9 }, { model: "B", score: .7 }]);
    render(<CandidateList candidates={candidates} />);
    expect(screen.getByText("%90")).toBeInTheDocument();
  });

  it("JSON dialog içinde girintili canonical çıktı gösterir", () => {
    render(<FinalOutputStepDetail output={finalOutput} sessionId="oturum-4" />);
    fireEvent.click(screen.getByRole("button", { name: "JSON'u Görüntüle" }));
    const dialog = screen.getByRole("dialog", { name: "Canonical JSON Çıktısı" });
    expect(dialog).toHaveTextContent('"status": "final"');
    expect(dialog).toHaveTextContent("Canonical nihai çıktının ham JSON gösterimi.");
  });

  it("JSON kopyalama başarısını bildirir", async () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockResolvedValue(undefined) } });
    render(<FinalOutputStepDetail output={finalOutput} sessionId="oturum-4" />);
    fireEvent.click(screen.getByRole("button", { name: "Panoya Kopyala" }));
    expect(await screen.findByText("JSON panoya kopyalandı.")).toBeInTheDocument();
  });

  it("JSON kopyalama hatasını Türkçe bildirir", async () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
    render(<FinalOutputStepDetail output={finalOutput} sessionId="oturum-4" />);
    fireEvent.click(screen.getByRole("button", { name: "Panoya Kopyala" }));
    expect(await screen.findByText("JSON panoya kopyalanamadı.")).toBeInTheDocument();
  });

  it("güvenli JSON dosya adı üretir ve lokal indirme başlatır", () => {
    expect(safeSessionFileName("Oturum / ŞĞ 42")).toBe("mevzuu-analiz-oturum-sg-42.json");
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:json");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    render(<FinalOutputStepDetail output={finalOutput} sessionId="Oturum / ŞĞ 42" />);
    fireEvent.click(screen.getByRole("button", { name: "JSON İndir" }));
    expect(click).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:json");
  });
});
