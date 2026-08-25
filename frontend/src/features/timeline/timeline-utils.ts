import type { RiskLevel, TimelineEvent } from "../../types";

export type TimelineFilter = "all" | "critical" | "high" | `target:${number}`;

export interface TimelineGroup {
  id: string;
  timeSeconds: number;
  events: TimelineEvent[];
}

const riskPriority: Record<RiskLevel, number> = { critical: 5, high: 4, medium: 3, low: 2, info: 1, unknown: 0 };

function safeSeconds(value: number): number { return Number.isFinite(value) ? Math.max(0, value) : 0; }

export function formatEventTime(seconds: number): string {
  const whole = Math.floor(safeSeconds(seconds));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remaining = whole % 60;
  return hours > 0
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}

export function getEventTimeLabel(event: TimelineEvent): string {
  return event.timeLabel?.trim() || formatEventTime(event.timeSeconds);
}

export function sortTimelineEvents(events: TimelineEvent[]): TimelineEvent[] {
  const unique = new Map<string, TimelineEvent>();
  for (const event of events) if (!unique.has(event.id)) unique.set(event.id, event);
  return [...unique.values()].sort((a, b) => safeSeconds(a.timeSeconds) - safeSeconds(b.timeSeconds) || a.id.localeCompare(b.id));
}

export function filterTimelineEvents(events: TimelineEvent[], filter: TimelineFilter): TimelineEvent[] {
  if (filter === "critical") return events.filter((event) => event.critical);
  if (filter === "high") return events.filter((event) => event.risk === "high" && !event.critical);
  if (filter.startsWith("target:")) {
    const targetId = Number(filter.slice(7));
    return events.filter((event) => event.targetId === targetId && targetId !== -1);
  }
  return events;
}

export function groupTimelineEvents(events: TimelineEvent[]): TimelineGroup[] {
  const groups = new Map<number, TimelineEvent[]>();
  for (const event of sortTimelineEvents(events)) {
    const second = Math.floor(safeSeconds(event.timeSeconds));
    groups.set(second, [...(groups.get(second) ?? []), event]);
  }
  return [...groups.entries()].map(([second, groupEvents]) => ({
    id: `timeline-${second}`,
    timeSeconds: second,
    events: [...groupEvents].sort((a, b) => Number(b.critical) - Number(a.critical) || riskPriority[b.risk] - riskPriority[a.risk] || safeSeconds(a.timeSeconds) - safeSeconds(b.timeSeconds) || a.id.localeCompare(b.id)),
  }));
}

export function getTimelineScale(events: TimelineEvent[], durationSeconds?: number): { seconds: number; provisional: boolean } {
  if (durationSeconds !== undefined && Number.isFinite(durationSeconds) && durationSeconds > 0) return { seconds: durationSeconds, provisional: false };
  const maximum = events.reduce((max, event) => Math.max(max, safeSeconds(event.timeSeconds)), 0);
  return { seconds: maximum || 1, provisional: true };
}

export function getEventPosition(timeSeconds: number, scaleSeconds: number): number {
  if (!Number.isFinite(timeSeconds) || !Number.isFinite(scaleSeconds) || scaleSeconds <= 0) return 0;
  return Math.min(100, Math.max(0, timeSeconds / scaleSeconds * 100));
}

export function getEventAriaLabel(event: TimelineEvent, index: number, total: number, riskLabel: string): string {
  const target = event.targetId !== undefined && event.targetId !== -1 ? `Hedef #${event.targetId}` : "Video Geneli";
  return `${total} olaydan ${index + 1}. olay, ${getEventTimeLabel(event)}, ${event.title}, ${riskLabel}, ${target}`;
}
