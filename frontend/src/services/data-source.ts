import type { OperatorDataSource } from "./contracts";
import { ExistingBackendAdapter } from "./existing-backend-adapter";
import { PlannedBackendAdapter } from "./planned-backend-adapter";

type DataSourceKind = "backend" | "planned-backend";

function createOperatorDataSource(kind: DataSourceKind): OperatorDataSource {
  const config = {
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
    wsBaseUrl: import.meta.env.VITE_WS_BASE_URL ?? "",
  };

  if (kind === "planned-backend") {
    return new PlannedBackendAdapter(config);
  }

  return new ExistingBackendAdapter(config);
}

const configuredKind = import.meta.env.VITE_DATA_SOURCE ?? "backend";

if (!["backend", "planned-backend"].includes(configuredKind)) {
  throw new Error(`Desteklenmeyen veri kaynağı: ${configuredKind}`);
}

export const operatorDataSource = createOperatorDataSource(configuredKind as DataSourceKind);
