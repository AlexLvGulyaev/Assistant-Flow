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

export async function fetchSummary(hours = 24): Promise<SummaryResponse> {
  const q = new URLSearchParams({ hours: String(hours) });
  const res = await fetch(`${getApiBaseUrl()}/api/summary?${q.toString()}`);
  if (!res.ok) {
    throw new Error(`Summary: ${res.status} ${res.statusText}`);
  }
  return parseJson<SummaryResponse>(res);
}

export async function fetchRecentLogs(
  options:
    | number
    | { limit?: number; offset?: number; sinceHours?: number } = 20
): Promise<LogsRecentResponse> {
  const opts =
    typeof options === "number" ? { limit: options } : options ?? {};
  const q = new URLSearchParams({ limit: String(opts.limit ?? 20) });
  if (opts.offset != null) {
    q.set("offset", String(opts.offset));
  }
  if (opts.sinceHours != null) {
    q.set("since_hours", String(opts.sinceHours));
  }
  const res = await fetch(
    `${getApiBaseUrl()}/api/logs/recent?${q.toString()}`
  );
  if (!res.ok) {
    throw new Error(`Logs: ${res.status} ${res.statusText}`);
  }
  return parseJson<LogsRecentResponse>(res);
}

export async function fetchDocuments(limit = 200): Promise<DocumentsResponse> {
  const q = new URLSearchParams({ limit: String(limit) });
  const res = await fetch(`${getApiBaseUrl()}/api/documents?${q.toString()}`);
  if (!res.ok) {
    throw new Error(`Documents: ${res.status} ${res.statusText}`);
  }
  return parseJson<DocumentsResponse>(res);
}

export async function fetchDocumentDetail(
  documentId: string,
  versionNumber?: number | null
): Promise<DocumentDetailResponse> {
  const q = new URLSearchParams();
  if (versionNumber != null && Number.isFinite(versionNumber)) {
    q.set("version_number", String(versionNumber));
  }
  const suffix = q.toString() ? `?${q.toString()}` : "";
  const res = await fetch(
    `${getApiBaseUrl()}/api/documents/${encodeURIComponent(documentId)}/detail${suffix}`
  );
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(
      `Document detail: ${res.status} ${t ? t.slice(0, 200) : res.statusText}`
    );
  }
  return parseJson<DocumentDetailResponse>(res);
}

export async function uploadDocument(file: File): Promise<UploadDocumentResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${getApiBaseUrl()}/api/documents/upload`, {
    method: "POST",
    body: fd,
  });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`Upload: ${res.status} ${t ? t.slice(0, 200) : res.statusText}`);
  }
  return parseJson<UploadDocumentResponse>(res);
}

export async function postDocumentsReindex(
  body: ReindexRequestBody
): Promise<ReindexResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/documents/reindex`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      scope: body.scope,
      document_id: body.document_id ?? null,
    }),
  });
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`Reindex: ${res.status} ${t ? t.slice(0, 200) : res.statusText}`);
  }
  return parseJson<ReindexResponse>(res);
}

export function getAssetPreviewUrl(assetRef: string): string {
  const enc = encodeURIComponent(assetRef.trim());
  return `${getApiBaseUrl()}/api/assets/preview?asset_ref=${enc}`;
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

export interface SummaryEventsBlock {
  total: number;
  success: number;
  error: number;
  other: number;
}

export interface SummarySessionsBlock {
  unique_execution_ids: number;
}

export interface SummaryRoutesBlock {
  text: number;
  rag: number;
  images: number;
  audio_voice: number;
  other_unknown: number;
}

export interface SummaryLifecycleRow {
  stage: string;
  events: number;
}

export interface TelemetrySampleBlock {
  scope?: string;
  cap?: number;
  rows_considered?: number;
  rows_in_window?: number;
  unique_execution_ids_in_sample?: number;
  tokens_total?: number | null;
  avg_latency_ms?: number | null;
  max_latency_ms?: number | null;
  top_provider_model?: string | null;
  by_provider_row_counts?: Record<string, number>;
}

export interface AudioVoiceCountsBlock {
  sessions_route_bucket: number;
  voice_pipeline_stage_events: number;
}

export interface SummaryResponse {
  hours?: number;
  events?: SummaryEventsBlock;
  sessions?: SummarySessionsBlock;
  routes?: SummaryRoutesBlock;
  lifecycle_events?: SummaryLifecycleRow[];
  telemetry_sample?: TelemetrySampleBlock;
  admin_events?: number;
  reindex_starts?: number;
  audio_voice_counts?: AudioVoiceCountsBlock;
}

export interface LogItem {
  execution_id?: string | null;
  stage?: string | null;
  status?: string | null;
  created_at?: string | null;
  route?: string | null;
  mode?: string | null;
  /** High-level modality (``text`` includes OCR). From Admin API ``log_row_to_entry``. */
  modality?: string | null;
  /** Logs filter bucket: ``text`` | ``rag`` | ``image`` | ``audio`` | ``other``. */
  modality_route?: string | null;
  details?: Record<string, unknown> | string | null;
  error_text?: string | null;
}

export interface LogsRecentResponse {
  limit?: number;
  offset?: number;
  count?: number;
  items?: LogItem[];
}

export interface DocumentItem {
  document_id: string;
  filename: string;
  extension: string;
  status: string;
  status_raw?: string;
  active_version?: number | null;
  versions_count?: number;
  chunk_count?: number;
  last_indexed_at?: string | null;
  size_bytes?: number | null;
  modified_at?: string | null;
  path_category?: string | null;
  last_indexing_event?: LogItem | null;
}

export interface DocumentsObservability {
  reindex_available?: boolean;
  last_reindex_event?: LogItem | null;
  admin_operations?: LogItem[];
  timeline_events?: LogItem[];
}

export interface DocumentsGlobalIndexSync {
  chroma_collection_chunks?: number;
  vector_index_chunks?: number;
  active_retrieval_backend?: string;
  postgres_chunks_sum_active_versions?: number | null;
  postgres_available?: boolean;
  global_chunks_mismatch?: boolean;
}

export interface DocumentsResponse {
  limit?: number;
  count?: number;
  items?: DocumentItem[];
  embedding_model?: string | null;
  global_index_sync?: DocumentsGlobalIndexSync;
  observability?: DocumentsObservability;
}

export interface DocumentDetailVersion {
  version_id?: string;
  version_number?: number;
  is_active?: boolean;
  chunk_count?: number;
  file_hash?: string | null;
  indexed_at?: string | null;
}

export interface DocumentDetailChunk {
  chunk_index?: number;
  chunk_text_preview?: string | null;
  token_count?: number | null;
  chroma_collection?: string | null;
  chroma_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at?: string | null;
}

export interface DocumentChunkCountByVersion {
  version_id?: string;
  row_count?: number;
}

export interface DocumentDetailResponse {
  document?: Record<string, unknown>;
  versions?: DocumentDetailVersion[];
  selected_version?: DocumentDetailVersion | null;
  active_version?: DocumentDetailVersion | null;
  selected_version_id?: string | null;
  chunks?: DocumentDetailChunk[];
  chunks_in_db?: number;
  chunk_count_declared?: number;
  chunks_sync_ok?: boolean;
  chunks_sync_diagnostic?: string | null;
  chunk_counts_by_version?: DocumentChunkCountByVersion[];
  text_preview?: string | null;
  preview_available?: boolean;
  embedding_model?: string | null;
  file_size_bytes?: number | null;
  timeline?: LogItem[];
  last_error_message?: string | null;
}

export interface UploadDocumentResponse {
  filename?: string;
  path?: string;
  success?: boolean;
  error?: string | null;
  chunks?: number;
  document_id?: string | null;
}

export interface ReindexRequestBody {
  scope: "all" | "document";
  document_id?: string | null;
}

export interface ReindexResponse {
  scope?: string;
  success?: boolean;
  error?: string | null;
  chunks_created?: number;
  collection_count?: number;
  files_indexed_ok?: number;
  files_found?: number;
  chunks?: number;
  document_id?: string | null;
}
