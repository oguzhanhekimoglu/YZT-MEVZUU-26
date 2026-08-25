import type { BackendAdapterConfig } from "./contracts";
import { UnavailableBackendAdapter } from "./unavailable-backend-adapter";

export class PlannedBackendAdapter extends UnavailableBackendAdapter {
  readonly adapterName = "Planlanan backend adaptörü";

  constructor(config: BackendAdapterConfig) {
    super(config);
  }
}
