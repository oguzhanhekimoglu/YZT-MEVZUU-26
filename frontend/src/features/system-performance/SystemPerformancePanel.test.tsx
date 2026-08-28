import { fireEvent, render, screen } from "@testing-library/react";
import { completedSessionFixture, idleSessionFixture, runningSessionFixture } from "../../test/fixtures";
import { SystemPerformancePanel } from "./SystemPerformancePanel";

describe("SystemPerformancePanel", () => {
  it("kapalı özette canlı performansı gösterir ve açılır", () => {
    render(<SystemPerformancePanel session={runningSessionFixture} />);
    expect(screen.getByText("24.8 FPS · 38 ms")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Sistem Performansı/ }));
    expect(screen.getByText("GPU kullanımı")).toBeInTheDocument();
    expect(screen.getByText("Stabil")).toBeInTheDocument();
  });

  it("kalite KPI ve yük testi kaynağını ayrı sekmede gösterir", () => {
    render(<SystemPerformancePanel session={completedSessionFixture} />);
    fireEvent.click(screen.getByRole("button", { name: /Sistem Performansı/ }));
    fireEvent.click(screen.getByRole("tab", { name: "Kalite KPI'ları" }));
    expect(screen.getByText("Olay tespit doğruluğu")).toBeInTheDocument();
    expect(screen.getByText("4 paralel video · 1080p · 22.6 FPS · %1.2 kare kaybı")).toBeInTheDocument();
    expect(screen.getByText(/24 senaryo/)).toBeInTheDocument();
  });

  it("telemetri yoksa veri bekleme durumunu gösterir", () => {
    render(<SystemPerformancePanel session={idleSessionFixture} />);
    expect(screen.getByText("Telemetri verisi bekleniyor")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Sistem Performansı/ }));
    expect(screen.getByText(/Backend telemetri verisi sağladığında/)).toBeInTheDocument();
  });
});
