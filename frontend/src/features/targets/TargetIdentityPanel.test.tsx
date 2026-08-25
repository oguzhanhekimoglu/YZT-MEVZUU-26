import { fireEvent, render, screen } from "@testing-library/react";
import { testTargets } from "../../test/fixtures";
import { TargetIdentityPanel } from "./TargetIdentityPanel";

describe("TargetIdentityPanel reference", () => {
  it("referans görseli hata verince lokal placeholder gösterir", () => {
    const target = { ...testTargets[0]!, vrag: { ...testTargets[0]!.vrag, detail: { ...testTargets[0]!.vrag.detail!, referenceImageUrl: "/referans?model=F-16" } } };
    render(<TargetIdentityPanel target={target} />);
    fireEvent.error(screen.getByRole("img", { name: /F-16.*referans görseli$/ }));
    expect(screen.getByRole("img", { name: /F-16.*referans görseli mevcut değil/ })).toBeVisible();
    expect(screen.getByText("Referans görsel yok")).toBeVisible();
  });
});
