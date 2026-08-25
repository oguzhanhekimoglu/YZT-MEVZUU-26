import type { AnalysisStep, FinalOutput, ProcessStatus, TargetAnalysis } from "../../types";

export const stepOrder: AnalysisStep["id"][] = ["detection", "vrag", "vlm", "llm", "final"];
export const statusLabels: Record<ProcessStatus, string> = { waiting: "Bekliyor", running: "Çalışıyor", completed: "Tamamlandı", warning: "Uyarılı", error: "Hata" };
export const statusIcons: Record<ProcessStatus, string> = { waiting: "○", running: "◉", completed: "✓", warning: "⚠", error: "×" };

export function finalStatus(output: FinalOutput): ProcessStatus {
  if (output.status === "pending") return "waiting";
  if (output.status === "partial") return "warning";
  if (output.status === "final") return "completed";
  return "running";
}

export function targetSteps(target: TargetAnalysis, output: FinalOutput): AnalysisStep[] {
  return [target.detection, target.vrag, target.vlm, target.llm, {
    id: "final",
    title: "Nihai Çıktı",
    status: finalStatus(output),
    statusText: output.status === "pending" ? "Bekliyor" : output.status === "provisional" ? "Geçici" : output.status === "partial" ? "Kısmi" : "Nihai",
    summary: output.status === "pending" ? "Önceki aşamalar bekleniyor" : output.summary,
    updatedAt: output.generatedAt,
    detail: output,
  }];
}

export function defaultOpenStep(steps: AnalysisStep[]): AnalysisStep["id"] | undefined {
  return steps.find((step) => step.status === "running")?.id
    ?? steps.find((step) => step.status === "error")?.id
    ?? steps.find((step) => step.status === "warning")?.id
    ?? undefined;
}

export function formatDuration(durationMs?: number): string | undefined {
  if (durationMs === undefined || !Number.isFinite(durationMs) || durationMs < 0) return undefined;
  return durationMs < 1000 ? `${Math.round(durationMs)} ms` : `${(durationMs / 1000).toFixed(1)} sn`;
}

export function percent(value?: number): string {
  if (value === undefined || !Number.isFinite(value)) return "Henüz mevcut değil";
  return `%${Math.round(Math.min(1, Math.max(0, value)) * 100)}`;
}

export function safeText(value?: string): string { return value?.trim() || "Henüz mevcut değil"; }
