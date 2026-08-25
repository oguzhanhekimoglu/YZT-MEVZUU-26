import type { RiskLevel } from "../types";

const normalizedRisks: Readonly<Record<string, RiskLevel>> = {
  info: "info",
  low: "low",
  düşük: "low",
  dusuk: "low",
  medium: "medium",
  orta: "medium",
  high: "high",
  yüksek: "high",
  yuksek: "high",
  critical: "critical",
  kritik: "critical",
};

export function normalizeRisk(value: unknown): RiskLevel {
  if (typeof value !== "string") {
    return "unknown";
  }

  return normalizedRisks[value.trim().toLowerCase()] ?? "unknown";
}
