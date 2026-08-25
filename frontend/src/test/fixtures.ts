import type {
  AnalysisStep,
  FinalOutput,
  OperatorSession,
  TargetAnalysis,
  TimelineEvent,
} from "../types";

export const timelineEvents: TimelineEvent[] = [
  {
    id: "target-detected",
    targetId: 4,
    timeSeconds: 18,
    timeLabel: "00:18",
    title: "Hedef ilk kez görüldü",
    description: "Hedef #4 görüntü alanında tespit edildi.",
    risk: "info",
    critical: false,
    confidence: 0.91,
    status: "completed",
    relatedStep: "detection",
  },
  {
    id: "matching-started",
    targetId: 4,
    timeSeconds: 24,
    timeLabel: "00:24",
    title: "Model eşleştirmesi başladı",
    description: "Hedef #4 için yerel referans kayıtları taranıyor.",
    risk: "info",
    critical: false,
    status: "completed",
    relatedStep: "vrag",
  },
  {
    id: "identity-determined",
    targetId: 4,
    timeSeconds: 29,
    timeLabel: "00:29",
    title: "Hava aracı kimliği belirlendi",
    description: "En iyi model eşleşmesi F-16 Fighting Falcon olarak belirlendi.",
    risk: "low",
    critical: false,
    confidence: 0.91,
    status: "completed",
    relatedStep: "vrag",
  },
  {
    id: "vlm-verified",
    targetId: 4,
    timeSeconds: 36,
    timeLabel: "00:36",
    title: "VLM doğrulaması tamamlandı",
    description: "Görsel doğrulama, model eşleştirmesiyle tutarlı sonuç verdi.",
    risk: "low",
    critical: false,
    status: "completed",
    relatedStep: "vlm",
  },
  {
    id: "risk-increased",
    targetId: 7,
    timeSeconds: 42,
    timeLabel: "00:42",
    title: "Risk seviyesi yükseldi",
    description: "Hedef #7 için operatör incelemesi gerekiyor.",
    risk: "high",
    critical: false,
    status: "active",
    relatedStep: "llm",
  },
  {
    id: "critical-review",
    targetId: 4,
    timeSeconds: 51,
    timeLabel: "00:51",
    title: "Operatör teyidi gerekiyor",
    description: "Operasyonel kayıtların manuel doğrulanması gerekiyor.",
    risk: "high",
    critical: false,
    status: "active",
    relatedStep: "llm",
  },
  {
    id: "critical-state",
    targetId: 4,
    timeSeconds: 51.1,
    timeLabel: "00:51",
    title: "Kritik durum oluştu",
    description: "Operasyonel kayıt eksikleri nedeniyle kritik inceleme durumu oluştu.",
    risk: "critical",
    critical: true,
    status: "active",
    relatedStep: "final",
  },
  {
    id: "permission-mismatch",
    targetId: 4,
    timeSeconds: 51.2,
    timeLabel: "00:51",
    title: "Operasyonel kayıt uyuşmazlığı",
    description: "Uçuş izni ve uçuş planı kayıtları doğrulanamadı.",
    risk: "high",
    critical: false,
    status: "completed",
    relatedStep: "llm",
  },
  {
    id: "identity-confidence-drop",
    targetId: 7,
    timeSeconds: 51.7,
    timeLabel: "00:51",
    title: "Kimlik güveninde düşüş",
    description: "Hedef #7 kimlik güveninde anlamlı düşüş görüldü.",
    risk: "medium",
    critical: false,
    confidence: 0.62,
    status: "active",
    relatedStep: "vrag",
  },
  {
    id: "analysis-completed",
    timeSeconds: 70,
    timeLabel: "01:10",
    title: "Analiz tamamlandı",
    description: "Video geneli canonical nihai çıktı hazırlandı.",
    risk: "info",
    critical: false,
    status: "completed",
    relatedStep: "final",
  },
];

export const denseTimelineEvents: TimelineEvent[] = Array.from({ length: 30 }, (_, index) => ({
  id: `dense-event-${index + 1}`,
  targetId: index % 3 === 0 ? 7 : index % 2 === 0 ? 4 : undefined,
  timeSeconds: 3 + index * 2,
  timeLabel: formatFixtureTime(3 + index * 2),
  title: `Yoğun senaryo olayı ${index + 1}`,
  description: "Timeline yoğunluk ve taşma davranışı için deterministik test olayı.",
  risk: index % 10 === 0 ? "critical" : index % 4 === 0 ? "high" : index % 3 === 0 ? "medium" : "info",
  critical: index % 10 === 0,
  status: "completed",
  relatedStep: index % 2 === 0 ? "detection" : "llm",
}));

const conflictTimelineEvents: TimelineEvent[] = [...timelineEvents, { id: "vrag-vlm-conflict", targetId: 4, timeSeconds: 38, timeLabel: "00:38", title: "VRAG/VLM çelişkisi oluştu", description: "Model eşleştirmesi ile görsel doğrulama farklı kimlik sonuçları verdi.", risk: "medium", critical: false, status: "completed", relatedStep: "vlm" }];
const vlmErrorTimelineEvents: TimelineEvent[] = [...timelineEvents.slice(0, 4), { id: "vlm-service-error", targetId: 4, timeSeconds: 37, timeLabel: "00:37", title: "VLM doğrulaması tamamlanamadı", description: "Yerel VLM servisi sonuç üretemedi; analiz kısmi olarak korunuyor.", risk: "unknown", critical: false, status: "completed", relatedStep: "vlm" }];
const llmErrorTimelineEvents: TimelineEvent[] = [...timelineEvents.slice(0, 5), { id: "llm-service-error", targetId: 4, timeSeconds: 44, timeLabel: "00:44", title: "Karar desteği tamamlanamadı", description: "Operasyonel karar servisi sonuç üretemedi; nihai risk belirlenemedi.", risk: "unknown", critical: false, status: "completed", relatedStep: "llm" }];

function formatFixtureTime(seconds: number): string {
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function step<T>(
  id: AnalysisStep["id"],
  title: string,
  status: AnalysisStep["status"],
  detail?: T,
): AnalysisStep<T> {
  const labels: Record<AnalysisStep["status"], string> = { waiting: "Bekliyor", running: "Çalışıyor", completed: "Tamamlandı", warning: "Uyarılı", error: "Hata" };
  return { id, title, status, statusText: labels[status], detail };
}

export const testTargets: TargetAnalysis[] = [
  {
    id: 4,
    displayName: "F-16 Fighting Falcon",
    className: "Askerî uçak",
    detectionConfidence: 0.91,
    risk: "medium",
    selected: true,
    trackingBox: { x: 0.48, y: 0.27, width: 0.23, height: 0.34 },
    detection: { ...step("detection", "Nesne Tespiti", "completed", {
      targetId: 4,
      className: "Askerî uçak",
      confidence: 0.91,
      trackingStatus: "active",
      hits: 38,
      speedPxS: 24.7,
      zigzagScore: 0.12,
    }), summary: "Hedef #4 · Askerî uçak · Güven %91", durationMs: 30 },
    vrag: { ...step("vrag", "VRAG Model Eşleştirmesi", "completed", {
      model: "F-16 Fighting Falcon",
      score: 0.91,
      lowConfidence: false,
      country: "ABD",
      manufacturer: "Lockheed Martin",
      role: "Çok amaçlı savaş uçağı",
      category: "Askerî uçak",
      margin: 0.13,
      candidates: [
        { model: "F-16 Fighting Falcon", score: 0.91, country: "ABD" },
        { model: "F-15 Eagle", score: 0.78, country: "ABD" },
        { model: "F-16 Fighting Falcon", score: 0.84, country: "ABD" },
        { model: "F/A-18 Hornet", score: 0.72, country: "ABD" },
      ],
    }), summary: "F-16 Fighting Falcon · Benzerlik %91", durationMs: 400 },
    vlm: { ...step("vlm", "VLM Görsel Doğrulama", "completed", {
      visualPrediction: "F-16 Fighting Falcon",
      vehicleType: "Askerî uçak",
      vehicleClass: "Sabit kanat",
      countryHypothesis: "Türkiye",
      threatHypothesis: "low",
      verification: "Onaylandı",
      vragConsistency: "Tutarlı",
      visualAssessment: "Görüntüde F-16 Fighting Falcon savaş uçağı görülmektedir. Görsel özellikler VRAG eşleşmesini desteklemektedir.",
    }), summary: "Askerî uçak · Sabit kanat · Sonuç tutarlı", durationMs: 4200 },
    llm: { ...step("llm", "LLM Karar Desteği", "running", {
      risk: "medium",
      humanReviewRequired: true,
      riskIncreasingFactors: [],
      riskReducingFactors: [],
      actions: [],
    }), summary: "Risk ve operasyonel durum değerlendiriliyor...", durationMs: 1800, substeps: [
      { id: "platform", label: "Platform kaydı kontrol edildi", status: "completed" },
      { id: "inventory", label: "Türkiye envanteri kontrol edildi", status: "completed" },
      { id: "permission", label: "Uçuş izni ve uçuş planı inceleniyor", status: "running" },
      { id: "notam", label: "NOTAM kontrolü bekliyor", status: "waiting" },
      { id: "risk", label: "Nihai risk değerlendirmesi bekliyor", status: "waiting" },
      { id: "actions", label: "Aksiyon önerileri bekliyor", status: "waiting" },
    ] },
  },
  {
    id: 7,
    displayName: "Bilinmeyen hava aracı",
    className: "Hava aracı",
    detectionConfidence: 0.67,
    risk: "high",
    selected: false,
    trackingBox: { x: 0.16, y: 0.39, width: 0.18, height: 0.27 },
    detection: step("detection", "Nesne Tespiti", "completed", {
      targetId: 7,
      className: "Hava aracı",
      confidence: 0.67,
      trackingStatus: "active",
      hits: 16,
    }),
    vrag: step("vrag", "VRAG Model Eşleştirmesi", "running", {
      lowConfidence: true,
      candidates: [],
    }),
    vlm: step("vlm", "VLM Görsel Doğrulama", "running", {}),
    llm: step("llm", "LLM Karar Desteği", "running", {
      risk: "high",
      riskIncreasingFactors: [],
      riskReducingFactors: [],
      actions: [],
    }),
  },
  {
    id: -1,
    displayName: "Korunan sonuç",
    className: "Sistem kaydı",
    detectionConfidence: 0,
    risk: "unknown",
    selected: false,
    detection: step("detection", "Nesne Tespiti", "completed"),
    vrag: step("vrag", "VRAG Model Eşleştirmesi", "completed"),
    vlm: step("vlm", "VLM Görsel Doğrulama", "completed"),
    llm: step("llm", "LLM Karar Desteği", "completed"),
  },
];

export const provisionalOutput: FinalOutput = {
  status: "provisional",
  summary: "Görüntüde iki hava aracı tespit edildi. Kimlik ve operasyonel kayıt kontrolleri test senaryosunda sürüyor.",
  events: timelineEvents,
  risk: "medium",
  riskReason: "Kimlik ve operasyonel izin doğrulamaları henüz tamamlanmadı.",
  actions: [
    { id: "track", label: "Takibi kesintisiz sürdür", priority: "urgent" },
    { id: "verify", label: "Operatör doğrulaması gerçekleştir", priority: "high" },
  ],
};

export const finalOutput: FinalOutput = {
  ...provisionalOutput,
  status: "final",
  summary: "Videoda F-16 Fighting Falcon olarak değerlendirilen bir hava aracı tespit edilmiştir. Görsel doğrulama kimlik sonucunu desteklemiş, operasyonel kayıt eksikleri nedeniyle genel risk Orta belirlenmiştir.",
  aircraft: {
    model: "F-16 Fighting Falcon",
    countryOrigin: "ABD",
    manufacturer: "Lockheed Martin",
    role: "Çok amaçlı savaş uçağı",
    vehicleClass: "Sabit kanat",
    identityConfidence: 0.91,
  },
  riskReason: "Uçuş izni ve uçuş planı doğrulanamadığı için operatör teyidi gereklidir.",
  actions: [
    { id: "track", label: "Takibi kesintisiz sürdür", priority: "urgent" },
    { id: "verify", label: "Operatör doğrulaması gerçekleştir", priority: "high" },
    { id: "permission", label: "İzin kayıtlarını kontrol et", priority: "normal" },
  ],
  generatedAt: "2026-08-13T12:00:14.000Z",
};

const completedTargets: TargetAnalysis[] = testTargets.map((target) => target.id !== 4 ? target : {
  ...target,
  llm: {
    ...target.llm,
    status: "completed",
    statusText: "Tamamlandı",
    summary: "Orta risk · Operatör teyidi gerekli",
    durationMs: 5900,
    substeps: target.llm.substeps?.map((substep) => ({ ...substep, status: "completed" })),
    detail: {
      risk: "medium",
      decision: "Operatör teyidi gerekli",
      inventoryStatus: "Kayıtlı",
      permissionStatus: "Doğrulanamadı",
      flightPlanStatus: "Bulunamadı",
      notamStatus: "Aktif kayıt bulunamadı",
      humanReviewRequired: true,
      summary: "Platform kimliği ve operasyonel kayıtlar değerlendirilmiştir. İlgili zaman ve saha için uçuş izni ile uçuş planı doğrulanamadığından operatör teyidi gerekmektedir.",
      riskIncreasingFactors: ["Uçuş izni doğrulanamadı", "Uçuş planı bulunamadı"],
      riskReducingFactors: ["Platform envanterde kayıtlı", "VRAG ve VLM sonuçları tutarlı"],
      actions: finalOutput.actions,
    },
  },
});

export const idleSessionFixture: OperatorSession = {
  id: "fixture-idle-session",
  status: "idle",
  connection: "connected",
  localMode: true,
  currentSeconds: 0,
  frameNumber: 0,
  activeTargetCount: 0,
  criticalEventCount: 0,
  targets: [],
  events: [],
  finalOutput: { status: "pending", summary: "", events: [], risk: "unknown", actions: [] },
};

export const preparingSessionFixture: OperatorSession = {
  ...idleSessionFixture,
  id: "fixture-preparing-session",
  status: "preparing",
};

export const runningSessionFixture: OperatorSession = {
  ...idleSessionFixture,
  id: "fixture-running-session",
  status: "running",
  currentSeconds: 42,
  durationSeconds: 70,
  progress: 0.6,
  frameNumber: 1050,
  activeTargetCount: 2,
  criticalEventCount: 1,
  selectedTargetId: 4,
  targets: testTargets,
  events: timelineEvents.slice(0, 8),
  finalOutput: provisionalOutput,
  performance: {
    processingSeconds: 42,
    inferenceMs: 38,
    framesPerSecond: 24.8,
    droppedFrameRate: 0.4,
    memoryGb: 4.2,
    gpuUtilization: 68,
    queueDepth: 3,
    health: "stable",
  },
};

export const completedSessionFixture: OperatorSession = {
  ...runningSessionFixture,
  id: "fixture-completed-session",
  status: "completed",
  currentSeconds: 70,
  progress: 1,
  targets: completedTargets,
  finalOutput,
  events: timelineEvents,
  performance: {
    ...runningSessionFixture.performance!,
    processingSeconds: 70,
    eventDetectionAccuracy: 94,
    criticalEventRecall: 100,
    summaryQuality: 91,
    actionAccuracy: 89,
    validationScenarioCount: 24,
    measuredAt: "2026-08-14T12:00:00.000Z",
    loadTest: { parallelVideos: 4, resolution: "1080p", averageFramesPerSecond: 22.6, droppedFrameRate: 1.2, result: "stable" },
  },
};

export const detectionSessionFixture: OperatorSession = {
  ...runningSessionFixture,
  id: "fixture-detection-session",
  currentSeconds: 18,
  events: timelineEvents.slice(0, 1),
  targets: testTargets.map((target) => target.id !== 4 ? target : {
    ...target,
    vrag: step("vrag", "VRAG Model Eşleştirmesi", "waiting", { lowConfidence: false, candidates: [] }),
    vlm: step("vlm", "VLM Görsel Doğrulama", "waiting", {}),
    llm: step("llm", "LLM Karar Desteği", "waiting", { risk: "unknown", riskIncreasingFactors: [], riskReducingFactors: [], actions: [] }),
  }),
  finalOutput: { status: "pending", summary: "", events: [], risk: "unknown", actions: [] },
};

export const vragRunningSessionFixture: OperatorSession = {
  ...detectionSessionFixture,
  id: "fixture-vrag-session",
  currentSeconds: 24,
  events: timelineEvents.slice(0, 2),
  targets: detectionSessionFixture.targets.map((target) => target.id !== 4 ? target : { ...target, vrag: step("vrag", "VRAG Model Eşleştirmesi", "running", { lowConfidence: false, candidates: [] }) }),
};

export const vlmRunningSessionFixture: OperatorSession = {
  ...runningSessionFixture,
  id: "fixture-vlm-session",
  currentSeconds: 31,
  events: timelineEvents.slice(0, 3),
  targets: testTargets.map((target) => target.id !== 4 ? target : { ...target, vlm: { ...target.vlm, status: "running", statusText: "Çalışıyor", detail: {} }, llm: step("llm", "LLM Karar Desteği", "waiting", { risk: "unknown", riskIncreasingFactors: [], riskReducingFactors: [], actions: [] }) }),
  finalOutput: { status: "pending", summary: "", events: [], risk: "unknown", actions: [] },
};

export const lowConfidenceSessionFixture: OperatorSession = {
  ...completedSessionFixture,
  id: "fixture-low-confidence",
  targets: completedTargets.map((target) => target.id !== 4 ? target : { ...target, vrag: { ...target.vrag, status: "warning", statusText: "Uyarılı", warning: "Düşük kimlik güveni", detail: { ...target.vrag.detail!, lowConfidence: true, margin: 0.03 } } }),
};

export const conflictSessionFixture: OperatorSession = {
  ...completedSessionFixture,
  id: "fixture-conflict",
  targets: completedTargets.map((target) => target.id !== 4 ? target : { ...target, vlm: { ...target.vlm, status: "warning", statusText: "Uyarılı", warning: "Görsel doğrulama çelişkisi", detail: { ...target.vlm.detail!, visualPrediction: "F-15 Eagle", vragConsistency: "Çelişkili", verification: "Belirsiz" } } }),
  events: conflictTimelineEvents,
  finalOutput: { ...finalOutput, events: conflictTimelineEvents },
};

export const vlmErrorSessionFixture: OperatorSession = {
  ...completedSessionFixture,
  id: "fixture-vlm-error",
  targets: completedTargets.map((target) => target.id !== 4 ? target : { ...target, vlm: { id: "vlm", title: "VLM Görsel Doğrulama", status: "error", statusText: "Hata", error: "Yerel VLM servisine ulaşılamadı" } }),
  events: vlmErrorTimelineEvents,
  finalOutput: { ...finalOutput, status: "partial", events: vlmErrorTimelineEvents, riskReason: "VLM sonucu üretilemedi. VRAG sonucu mevcut olduğu için analiz kısmi olarak devam etti." },
};

export const llmErrorSessionFixture: OperatorSession = {
  ...completedSessionFixture,
  id: "fixture-llm-error",
  targets: completedTargets.map((target) => target.id !== 4 ? target : { ...target, llm: { id: "llm", title: "LLM Karar Desteği", status: "error", statusText: "Hata", error: "Operasyonel karar servisine ulaşılamadı" } }),
  events: llmErrorTimelineEvents,
  finalOutput: { ...finalOutput, status: "partial", events: llmErrorTimelineEvents, risk: "unknown", riskReason: undefined, actions: [] },
};

export const denseTimelineSessionFixture: OperatorSession = {
  ...completedSessionFixture,
  id: "fixture-dense-timeline",
  durationSeconds: 70,
  events: denseTimelineEvents,
  finalOutput: { ...finalOutput, events: denseTimelineEvents },
};
