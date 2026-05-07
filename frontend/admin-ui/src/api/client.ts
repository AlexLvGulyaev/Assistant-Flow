const DEFAULT_BASE = "http://localhost:8600";

export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_ADMIN_API_BASE_URL;
  if (typeof raw === "string" && raw.trim()) {
    return raw.replace(/\/+$/, "");
  }
  return DEFAULT_BASE;
}

async function parseJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!text) {
    throw new Error(`Empty response (${res.status})`);
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`Invalid JSON (${res.status}): ${text.slice(0, 120)}`);
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/health`);
  if (!res.ok) {
    throw new Error(`Health: ${res.status} ${res.statusText}`);
  }
  return parseJson<HealthResponse>(res);
}

export async function fetchOverview(): Promise<OverviewResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/overview`);
  if (!res.ok) {
    throw new Error(`Overview: ${res.status} ${res.statusText}`);
  }
  return parseJson<OverviewResponse>(res);
}

export async function fetchRecentLogs(limit = 20): Promise<LogsRecentResponse> {
  const q = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(
    `${getApiBaseUrl()}/api/logs/recent?${q.toString()}`
  );
  if (!res.ok) {
    throw new Error(`Logs: ${res.status} ${res.statusText}`);
  }
  return parseJson<LogsRecentResponse>(res);
}

/** Mirrors admin_api/schemas — keep loose for API evolution */
export interface HealthResponse {
  status: string;
  app?: string;
  timestamp?: string;
  version?: string | null;
  build?: string | null;
  dependencies?: Record<string, unknown>;
  config_readiness?: Record<string, unknown>;
}

export interface OverviewResponse {
  database?: Record<string, unknown>;
  chroma?: Record<string, unknown>;
  rag?: Record<string, unknown>;
  supported_modalities?: string[];
  providers?: Record<string, { status?: string; detail?: string | null }>;
  asset_storage?: Record<string, unknown>;
  audio?: Record<string, unknown>;
  config_readiness?: Record<string, unknown>;
}

export interface LogItem {
  execution_id?: string | null;
  stage?: string | null;
  status?: string | null;
  created_at?: string | null;
  route?: string | null;
  mode?: string | null;
  details?: Record<string, unknown> | string | null;
}

export interface LogsRecentResponse {
  limit?: number;
  count?: number;
  items?: LogItem[];
}
