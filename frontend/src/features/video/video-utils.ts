export const ACCEPTED_VIDEO_EXTENSIONS = ["mp4", "mov", "avi", "mkv"] as const;

export function isAcceptedVideo(file: File): boolean {
  const extension = file.name.split(".").pop()?.toLowerCase();
  return ACCEPTED_VIDEO_EXTENSIONS.includes(extension as (typeof ACCEPTED_VIDEO_EXTENSIONS)[number]);
}
