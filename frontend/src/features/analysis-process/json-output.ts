import type { FinalOutput } from "../../types";

export function formatFinalOutputJson(output: FinalOutput): string { return JSON.stringify(output, null, 2); }
export function safeSessionFileName(sessionId: string): string {
  const safe = sessionId.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").toLowerCase();
  return `mevzuu-analiz-${safe || "oturum"}.json`;
}

export function downloadFinalOutput(output: FinalOutput, sessionId: string): void {
  const blob = new Blob([formatFinalOutputJson(output)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = safeSessionFileName(sessionId);
  anchor.click();
  URL.revokeObjectURL(url);
}
