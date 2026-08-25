import { render, screen } from "@testing-library/react";
import { finalOutput, provisionalOutput } from "../../test/fixtures";
import { FinalResultPanel } from "./FinalResultPanel";

describe("FinalResultPanel", () => {
  it("geçici ve nihai durumları doğru gösterir", () => {
    const { rerender } = render(<FinalResultPanel output={provisionalOutput} />);
    expect(screen.getByText("Geçici sonuç")).toBeInTheDocument();
    rerender(<FinalResultPanel output={finalOutput} />);
    expect(screen.getByText("Nihai sonuç")).toBeInTheDocument();
  });
});
