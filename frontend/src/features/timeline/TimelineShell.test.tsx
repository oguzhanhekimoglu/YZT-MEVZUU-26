import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { AppProviders } from "../../app/providers";
import type { OperatorDataSource } from "../../services/contracts";
import type { OperatorSession, TimelineEvent } from "../../types";
import { completedSessionFixture, denseTimelineSessionFixture, idleSessionFixture, timelineEvents } from "../../test/fixtures";
import { AnalysisProcessDrawer } from "../analysis-process/AnalysisProcessDrawer";
import { TimelineShell } from "./TimelineShell";
import { SelectedEventPanel } from "./SelectedEventPanel";
import { testCapabilities } from "../../test/test-data-source";

function dataSource(): OperatorDataSource & { selectTarget: ReturnType<typeof vi.fn> } {
  return { capabilities: testCapabilities, getSession: vi.fn().mockResolvedValue(idleSessionFixture), subscribe: vi.fn(() => () => undefined), selectVideo: vi.fn(), listServerVideos: vi.fn().mockResolvedValue([]), start: vi.fn(), pause: vi.fn(), resume: vi.fn(), stop: vi.fn(), restart: vi.fn(), selectTarget: vi.fn().mockResolvedValue(completedSessionFixture), dispose: vi.fn() } as OperatorDataSource & { selectTarget: ReturnType<typeof vi.fn> };
}

function Harness({ initial = completedSessionFixture, source = dataSource(), withDrawer = false }: { initial?: OperatorSession; source?: ReturnType<typeof dataSource>; withDrawer?: boolean }) {
  const [session, setSession] = useState(initial);
  const [selectedEvent, setSelectedEvent] = useState<TimelineEvent>();
  return <AppProviders dataSource={source}><button type="button" onClick={() => setSession((current) => ({ ...current, events: [...current.events, { ...timelineEvents[0]!, id: "new-critical", title: "Yeni kritik olay", critical: true, risk: "critical" }] }))}>Olay Ekle</button><button type="button" onClick={() => setSession((current) => ({ ...current, events: current.events.filter((event) => event.id !== "risk-increased") }))}>Olayı Sil</button><button type="button" onClick={() => setSession({ ...idleSessionFixture, id: "new-session", sourceName: "yeni.mp4" })}>Yeni Video</button><TimelineShell session={session} dataSource={source} onSelectEvent={setSelectedEvent} /><SelectedEventPanel event={selectedEvent} session={session} dataSource={source} />{withDrawer && <AnalysisProcessDrawer session={session} onSelectTarget={(id) => void source.selectTarget(id)} />}</AppProviders>;
}

function marker(name: RegExp) { return screen.getByRole("button", { name }); }

describe("TimelineShell", () => {
  it("olayları zaman sırasıyla ve oranlı konumlarla gösterir", () => {
    render(<Harness />);
    const first = marker(/Hedef ilk kez görüldü/); const last = marker(/Analiz tamamlandı/);
    expect(Number.parseFloat(first.style.left)).toBeCloseTo(18 / 70 * 100, 3); expect(last.style.left).toBe("100%");
    expect(first.compareDocumentPosition(last) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("süre bilinmediğinde sahte toplam süre göstermez", () => {
    render(<Harness initial={{ ...completedSessionFixture, durationSeconds: undefined }} />);
    expect(screen.getByText("Süre bekleniyor")).toBeInTheDocument(); expect(screen.getByText("Süre bilinmiyor")).toBeInTheDocument();
  });

  it("marker seçilince sabit ayrıntı alanını günceller", () => {
    render(<Harness />); fireEvent.click(marker(/Risk seviyesi yükseldi/));
    expect(screen.getByTestId("selected-event-detail")).toHaveTextContent("Hedef #7 için operatör incelemesi gerekiyor.");
    expect(screen.getByLabelText("Zaman Damgalı Olaylar")).toHaveAttribute("data-layout", "fixed-timeline");
  });

  it("seçimi canlı güncellemede korur ve yeni kritiğe geçmez", () => {
    render(<Harness />); fireEvent.click(marker(/Risk seviyesi yükseldi/)); fireEvent.click(screen.getByRole("button", { name: "Olay Ekle" }));
    expect(screen.getByTestId("selected-event-detail")).toHaveTextContent("Risk seviyesi yükseldi");
  });

  it("kaldırılan seçili olayı temizler", async () => {
    render(<Harness />); fireEvent.click(marker(/Risk seviyesi yükseldi/)); fireEvent.click(screen.getByRole("button", { name: "Olayı Sil" }));
    await waitFor(() => expect(screen.queryByTestId("selected-event-detail")).not.toBeInTheDocument());
  });

  it("Tümü Kritik Yüksek ve hedef filtrelerini uygular", () => {
    render(<Harness />); expect(screen.getByRole("button", { name: "Tümü" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Kritik" })); expect(marker(/Kritik durum oluştu/)).toBeInTheDocument(); expect(screen.queryByRole("button", { name: /Risk seviyesi yükseldi/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Yüksek" })); expect(marker(/Risk seviyesi yükseldi/)).toBeInTheDocument(); expect(screen.queryByRole("button", { name: /Operatör teyidi gerekiyor/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hedef #7" })); expect(marker(/Risk seviyesi yükseldi/)).toBeInTheDocument(); expect(screen.queryByRole("button", { name: /Hedef ilk kez görüldü/ })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Hedef #-1" })).not.toBeInTheDocument();
  });

  it("boş filtre sonucunu gösterir ve seçimi temizler", async () => {
    const noCritical = { ...completedSessionFixture, events: completedSessionFixture.events.filter((event) => !event.critical) };
    render(<Harness initial={noCritical} />); fireEvent.click(marker(/Risk seviyesi yükseldi/)); fireEvent.click(screen.getByRole("button", { name: "Kritik" }));
    expect(screen.getByText("Bu filtreyle eşleşen olay bulunamadı.")).toBeInTheDocument(); await waitFor(() => expect(screen.queryByTestId("selected-event-detail")).not.toBeInTheDocument());
  });

  it("aynı event ID'yi bir kez render eder", () => {
    render(<Harness initial={{ ...completedSessionFixture, events: [...completedSessionFixture.events, completedSessionFixture.events[0]!] }} />);
    expect(screen.getAllByRole("button", { name: /Hedef ilk kez görüldü/ })).toHaveLength(1);
  });

  it("aynı saniyedeki olayları cluster içinde listeler ve seçer", () => {
    render(<Harness />); const cluster = screen.getByRole("button", { name: /00:51 civarında 4 olay/ }); fireEvent.click(cluster);
    const popover = screen.getByRole("dialog", { name: /00:51 civarındaki olaylar/ }); fireEvent.click(within(popover).getByRole("button", { name: /Kimlik güveninde düşüş/ }));
    expect(screen.getByTestId("selected-event-detail")).toHaveTextContent("Hedef #7 kimlik güveninde anlamlı düşüş görüldü.");
  });

  it("cluster popover Esc ile kapanır ve odağı döndürür", () => {
    render(<Harness />); const cluster = screen.getByRole("button", { name: /00:51 civarında 4 olay/ }); fireEvent.click(cluster);
    fireEvent.keyDown(screen.getByRole("button", { name: /Operatör teyidi gerekiyor/ }), { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: /00:51 civarındaki olaylar/ })).not.toBeInTheDocument(); expect(cluster).toHaveFocus();
  });

  it("oklar ve Home End marker odağını taşır", () => {
    const simple = { ...completedSessionFixture, events: timelineEvents.filter((event) => !["permission-mismatch", "identity-confidence-drop"].includes(event.id)) };
    render(<Harness initial={simple} />); const first = marker(/Hedef ilk kez görüldü/); const second = marker(/Model eşleştirmesi başladı/); fireEvent.focus(first); fireEvent.keyDown(first, { key: "ArrowRight" }); expect(second).toHaveFocus(); fireEvent.keyDown(second, { key: "End" }); expect(marker(/Analiz tamamlandı/)).toHaveFocus(); fireEvent.keyDown(document.activeElement!, { key: "Home" }); expect(first).toHaveFocus();
  });

  it("erişilebilir adda sıra zaman risk ve hedef bulunur", () => {
    render(<Harness />); expect(marker(/10 olaydan 1\. olay, 00:18, Hedef ilk kez görüldü, Bilgi, Hedef #4/)).toBeInTheDocument();
  });

  it("marker tıklanınca hedefi seçer ve analiz ayrıntılarını açma butonu gösterir", () => {
    const source = dataSource(); render(<Harness source={source} />); fireEvent.click(marker(/Risk seviyesi yükseldi/)); expect(source.selectTarget).toHaveBeenCalledWith(7); expect(screen.getByRole("button", { name: "Analiz Ayrıntılarını Aç" })).toBeInTheDocument();
  });

  it("olay eylemi doğru hedef ve step ile inline panel açar", async () => {
    render(<Harness withDrawer />); fireEvent.click(marker(/Risk seviyesi yükseldi/)); const action = screen.getByRole("button", { name: "Analiz Ayrıntılarını Aç" }); action.focus(); fireEvent.click(action);
    const panel = await screen.findByRole("region", { name: "Analiz Süreci ayrıntıları" }); expect(within(panel).getByRole("heading", { name: "Hedef #7" })).toBeInTheDocument(); expect(within(panel).getByRole("button", { name: /LLM Karar/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("video geneli olayı final adımıyla açar ve seek göstermez", async () => {
    render(<Harness withDrawer />); fireEvent.click(marker(/Analiz tamamlandı/)); fireEvent.click(screen.getByRole("button", { name: "Analiz Ayrıntılarını Aç" })); const panel = await screen.findByRole("region", { name: "Analiz Süreci ayrıntıları" }); expect(within(panel).getByRole("heading", { name: "Video Geneli" })).toBeInTheDocument(); expect(within(panel).getByRole("button", { name: /Nihai Çıktı/ })).toHaveAttribute("aria-expanded", "true"); expect(screen.queryByRole("button", { name: "Bu Ana Git" })).not.toBeInTheDocument();
  });

  it("snapshot varsa gösterir", () => {
    const snapshotEvent: TimelineEvent = { ...timelineEvents[0]!, id: "snapshot", snapshotUrl: "data:image/gif;base64,R0lGODlhAQABAAAAACw=" };
    render(<Harness initial={{ ...completedSessionFixture, events: [snapshotEvent] }} />); fireEvent.click(marker(/Hedef ilk kez görüldü/)); expect(screen.getByRole("img", { name: /olay görüntüsü/ })).toBeInTheDocument();
  });

  it("30 olaylı yoğun senaryoyu sabit yapıda render eder", () => {
    render(<Harness initial={denseTimelineSessionFixture} />); expect(screen.getByText("30 olay")).toBeInTheDocument(); expect(screen.getByLabelText("Zaman Damgalı Olaylar")).toHaveAttribute("data-layout", "fixed-timeline");
  });

  it("yeni video session ID'sinde seçim ve filtreyi sıfırlar", async () => {
    render(<Harness />); fireEvent.click(marker(/Risk seviyesi yükseldi/)); fireEvent.click(screen.getByRole("button", { name: "Yüksek" })); fireEvent.click(screen.getByRole("button", { name: "Yeni Video" })); await waitFor(() => expect(screen.getByRole("button", { name: "Tümü" })).toHaveAttribute("aria-pressed", "true")); expect(screen.queryByTestId("selected-event-detail")).not.toBeInTheDocument(); expect(screen.getByText("0 olay")).toBeInTheDocument();
  });

  it("timeline ile final çıktı aynı canonical olay kimliklerini kullanır", () => {
    expect(completedSessionFixture.events[0]).toBe(completedSessionFixture.finalOutput.events[0]);
  });

  it("timeline metninde yasaklı terminoloji bulunmaz", () => {
    render(<Harness />); expect(screen.getByLabelText("Zaman Damgalı Olaylar").textContent).not.toMatch(/gidiş yönü/i);
  });
});
