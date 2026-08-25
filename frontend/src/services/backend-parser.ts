import type { ActionRecommendation, AircraftCandidate, FinalOutput, LlmDetail, TargetAnalysis, TimelineEvent, VlmDetail, VragDetail } from "../types";
import { normalizeRisk } from "./risk-normalization";
import { referenceImageUrl } from "./backend-url";

export interface BackendStatusPayload { calisiyor?: boolean; kaynak?: string; frame_no?: number; hedef_sayisi?: number; model_sayisi?: number; sure_saniye?: number; gecen_saniye?: number; }
export interface BackendTargetsEnvelope { frame?: number; hedefler: unknown[]; }

function record(value: unknown): Record<string, unknown> | undefined { return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined; }
function text(value: unknown): string | undefined { return typeof value === "string" && value.trim() ? value.trim() : undefined; }
function finite(value: unknown): number | undefined { return typeof value === "number" && Number.isFinite(value) ? value : undefined; }
function integer(value: unknown): number | undefined { const number = finite(value); return number !== undefined && Number.isInteger(number) ? number : undefined; }
function score(value: unknown): number | undefined { const number = finite(value); return number === undefined ? undefined : Math.min(1, Math.max(0, number)); }

function parseTrackingBox(value: unknown): TargetAnalysis["trackingBox"] {
  const source = record(value);
  const x = finite(source?.x); const y = finite(source?.y); const width = finite(source?.width); const height = finite(source?.height);
  if (x === undefined || y === undefined || width === undefined || height === undefined || x < 0 || y < 0 || width <= 0 || height <= 0 || x + width > 1 || y + height > 1) return undefined;
  return { x, y, width, height };
}

export function parseServerVideos(value: unknown): { name: string; path: string }[] {
  const source = record(value);
  const items = Array.isArray(source?.videolar) ? source!.videolar : [];
  const parsed: { name: string; path: string }[] = [];
  for (const item of items) {
    const entry = record(item);
    const name = text(entry?.ad);
    const path = text(entry?.yol);
    if (name && path) parsed.push({ name, path });
  }
  return parsed;
}

export function parseBackendStatus(value: unknown): BackendStatusPayload {
  const source = record(value);
  if (!source) return {};
  return {
    calisiyor: typeof source.calisiyor === "boolean" ? source.calisiyor : undefined,
    kaynak: text(source.kaynak), frame_no: integer(source.frame_no),
    hedef_sayisi: integer(source.hedef_sayisi), model_sayisi: integer(source.model_sayisi),
    sure_saniye: finite(source.sure_saniye), gecen_saniye: finite(source.gecen_saniye),
  };
}

export function parseTargetsEnvelope(value: unknown): BackendTargetsEnvelope | undefined {
  const source = record(value);
  if (!source || !Array.isArray(source.hedefler)) return undefined;
  return { frame: integer(source.frame), hedefler: source.hedefler };
}

function parseCandidates(value: unknown, apiBaseUrl: string): AircraftCandidate[] {
  if (!Array.isArray(value)) return [];
  const unique = new Map<string, AircraftCandidate>();
  for (const item of value) {
    const source = record(item); const model = text(source?.model); const candidateScore = score(source?.skor);
    if (!model || candidateScore === undefined) continue;
    const candidate = { model, score: candidateScore, country: text(source?.ulke), role: text(source?.rol), referenceImageUrl: referenceImageUrl(apiBaseUrl, model) };
    if (!unique.has(model) || unique.get(model)!.score < candidateScore) unique.set(model, candidate);
  }
  return [...unique.values()].sort((a, b) => b.score - a.score || a.model.localeCompare(b.model)).slice(0, 5);
}

function parseVlm(value: unknown): VlmDetail | undefined {
  const source = record(value); if (!source) return undefined;
  const detail: VlmDetail = {
    visualPrediction: text(source.gercek_tahmin), vehicleClass: text(source.arac_sinifi),
    countryHypothesis: text(source.ulke_orjini), threatHypothesis: normalizeRisk(source.tehdit_seviyesi),
    verification: text(source.dogrulama), vragConsistency: text(source.hedef_modeli_tutarlilik), visualAssessment: text(source.gorsel_analiz),
  };
  return Object.values(detail).some((item) => item !== undefined && item !== "unknown") ? detail : undefined;
}

function parseLlm(value: unknown): LlmDetail | undefined {
  const source = record(value); if (!source) return undefined;
  const summary = text(source.summary); const rawActions = Array.isArray(source.actions) ? source.actions : [];
  const actions: ActionRecommendation[] = rawActions.map(text).filter((item): item is string => Boolean(item)).slice(0, 10).map((label, index) => ({ id: `backend-action-${index + 1}`, label, priority: "normal" }));
  const risk = normalizeRisk(source.risk);
  if (!summary && risk === "unknown" && actions.length === 0) return undefined;
  return { risk, summary, riskIncreasingFactors: [], riskReducingFactors: [], actions };
}

function parseTimeLabelToSeconds(label: string): number {
  const parts = label.split(":").map((part) => Number.parseInt(part, 10));
  if (parts.some((part) => !Number.isFinite(part))) return 0;
  return parts.reduce((total, part) => total * 60 + part, 0);
}

export function parseVideoSummary(value: unknown): FinalOutput {
  const source = record(value);
  const status = text(source?.status);
  const summary = text(source?.summary) ?? "";
  const risk = normalizeRisk(source?.risk);
  const rawEvents = Array.isArray(source?.events) ? source.events : [];
  const events: TimelineEvent[] = rawEvents.map((item, index) => {
    const eventSource = record(item);
    const timeLabel = text(eventSource?.time) ?? "00:00";
    const description = text(eventSource?.event) ?? "";
    return {
      id: `video-summary-event-${index + 1}`,
      timeSeconds: parseTimeLabelToSeconds(timeLabel),
      timeLabel,
      title: description,
      description,
      risk,
      critical: eventSource?.critical === true,
      status: "completed" as const,
    };
  });
  const rawActions = Array.isArray(source?.actions) ? source.actions : [];
  const actions: ActionRecommendation[] = rawActions
    .map(text)
    .filter((item): item is string => Boolean(item))
    .slice(0, 10)
    .map((label, index) => ({ id: `video-summary-action-${index + 1}`, label, priority: "normal" }));
  return {
    status: status === "final" || status === "partial" ? status : "pending",
    summary,
    events,
    risk,
    actions,
  };
}

function isConflict(vlm?: VlmDetail): boolean {
  const value = `${vlm?.verification ?? ""} ${vlm?.vragConsistency ?? ""}`.toLocaleLowerCase("tr-TR");
  return /çeliş|tutarsız|uyuşma/.test(value);
}

export function parseBackendTarget(value: unknown, apiBaseUrl: string): TargetAnalysis | undefined {
  const source = record(value); const id = integer(source?.id);
  if (id === undefined || id === -1) return undefined;
  const className = text(source?.sinif) ?? "Hava aracı"; const confidence = score(source?.guven) ?? 0;
  const model = text(source?.model); const modelScore = score(source?.model_skor); const candidates = parseCandidates(source?.adaylar, apiBaseUrl);
  const lowConfidence = source?.dusuk_guven === true;
  const vrag: VragDetail = { model, score: modelScore, lowConfidence, country: text(source?.ulke), manufacturer: text(source?.uretici), role: text(source?.rol), referenceImageUrl: referenceImageUrl(apiBaseUrl, model), candidates };
  const vlm = parseVlm(source?.vlm); const llm = parseLlm(source?.llm);
  const vragReady = Boolean(model || candidates.length); const vlmConflict = isConflict(vlm);
  return {
    id, displayName: model ?? `${className} #${id}`, className, detectionConfidence: confidence, risk: llm?.risk ?? "unknown", selected: false, trackingBox: parseTrackingBox(source?.bbox),
    detection: { id: "detection", title: "Nesne Tespiti", status: "completed", statusText: "Tamamlandı", summary: `Hedef #${id} · ${className} · Güven %${Math.round(confidence * 100)}`, detail: { targetId: id, className, confidence, trackingStatus: "active", hits: Math.max(0, integer(source?.hits) ?? 0), speedPxS: finite(source?.hiz_px_s), zigzagScore: score(source?.zigzag) } },
    vrag: { id: "vrag", title: "VRAG Model Eşleştirmesi", status: lowConfidence ? "warning" : vragReady ? "completed" : "waiting", statusText: lowConfidence ? "Uyarılı" : vragReady ? "Tamamlandı" : "Bekliyor", summary: model ? `${model}${modelScore !== undefined ? ` · Benzerlik %${Math.round(modelScore * 100)}` : ""}` : "Model eşleştirmesi henüz mevcut değil", warning: lowConfidence ? "Düşük kimlik güveni" : undefined, detail: vrag },
    vlm: { id: "vlm", title: "VLM Görsel Doğrulama", status: vlmConflict ? "warning" : vlm ? "completed" : "waiting", statusText: vlmConflict ? "Uyarılı" : vlm ? "Tamamlandı" : "Bekliyor", summary: vlm?.visualPrediction ?? "Görsel doğrulama henüz mevcut değil", warning: vlmConflict ? "Görsel doğrulama çelişkisi" : undefined, detail: vlm ?? {} },
    llm: { id: "llm", title: "LLM Karar Desteği", status: llm ? "completed" : "waiting", statusText: llm ? "Tamamlandı" : "Bekliyor", summary: llm?.summary ?? "Operasyonel karar sonucu henüz mevcut değil", detail: llm ?? { risk: "unknown", riskIncreasingFactors: [], riskReducingFactors: [], actions: [] } },
  };
}

export function parseBackendTargets(values: unknown[], apiBaseUrl: string): TargetAnalysis[] {
  return values.map((value) => parseBackendTarget(value, apiBaseUrl)).filter((target): target is TargetAnalysis => Boolean(target)).sort((a, b) => a.id - b.id);
}
