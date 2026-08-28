import type { OperatorCapabilities } from "./contracts";

export const existingBackendCapabilities: OperatorCapabilities = {
  localFilePreview: true, videoUpload: true, liveCamera: true, serverPathStart: true, start: true,
  pause: false, resume: false, stop: true, restart: false, mjpegStream: true,
  liveTargets: true, persistentEvents: false, finalOutput: false, referenceImages: true,
  metrics: false, eventSnapshots: false, seekToEvent: false,
};
