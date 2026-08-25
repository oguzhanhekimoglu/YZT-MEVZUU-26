export const ACCEPTED_VIDEO_EXTENSIONS = ["mp4", "mov", "avi", "mkv"] as const;

export interface VideoMetadataState {
  name: string;
  sizeBytes: number;
  format: string;
  durationSeconds?: number;
  width?: number;
  height?: number;
}

export function isAcceptedVideo(file: File): boolean {
  const extension = file.name.split(".").pop()?.toLowerCase();
  return ACCEPTED_VIDEO_EXTENSIONS.includes(extension as (typeof ACCEPTED_VIDEO_EXTENSIONS)[number]);
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDuration(seconds?: number): string {
  if (seconds === undefined || !Number.isFinite(seconds)) return "Okunuyor";
  const whole = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}
