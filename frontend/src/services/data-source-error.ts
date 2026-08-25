export type DataSourceErrorCode = "CONNECTION_ERROR" | "TIMEOUT" | "INVALID_RESPONSE" | "HTTP_ERROR" | "UNSUPPORTED" | "UNKNOWN";

export class DataSourceError extends Error {
  constructor(readonly code: DataSourceErrorCode, message: string, readonly recoverable: boolean, readonly status?: number, readonly detail?: string) {
    super(message);
    this.name = "DataSourceError";
  }
}

export function unsupported(operation: string): DataSourceError {
  return new DataSourceError("UNSUPPORTED", `${operation} mevcut backend sürümünde desteklenmiyor.`, false);
}
