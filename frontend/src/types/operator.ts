export type ProcessStatus =
  | "waiting"
  | "running"
  | "completed"
  | "warning"
  | "error";

export type RiskLevel =
  | "info"
  | "low"
  | "medium"
  | "high"
  | "critical"
  | "unknown";

export type SessionStatus =
  | "idle"
  | "file-selected"
  | "uploading"
  | "preparing"
  | "running"
  | "paused"
  | "stopped"
  | "completed"
  | "error";

export interface AircraftCandidate {
  model: string;
  score: number;
  country?: string;
  role?: string;
  referenceImageUrl?: string;
}

export interface DetectionDetail {
  targetId: number;
  className: string;
  confidence: number;
  trackingStatus: "active" | "lost" | "completed";
  hits: number;
  speedPxS?: number;
  zigzagScore?: number;
}

export interface VragDetail {
  model?: string;
  score?: number;
  lowConfidence: boolean;
  margin?: number;
  country?: string;
  manufacturer?: string;
  role?: string;
  category?: string;
  referenceImageUrl?: string;
  candidates: AircraftCandidate[];
}

export interface VlmDetail {
  visualPrediction?: string;
  vehicleType?: string;
  vehicleClass?: string;
  countryHypothesis?: string;
  threatHypothesis?: RiskLevel;
  verification?: string;
  vragConsistency?: string;
  visualAssessment?: string;
}

export interface ActionRecommendation {
  id: string;
  label: string;
  priority: "urgent" | "high" | "normal";
  reason?: string;
  requiresConfirmation?: boolean;
}

export interface LlmDetail {
  risk: RiskLevel;
  decision?: string;
  inventoryStatus?: string;
  permissionStatus?: string;
  flightPlanStatus?: string;
  notamStatus?: string;
  humanReviewRequired?: boolean;
  summary?: string;
  riskIncreasingFactors: string[];
  riskReducingFactors: string[];
  actions: ActionRecommendation[];
}

export interface AnalysisStep<T = unknown> {
  id: "detection" | "vrag" | "vlm" | "llm" | "final";
  title: string;
  status: ProcessStatus;
  statusText: string;
  summary?: string;
  durationMs?: number;
  updatedAt?: string;
  warning?: string;
  error?: string;
  substeps?: Array<{
    id: string;
    label: string;
    status: ProcessStatus;
  }>;
  detail?: T;
}

export interface TargetAnalysis {
  id: number;
  displayName: string;
  className: string;
  detectionConfidence: number;
  risk: RiskLevel;
  selected: boolean;
  trackingBox?: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  detection: AnalysisStep<DetectionDetail>;
  vrag: AnalysisStep<VragDetail>;
  vlm: AnalysisStep<VlmDetail>;
  llm: AnalysisStep<LlmDetail>;
}

export interface TimelineEvent {
  id: string;
  targetId?: number;
  timeSeconds: number;
  timeLabel: string;
  startSeconds?: number;
  endSeconds?: number;
  title: string;
  description: string;
  risk: RiskLevel;
  critical: boolean;
  confidence?: number;
  status: "active" | "completed";
  relatedStep?: AnalysisStep["id"];
  snapshotUrl?: string;
  actions?: ActionRecommendation[];
}

export interface FinalOutput {
  status: "pending" | "provisional" | "final" | "partial";
  summary: string;
  aircraft?: {
    model?: string;
    countryOrigin?: string;
    manufacturer?: string;
    role?: string;
    vehicleClass?: string;
    identityConfidence?: number;
  };
  events: TimelineEvent[];
  risk: RiskLevel;
  riskReason?: string;
  actions: ActionRecommendation[];
  generatedAt?: string;
}

export interface SystemPerformance {
  processingSeconds: number;
  inferenceMs: number;
  framesPerSecond: number;
  droppedFrameRate: number;
  memoryGb: number;
  gpuUtilization: number;
  queueDepth: number;
  health: "stable" | "strained" | "critical";
  eventDetectionAccuracy?: number;
  criticalEventRecall?: number;
  summaryQuality?: number;
  actionAccuracy?: number;
  validationScenarioCount?: number;
  measuredAt?: string;
  loadTest?: {
    parallelVideos: number;
    resolution: string;
    averageFramesPerSecond: number;
    droppedFrameRate: number;
    result: "stable" | "strained" | "critical";
  };
}

export interface OperatorSession {
  id: string;
  status: SessionStatus;
  connection: "connecting" | "connected" | "reconnecting" | "disconnected";
  localMode: boolean;
  sourceName?: string;
  durationSeconds?: number;
  currentSeconds: number;
  progress?: number;
  frameNumber: number;
  activeTargetCount: number;
  criticalEventCount: number;
  streamUrl?: string;
  selectedTargetId?: number;
  targets: TargetAnalysis[];
  events: TimelineEvent[];
  finalOutput: FinalOutput;
  performance?: SystemPerformance;
  lastMessageAt?: string;
}
