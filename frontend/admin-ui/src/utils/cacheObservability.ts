/** Cache observability helpers for Admin UI (PEr07). */

export type CacheState = "hit" | "miss" | "bypass" | "off" | "na";

export interface CacheTelemetry {
  state: CacheState;
  cacheLayer: string | null;
  cacheLatencyMs: number | null;
  retrievalCacheGeneration: string | null;
  retrievalCacheBackend: string | null;
  keyHashPrefix: string | null;
  fingerprintBackend: string | null;
  skippedRetrieval: boolean | null;
  invalidationReason: string | null;
  evaluationCacheBypass: boolean | null;
  evaluationCachePolicy: string | null;
}

function pickBool(detailsPool: Record<string, unknown>[], keys: string[]): boolean | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const key of keys) {
      const v = d[key];
      if (v === true || v === false) return v;
      if (v === 1) return true;
      if (v === 0) return false;
    }
  }
  return null;
}

function pickText(detailsPool: Record<string, unknown>[], keys: string[]): string | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const key of keys) {
      const v = d[key];
      if (typeof v === "string" && v.trim()) return v.trim();
    }
  }
  return null;
}

function pickNumber(detailsPool: Record<string, unknown>[], keys: string[]): number | null {
  for (let i = detailsPool.length - 1; i >= 0; i--) {
    const d = detailsPool[i];
    for (const key of keys) {
      const n = Number(d[key]);
      if (Number.isFinite(n)) return n;
    }
  }
  return null;
}

export function cacheStateFromDetailsPool(
  detailsPool: Record<string, unknown>[]
): CacheState {
  const bypass = pickBool(detailsPool, ["evaluation_cache_bypass"]);
  if (bypass === true) return "bypass";
  const disabled = pickBool(detailsPool, ["retrieval_cache_disabled"]);
  if (disabled === true) return "off";
  const hit = pickBool(detailsPool, ["retrieval_cache_hit"]);
  if (hit === true) return "hit";
  const miss = pickBool(detailsPool, ["retrieval_cache_miss"]);
  if (miss === true) return "miss";
  if (hit === false && miss === false) return "na";
  if (hit != null || miss != null) return "na";
  return "na";
}

function cacheDisabledByLogHints(detailsPool: Record<string, unknown>[]): boolean {
  const wrapper = pickText(detailsPool, ["backend_wrapper_class"]);
  if (!wrapper?.trim()) return false;
  if (wrapper === "CachingRetrievalBackend") return false;
  const hit = pickBool(detailsPool, ["retrieval_cache_hit"]);
  const miss = pickBool(detailsPool, ["retrieval_cache_miss"]);
  return hit == null && miss == null;
}

/** Map unknown/missing telemetry to OFF when cache is globally disabled (not N/A). */
export function resolveCacheDisplayState(
  state: CacheState,
  options?: {
    retrievalCacheGloballyEnabled?: boolean | null;
    detailsPool?: Record<string, unknown>[];
  }
): CacheState {
  if (state === "bypass" || state === "hit" || state === "miss" || state === "off") {
    return state;
  }
  if (options?.detailsPool && cacheDisabledByLogHints(options.detailsPool)) {
    return "off";
  }
  if (options?.retrievalCacheGloballyEnabled === false) {
    return "off";
  }
  return state;
}

export function isRetrievalCacheGloballyEnabled(raw: unknown): boolean {
  return raw === true || raw === "true" || raw === 1 || raw === "1";
}

export function extractCacheTelemetry(
  detailsPool: Record<string, unknown>[],
  options?: { retrievalCacheGloballyEnabled?: boolean | null }
): CacheTelemetry {
  const rawState = cacheStateFromDetailsPool(detailsPool);
  const state = resolveCacheDisplayState(rawState, {
    retrievalCacheGloballyEnabled: options?.retrievalCacheGloballyEnabled,
    detailsPool,
  });
  return {
    state,
    cacheLayer: pickText(detailsPool, ["cache_layer"]),
    cacheLatencyMs: pickNumber(detailsPool, ["cache_latency_ms"]),
    retrievalCacheGeneration: pickText(detailsPool, ["retrieval_cache_generation"]),
    retrievalCacheBackend: pickText(detailsPool, [
      "retrieval_cache_backend",
      "retrieval_cache_fingerprint_backend",
    ]),
    keyHashPrefix: pickText(detailsPool, ["retrieval_cache_key_hash_prefix"]),
    fingerprintBackend: pickText(detailsPool, ["retrieval_cache_fingerprint_backend"]),
    skippedRetrieval: pickBool(detailsPool, ["skipped_retrieval"]),
    invalidationReason: pickText(detailsPool, ["cache_invalidation_reason"]),
    evaluationCacheBypass: pickBool(detailsPool, ["evaluation_cache_bypass"]),
    evaluationCachePolicy: pickText(detailsPool, ["evaluation_cache_policy"]),
  };
}

export function cacheStateLabelRu(state: CacheState): string {
  switch (state) {
    case "hit":
      return "кэш: hit";
    case "miss":
      return "кэш: miss";
    case "bypass":
      return "кэш: bypass";
    case "off":
      return "кэш: off";
    default:
      return "кэш: нет данных";
  }
}

/** Cache was active for this session (lookup ran with cache enabled). */
export function isCacheLookupActive(state: CacheState): boolean {
  return state === "hit" || state === "miss";
}

/** Latency/state comparison between sessions is meaningful only when cache participated in both. */
export function isCacheSessionComparisonAllowed(
  currentState: CacheState,
  previousState: CacheState | null
): boolean {
  if (!previousState) return false;
  return isCacheLookupActive(currentState) && isCacheLookupActive(previousState);
}

export function cacheStateBadgeText(state: CacheState): string {
  switch (state) {
    case "hit":
      return "HIT";
    case "miss":
      return "MISS";
    case "bypass":
      return "BYPASS";
    case "off":
      return "OFF";
    default:
      return "N/A";
  }
}

export function collapseComparableQueryText(s: string | null | undefined): string {
  return (s ?? "").replace(/\s+/g, " ").trim().toLowerCase();
}

export interface ComparableSession {
  executionId: string;
  lastAt: number;
  query: string | null;
  retrievalReadyQuery: string | null;
  cacheState: CacheState;
  retrievalLatencyMs: number | null;
  cacheTelemetry: CacheTelemetry;
}

export function sessionComparableQuery(s: {
  query: string | null;
  retrievalReadyQuery?: string | null;
}): string {
  const rq = collapseComparableQueryText(s.retrievalReadyQuery);
  if (rq) return rq;
  return collapseComparableQueryText(s.query);
}

/** Previous session in window with the same normalized query (strictly older). */
export function findPreviousMatchingSession<T extends ComparableSession>(
  sessions: T[],
  current: T
): T | null {
  const key = sessionComparableQuery(current);
  if (!key) return null;
  let best: T | null = null;
  for (const s of sessions) {
    if (s.executionId === current.executionId) continue;
    if (sessionComparableQuery(s) !== key) continue;
    if (s.lastAt >= current.lastAt) continue;
    if (!best || s.lastAt > best.lastAt) best = s;
  }
  return best;
}

export function formatCacheEnabledLabel(raw: unknown): string {
  if (raw === true || raw === "true" || raw === 1 || raw === "1") return "ON";
  if (raw === false || raw === "false" || raw === 0 || raw === "0") return "OFF";
  return "—";
}
