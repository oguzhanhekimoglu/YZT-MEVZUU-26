import type { TimelineEvent } from "../../types";
import { filterTimelineEvents, formatEventTime, getEventAriaLabel, getEventPosition, getTimelineScale, groupTimelineEvents, sortTimelineEvents } from "./timeline-utils";

const event = (id: string, timeSeconds: number, overrides: Partial<TimelineEvent> = {}): TimelineEvent => ({ id, timeSeconds, timeLabel: "", title: id, description: `${id} açıklaması`, risk: "info", critical: false, status: "completed", ...overrides });

describe("timeline-utils", () => {
  it("zamanı güvenli biçimler", () => { expect(formatEventTime(65)).toBe("01:05"); expect(formatEventTime(3661)).toBe("01:01:01"); expect(formatEventTime(Number.NaN)).toBe("00:00"); });
  it("zaman ve ID ile sıralayıp aynı ID'yi tekilleştirir", () => { const sorted = sortTimelineEvents([event("b", 9), event("a", 9), event("late", 20), event("a", 2)]); expect(sorted.map((item) => item.id)).toEqual(["a", "b", "late"]); expect(sorted[0]?.timeSeconds).toBe(9); });
  it("kritik yüksek ve hedef filtrelerini uygular", () => { const events = [event("critical", 1, { critical: true, risk: "critical" }), event("high", 2, { risk: "high" }), event("target", 3, { targetId: 4 }), event("ghost", 4, { targetId: -1 })]; expect(filterTimelineEvents(events, "critical").map((item) => item.id)).toEqual(["critical"]); expect(filterTimelineEvents(events, "high").map((item) => item.id)).toEqual(["high"]); expect(filterTimelineEvents(events, "target:4").map((item) => item.id)).toEqual(["target"]); expect(filterTimelineEvents(events, "target:-1")).toEqual([]); });
  it("aynı saniyedeki olayları deterministik kümeler", () => { const groups = groupTimelineEvents([event("medium", 5.2, { risk: "medium" }), event("critical", 5.8, { risk: "critical", critical: true }), event("later", 6)]); expect(groups).toHaveLength(2); expect(groups[0]?.events.map((item) => item.id)).toEqual(["critical", "medium"]); });
  it("konumu güvenli sınırlar", () => { expect(getEventPosition(25, 100)).toBe(25); expect(getEventPosition(-10, 100)).toBe(0); expect(getEventPosition(120, 100)).toBe(100); expect(getEventPosition(Number.NaN, 100)).toBe(0); });
  it("bilinmeyen sürede geçici ölçek kullanır", () => { expect(getTimelineScale([event("one", 12), event("two", 30)])).toEqual({ seconds: 30, provisional: true }); expect(getTimelineScale([], undefined)).toEqual({ seconds: 1, provisional: true }); expect(getTimelineScale([], 70)).toEqual({ seconds: 70, provisional: false }); });
  it("erişilebilir adı tüm bağlamla oluşturur", () => { expect(getEventAriaLabel(event("Kimlik belirlendi", 18, { timeLabel: "00:18", targetId: 4 }), 1, 3, "Bilgi")).toBe("3 olaydan 2. olay, 00:18, Kimlik belirlendi, Bilgi, Hedef #4"); });
});
