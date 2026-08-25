import { render, screen } from "@testing-library/react";
import { normalizeRisk } from "../../services/risk-normalization";
import { RiskBadge } from "./RiskBadge";

describe("RiskBadge", () => {
  it("normalize edilen riski metin, işaret ve semantik değerle gösterir", () => {
    render(<RiskBadge risk={normalizeRisk("YÜKSEK")} prefix="Hedef riski" />);
    const badge = screen.getByText(/Hedef riski: Yüksek/);
    expect(badge).toHaveAttribute("data-risk", "high");
    expect(badge).toHaveTextContent("▲");
  });
});
