import { fireEvent, render, screen } from "@testing-library/react";
import { runningSessionFixture } from "../../test/fixtures";
import { TacticalOverlay } from "./TacticalOverlay";

describe("TacticalOverlay", () => {
  it("koordinatı bulunan hedefleri güven ve risk bilgisiyle gösterir", () => {
    const onSelectTarget = vi.fn();
    render(<TacticalOverlay session={runningSessionFixture} onSelectTarget={onSelectTarget} />);
    fireEvent.click(screen.getByRole("button", { name: /Bilinmeyen hava aracı, Hedef 7, Risk Yüksek/ }));
    expect(onSelectTarget).toHaveBeenCalledWith(7);
    expect(screen.getByText("ANALİZ AKTİF")).toBeInTheDocument();
  });

  it("aktif kritik olaydan ilgili hedefe geçer", () => {
    const onSelectTarget = vi.fn();
    render(<TacticalOverlay session={runningSessionFixture} onSelectTarget={onSelectTarget} />);
    expect(screen.getByText("KRİTİK OLAY · 00:51")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hedefi İncele" }));
    expect(onSelectTarget).toHaveBeenCalledWith(4);
  });
});
