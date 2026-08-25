import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { App } from "../../app/App";
import { AppProviders } from "../../app/providers";
import { TestOperatorDataSource, type TestScenario } from "../../test/test-data-source";
import {
  completedSessionFixture,
  conflictSessionFixture,
  idleSessionFixture,
  llmErrorSessionFixture,
  lowConfidenceSessionFixture,
  runningSessionFixture,
  vlmErrorSessionFixture,
} from "../../test/fixtures";
import type { OperatorSession } from "../../types";
import { useState } from "react";
import { AnalysisProcessDrawer } from "./AnalysisProcessDrawer";
import { useAnalysisDrawer } from "./analysis-drawer-context";

function dataSourceFor(session: OperatorSession) {
  const scenario: TestScenario = { id: `test-${session.id}`, label: "Test", snapshots: [idleSessionFixture, session] };
  return new TestOperatorDataSource(scenario);
}

async function renderSession(session: OperatorSession = completedSessionFixture) {
  const dataSource = dataSourceFor(session);
  const result = render(<AppProviders dataSource={dataSource}><App /></AppProviders>);
  await act(async () => { await dataSource.selectVideo({ name: "gorev.mp4" }); await dataSource.start(); });
  return { dataSource, ...result };
}

async function openDrawer(session: OperatorSession = completedSessionFixture) {
  const result = await renderSession(session);
  const trigger = await screen.findByRole("button", { name: /Ayrıntıları Gör/ });
  trigger.focus();
  fireEvent.click(trigger);
  return { trigger, dialog: await screen.findByRole("region", { name: "Analiz Süreci ayrıntıları" }), ...result };
}

function ensureStepOpen(dialog: HTMLElement, name: RegExp) {
  const button = within(dialog).getByRole("button", { name });
  if (button.getAttribute("aria-expanded") !== "true") fireEvent.click(button);
  return button;
}

function stepContent(dialog: HTMLElement, name: RegExp) {
  const button = ensureStepOpen(dialog, name);
  return dialog.querySelector<HTMLElement>(`#${button.getAttribute("aria-controls")}`)!;
}

afterEach(() => vi.restoreAllMocks());

describe("AnalysisProcessDrawer", () => {
  it("trigger ile sağ sütunda inline analiz paneli açar", async () => {
    const { trigger, dialog } = await openDrawer();
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(dialog).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Analiz Süreci" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Video çalışma alanı")).toBeInTheDocument();
    expect(screen.getByLabelText("Operatör karar paneli")).toBeInTheDocument();
  });

  it("aynı tetikleyiciyle inline paneli kapatır", async () => {
    const { trigger } = await openDrawer();
    fireEvent.click(trigger);
    expect(screen.queryByRole("region", { name: "Analiz Süreci ayrıntıları" })).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("aşama başlıklarını normal sayfa akışında klavye erişimli tutar", async () => {
    const { dialog } = await openDrawer();
    const buttons = within(dialog).getAllByRole("button");
    buttons[0].focus();
    expect(buttons[0]).toHaveFocus();
    expect(buttons[0]).toHaveAttribute("aria-expanded");
  });

  it("ana seçili hedefle açılır ve id -1 görünmez", async () => {
    const { dialog } = await openDrawer();
    expect(within(dialog).getByRole("heading", { name: "Hedef #4" })).toBeInTheDocument();
    expect(within(dialog).queryByText("Hedef #-1")).not.toBeInTheDocument();
  });

  it("karar zinciri ayrıntılarını kapalı başlatır ve bağımsız açar", async () => {
    const { dialog } = await openDrawer();
    const vrag = within(dialog).getByRole("button", { name: /VRAG Model/ });
    const vlm = within(dialog).getByRole("button", { name: /VLM Görsel/ });
    const llm = within(dialog).getByRole("button", { name: /LLM Karar/ });
    expect(vrag).toHaveAttribute("aria-expanded", "false");
    expect(vlm).toHaveAttribute("aria-expanded", "false");
    expect(llm).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(vrag);
    expect(vrag).toHaveAttribute("aria-expanded", "true");
    expect(vlm).toHaveAttribute("aria-expanded", "false");
  });

  it("nesne tespiti canonical ayrıntılarını gösterir", async () => {
    const { dialog } = await openDrawer();
    fireEvent.click(within(dialog).getByRole("button", { name: /Nesne Tespiti/ }));
    const detection = dialog.querySelector<HTMLElement>("#analysis-step-detection-content")!;
    expect(within(detection).getByText("%91")).toBeInTheDocument();
    expect(within(detection).getByText("38 eşleşme")).toBeInTheDocument();
    expect(within(detection).getByText("24.7 px/sn")).toBeInTheDocument();
  });

  it("VRAG adaylarını benzersiz ve azalan skorla gösterir", async () => {
    const { dialog } = await openDrawer();
    const vrag = stepContent(dialog, /VRAG Model/);
    const f16 = within(vrag).getAllByText("F-16 Fighting Falcon");
    expect(f16).toHaveLength(2);
    const candidates = within(vrag).getByText("Benzer Adaylar").nextElementSibling!;
    const text = candidates.textContent ?? "";
    expect(text.indexOf("%91")).toBeLessThan(text.indexOf("%78"));
    expect(text.indexOf("%78")).toBeLessThan(text.indexOf("%72"));
  });

  it("düşük VRAG güveni uyarısını gösterir", async () => {
    const { dialog } = await openDrawer(lowConfidenceSessionFixture);
    ensureStepOpen(dialog, /VRAG Model/);
    expect(within(dialog).getByText("⚠ Düşük kimlik güveni")).toBeInTheDocument();
    expect(within(dialog).getByText("İlk iki aday farkı: %3")).toBeInTheDocument();
  });

  it("VLM tehdidini doğru etiketler ve VRAG çelişkisini gösterir", async () => {
    const { dialog } = await openDrawer(conflictSessionFixture);
    const vlm = stepContent(dialog, /VLM Görsel/);
    expect(within(vlm).getByText("Tehdit hipotezi")).toBeInTheDocument();
    expect(within(vlm).getByText("⚠ Görsel doğrulama çelişkisi")).toBeInTheDocument();
    expect(within(vlm).queryByText("Nihai risk", { selector: "dt" })).not.toBeInTheDocument();
  });

  it("LLM risk faktörlerini ve aksiyonlarını gruplandırır", async () => {
    const { dialog } = await openDrawer();
    const llm = stepContent(dialog, /LLM Karar/);
    expect(within(llm).getByText("Riski Artıran Faktörler")).toBeInTheDocument();
    expect(within(llm).getByText("Uçuş izni doğrulanamadı")).toBeInTheDocument();
    expect(within(llm).getByText("Riski Azaltan Faktörler")).toBeInTheDocument();
    expect(within(llm).getByText("Takibi kesintisiz sürdür")).toBeInTheDocument();
  });

  it("çalışan LLM'de alt adımları gösterip sahte nihai alan üretmez", async () => {
    const { dialog } = await openDrawer(runningSessionFixture);
    const llm = stepContent(dialog, /LLM Karar/);
    expect(within(llm).getByText("Uçuş izni ve uçuş planı inceleniyor")).toBeInTheDocument();
    expect(within(dialog).queryByText("Envanter", { selector: "dt" })).not.toBeInTheDocument();
  });

  it("VLM hatasında kısmi devam açıklamasını gösterir", async () => {
    const { dialog } = await openDrawer(vlmErrorSessionFixture);
    ensureStepOpen(dialog, /VLM Görsel/);
    expect(within(dialog).getByText(/Yerel VLM servisine ulaşılamadı/)).toBeInTheDocument();
    expect(within(dialog).getByText(/analiz kısmi olarak devam edebilir/)).toBeInTheDocument();
  });

  it("LLM hatasında nihai risk uydurmaz", async () => {
    const { dialog } = await openDrawer(llmErrorSessionFixture);
    ensureStepOpen(dialog, /LLM Karar/);
    expect(within(dialog).getByText(/Operasyonel karar servisine ulaşılamadı/)).toBeInTheDocument();
    expect(within(dialog).queryByText("Orta", { exact: true })).not.toBeInTheDocument();
  });

  it("yasaklı terminolojiyi render etmez", async () => {
    await openDrawer();
    expect(document.body.textContent).not.toMatch(/gidiş yönü/i);
  });

  it("pipeline ilerleyince açık ayrıntıyı güncel aşamaya taşır", async () => {
    const scenario: TestScenario = { id: "live-complete", label: "Canlı", snapshots: [idleSessionFixture, runningSessionFixture, completedSessionFixture] };
    const dataSource = new TestOperatorDataSource(scenario);
    render(<AppProviders dataSource={dataSource}><App /></AppProviders>);
    await act(async () => { await dataSource.selectVideo({ name: "gorev.mp4" }); await dataSource.start(); });
    fireEvent.click(await screen.findByRole("button", { name: /Ayrıntıları Gör/ }));
    const dialog = await screen.findByRole("region", { name: "Analiz Süreci ayrıntıları" });
    const llm = within(dialog).getByRole("button", { name: /LLM Karar/ });
    fireEvent.click(llm);
    expect(llm).toHaveAttribute("aria-expanded", "true");
    expect(within(dialog).getByText("Uçuş izni ve uçuş planı inceleniyor")).toBeInTheDocument();
    act(() => dataSource.advance());
    const finalBtn = within(dialog).getByRole("button", { name: /Nihai Çıktı/ });
    fireEvent.click(finalBtn);
    expect(finalBtn).toHaveAttribute("aria-expanded", "true");
  });

  it("manuel açılan aşamayı canlı güncellemede değiştirmez", async () => {
    const scenario: TestScenario = { id: "manual-stays", label: "Manuel", snapshots: [idleSessionFixture, runningSessionFixture, completedSessionFixture] };
    const dataSource = new TestOperatorDataSource(scenario);
    render(<AppProviders dataSource={dataSource}><App /></AppProviders>);
    await act(async () => { await dataSource.selectVideo({ name: "gorev.mp4" }); await dataSource.start(); });
    fireEvent.click(await screen.findByRole("button", { name: /Ayrıntıları Gör/ }));
    const dialog = await screen.findByRole("region", { name: "Analiz Süreci ayrıntıları" });
    const detection = within(dialog).getByRole("button", { name: /Nesne Tespiti/ });
    fireEvent.click(detection);
    act(() => dataSource.advance());
    expect(detection).toHaveAttribute("aria-expanded", "true");
    expect(within(dialog).getByRole("button", { name: /LLM Karar/ })).toHaveAttribute("aria-expanded", "false");
  });

  it("ana panel ve inline süreç aynı canonical nihai özeti kullanır", async () => {
    const { dialog } = await openDrawer();
    ensureStepOpen(dialog, /Nihai Çıktı/);
    expect(screen.getAllByText(completedSessionFixture.finalOutput.summary).length).toBeGreaterThanOrEqual(2);
  });
});

function ExternalOpenHarness({ session }: { session: OperatorSession }) {
  const { openAnalysis } = useAnalysisDrawer();
  return <><button type="button" onClick={() => openAnalysis({ scope: "target", targetId: 4, stepId: "llm" })}>Dışarıdan Aç</button><AnalysisProcessDrawer session={session} onSelectTarget={() => undefined} /></>;
}

function RemovableTargetHarness() {
  const { openAnalysis } = useAnalysisDrawer();
  const [session, setSession] = useState(completedSessionFixture);
  return <><button type="button" onClick={() => openAnalysis({ scope: "target", targetId: 4 })}>Aç</button><button type="button" onClick={() => setSession((current) => ({ ...current, targets: current.targets.filter((target) => target.id !== 4) }))}>Hedefi Sil</button><AnalysisProcessDrawer session={session} onSelectTarget={() => undefined} /></>;
}

describe("openAnalysis API", () => {
  it("belirli hedef ve step ile inline panel açar", async () => {
    render(<AppProviders dataSource={dataSourceFor(completedSessionFixture)}><ExternalOpenHarness session={completedSessionFixture} /></AppProviders>);
    fireEvent.click(screen.getByRole("button", { name: "Dışarıdan Aç" }));
    const dialog = await screen.findByRole("region", { name: "Analiz Süreci ayrıntıları" });
    expect(within(dialog).getByRole("heading", { name: "Hedef #4" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /LLM Karar/ })).toHaveAttribute("aria-expanded", "true");
  });

  it("seçili hedef silinince Video Geneli kapsamına döner", async () => {
    render(<AppProviders dataSource={dataSourceFor(completedSessionFixture)}><RemovableTargetHarness /></AppProviders>);
    fireEvent.click(screen.getByRole("button", { name: "Aç" }));
    const dialog = await screen.findByRole("region", { name: "Analiz Süreci ayrıntıları" });
    expect(within(dialog).getByRole("heading", { name: "Hedef #4" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Hedefi Sil" }));
    expect(within(dialog).getByRole("heading", { name: "Video Geneli" })).toBeInTheDocument();
  });
});
