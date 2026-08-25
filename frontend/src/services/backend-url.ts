export function normalizeBaseUrl(base: string): string { return base.trim().replace(/\/+$/, ""); }

export function resolveApiUrl(base: string, path: string, origin = globalThis.location?.origin ?? "http://127.0.0.1"): string {
  const normalizedPath = `/${path.replace(/^\/+/, "")}`;
  const normalizedBase = normalizeBaseUrl(base);
  if (!normalizedBase) return new URL(normalizedPath, origin).toString();
  return `${normalizedBase}${normalizedPath}`;
}

export function resolveWebSocketUrl(explicitBase: string, path: string, locationLike: Pick<Location, "protocol" | "host"> = globalThis.location): string {
  const normalizedPath = `/${path.replace(/^\/+/, "")}`;
  const normalizedBase = normalizeBaseUrl(explicitBase);
  if (normalizedBase) return `${normalizedBase}${normalizedPath}`;
  const protocol = locationLike.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${locationLike.host}${normalizedPath}`;
}

export function safeBasename(path?: string): string | undefined {
  const value = path?.trim();
  if (!value) return undefined;
  return value.split(/[\\/]/).filter(Boolean).at(-1);
}

export function referenceImageUrl(base: string, model?: string): string | undefined {
  const value = model?.trim();
  return value ? resolveApiUrl(base, `/referans?model=${encodeURIComponent(value)}`) : undefined;
}
