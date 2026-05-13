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

export type FetchDocumentDetailOptions = {
  fullCanonicalText?: boolean;
  fullPreprocessingRaw?: boolean;
};

export async function fetchDocumentDetail(
  documentId: string,
  versionNumber?: number | null,
  opts?: FetchDocumentDetailOptions
): Promise<DocumentDetailResponse> {
  const q = new URLSearchParams();
  if (versionNumber != null && Number.isFinite(versionNumber)) {
    q.set("version_number", String(versionNumber));
  }
  if (opts?.fullCanonicalText) {
    q.set("full_canonical_text", "true");
  }
  if (opts?.fullPreprocessingRaw) {
    q.set("full_preprocessing_raw", "true");
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

export interface DocumentTextEditBody {
  text: string;
  editor_source?: string;
}

export interface DocumentTextEditResponse {
  success?: boolean;
  error?: string | null;
  chunks?: number | null;
  document_id?: string | null;
  edit_execution_id?: string;
  previous_version?: number;
  new_version?: number;
  expected_new_version?: number;
  editor_source?: string;
  edited_characters?: number;
  diff_size?: number;
}

export async function postDocumentTextEdit(
  documentId: string,
  body: DocumentTextEditBody
): Promise<DocumentTextEditResponse> {
  const res = await fetch(
    `${getApiBaseUrl()}/api/documents/${encodeURIComponent(documentId)}/edit-text`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: body.text,
        editor_source: body.editor_source ?? "admin_ui",
      }),
    }
  );
  if (!res.ok) {
    throw new Error(
      await parseFastApiError(res, `Сохранение текста: ${res.status}`)
    );
  }
  return parseJson<DocumentTextEditResponse>(res);
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

export async function fetchRetrievalOverview(): Promise<RetrievalOverviewResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/retrieval/overview`);
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(`Retrieval overview: ${res.status} ${t ? t.slice(0, 200) : res.statusText}`);
  }
  return parseJson<RetrievalOverviewResponse>(res);
}

async function parseFastApiError(res: Response, fallback: string): Promise<string> {
  const t = await res.text().catch(() => "");
  if (!t) return fallback;
  try {
    const j = JSON.parse(t) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) return j.detail.map((x) => JSON.stringify(x)).join("; ");
  } catch {
    /* ignore */
  }
  return `${fallback} ${t.slice(0, 240)}`;
}

export interface RetrievalTuningResponse {
  effective: Record<string, number>;
  env_defaults: Record<string, number>;
  db_overrides: Record<string, number>;
  requires_reindex_keys: string[];
  runtime_keys: string[];
  reindex_required?: boolean;
}

export async function fetchRetrievalTuning(): Promise<RetrievalTuningResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/retrieval/tuning`);
  if (!res.ok) {
    throw new Error(await parseFastApiError(res, `Retrieval tuning: ${res.status}`));
  }
  return parseJson<RetrievalTuningResponse>(res);
}

export async function putRetrievalTuning(
  patch: Record<string, number>
): Promise<RetrievalTuningResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/retrieval/tuning`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    throw new Error(await parseFastApiError(res, `Retrieval tuning save: ${res.status}`));
  }
  return parseJson<RetrievalTuningResponse>(res);
}

export async function deleteRetrievalTuning(): Promise<RetrievalTuningResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/retrieval/tuning`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(await parseFastApiError(res, `Retrieval tuning clear: ${res.status}`));
  }
  return parseJson<RetrievalTuningResponse>(res);
}

export async function setActiveRetrievalBackend(
  backend: string
): Promise<SetActiveRetrievalBackendResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/retrieval/active-backend`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ backend: backend.trim() }),
  });
  if (!res.ok) {
    let msg = `Switch backend: ${res.status}`;
    const t = await res.text().catch(() => "");
    if (t) {
      try {
        const j = JSON.parse(t) as { detail?: unknown };
        if (typeof j.detail === "string") {
          msg = j.detail;
        } else if (Array.isArray(j.detail)) {
          msg = j.detail.map((x) => JSON.stringify(x)).join("; ");
        }
      } catch {
        msg = `${msg} ${t.slice(0, 240)}`;
      }
    }
    throw new Error(msg);
  }
  return parseJson<SetActiveRetrievalBackendResponse>(res);
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

export interface RetrievalPlatformCompact {
  effective_backend?: string;
  active_readiness?: string;
  active_ok?: boolean;
  active_collection_count?: number | null;
  backends_compact?: Record<
    string,
    { ok?: boolean; count?: number | null; readiness?: string }
  >;
  reindex_recommended?: boolean;
}

export interface OverviewResponse {
  database?: Record<string, unknown>;
  chroma?: Record<string, unknown>;
  rag?: Record<string, unknown>;
  retrieval?: RetrievalPlatformCompact | Record<string, unknown>;
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
  /** Distinct execution_id in ``document`` bucket (upload / preprocess / index pipeline). */
  documents?: number;
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
  /** Logs filter bucket: ``text`` | ``rag`` | ``image`` | ``audio`` | ``document`` | ``other``. */
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

/** Merged from ``document_upload_pipeline_done`` / legacy ``admin_document_uploaded`` logs. */
export interface DocumentPreprocessingPublic {
  status?: string;
  original_format?: string | null;
  original_bytes?: number | null;
  cleaned_bytes?: number | null;
  /** PyMuPDF Phase 2: ``pdf_pymupdf`` внутри блока preprocessing в логах. */
  extractor?: string | null;
  page_count?: number | null;
  extracted_characters?: number | null;
  removed_line_count?: number | null;
  original_upload_filename?: string | null;
  indexed_target_filename?: string | null;
  preview_raw?: string | null;
  preview_cleaned?: string | null;
  error?: string | null;
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
  preprocessing?: DocumentPreprocessingPublic | null;
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
  retrieval_operational?: RetrievalPlatformCompact;
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
  chunk_id?: string | null;
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
  /** Полный canonical .txt/.md; приходит только при `full_canonical_text=true`. */
  canonical_text_full?: string | null;
  preprocessing_raw_full?: string | null;
  preprocessing_raw_full_error?: string | null;
  preview_available?: boolean;
  embedding_model?: string | null;
  file_size_bytes?: number | null;
  timeline?: LogItem[];
  last_error_message?: string | null;
}

export interface UploadDocumentResponse {
  upload_id?: string | null;
  filename?: string;
  original_filename?: string | null;
  path?: string;
  success?: boolean;
  error?: string | null;
  chunks?: number;
  document_id?: string | null;
  preprocessing?: DocumentPreprocessingPublic | null;
  original_bytes?: number | null;
  cleaned_bytes?: number | null;
  raw_asset_ref?: string | null;
  cleaned_asset_ref?: string | null;
  processed_asset_ref?: string | null;
  compatibility_path?: string | null;
  compatibility_paths_written?: string[] | null;
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

export interface RetrievalBackendHealthRow {
  backend?: string;
  ok?: boolean;
  detail?: string | null;
  collection_count?: number | null;
}

/** GET /api/retrieval/overview — backend matrix + read-only tuning/paths (P6.11). */
export interface RetrievalOverviewResponse {
  database_configured?: boolean;
  env_default_backend?: string;
  db_active_backend?: string | null;
  effective_backend?: string;
  allowed_backends?: string[];
  degraded?: boolean;
  warnings?: string[];
  backends?: Record<string, RetrievalBackendHealthRow>;
  active_backend_health?: RetrievalBackendHealthRow;
  runtime_tuning?: Record<string, unknown> & {
    field_sources?: Record<string, string>;
  };
  indexing_tuning?: Record<string, unknown> & {
    field_sources?: Record<string, string>;
  };
  cache?: Record<string, unknown>;
  paths?: Record<string, unknown>;
}

export interface SetActiveRetrievalBackendResponse {
  effective_backend?: string;
  warnings?: string[];
  target_health?: RetrievalBackendHealthRow;
}

/** GET /api/memory/observability/summary */
export interface MemoryObservabilitySummary {
  database_available?: boolean;
  memory_runtime_source?: string;
  telegram_pg_conversation_memory?: boolean;
  database_url_configured?: boolean;
  active_sessions_count?: number;
  avg_turns_sessions_touched?: number;
  clear_reset_events_count?: number;
  hours?: number;
  budget_limits?: {
    max_turn_pairs?: number;
    max_llm_messages?: number;
  };
  llm_conversation_tail_cap?: number;
  chat_session_idle_timeout_seconds?: number;
}

export interface MemorySessionListItem {
  session_id?: string;
  user_id?: string;
  telegram_user_id?: string;
  user_label?: string;
  mode?: string;
  is_active?: boolean;
  updated_at?: string | null;
  messages_count?: number;
  turns_approx?: number;
  memory_source?: string;
  recent_clear_badge?: boolean;
}

export interface MemorySessionsListResponse {
  memory_runtime_source?: string;
  count?: number;
  limit?: number;
  offset?: number;
  items?: MemorySessionListItem[];
}

export interface MemorySessionDetailResponse {
  session_id?: string;
  user_id?: string;
  telegram_user_id?: string;
  mode?: string;
  is_active?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  memory_source?: string;
  messages_count?: number;
  recent_turns?: { role: string; preview: string }[];
  last_memory_load?: Record<string, unknown> | null;
  last_memory_append?: Record<string, unknown> | null;
  last_clear_event?: Record<string, unknown> | null;
  memory_lifecycle_recent?: Record<string, unknown>[];
  budget?: {
    max_turn_pairs?: number;
    max_llm_messages?: number;
    dialog_messages_in_session?: number;
    last_load_messages_loaded?: number | null;
    last_load_limit_pairs?: number | null;
    trimmed?: boolean;
    llm_conversation_tail_cap?: number;
  };
}

export async function fetchMemoryObservabilitySummary(
  hours = 24
): Promise<MemoryObservabilitySummary> {
  const q = new URLSearchParams({ hours: String(hours) });
  const res = await fetch(
    `${getApiBaseUrl()}/api/memory/observability/summary?${q.toString()}`
  );
  if (!res.ok) {
    throw new Error(`Memory summary: ${res.status} ${res.statusText}`);
  }
  return parseJson<MemoryObservabilitySummary>(res);
}

export async function fetchMemorySessionsList(opts?: {
  activeOnly?: boolean;
  limit?: number;
  offset?: number;
}): Promise<MemorySessionsListResponse> {
  const q = new URLSearchParams();
  if (opts?.activeOnly) q.set("active_only", "true");
  if (opts?.limit != null) q.set("limit", String(opts.limit));
  if (opts?.offset != null) q.set("offset", String(opts.offset));
  const suffix = q.toString() ? `?${q.toString()}` : "";
  const res = await fetch(
    `${getApiBaseUrl()}/api/memory/sessions${suffix}`
  );
  if (!res.ok) {
    throw new Error(`Memory sessions: ${res.status} ${res.statusText}`);
  }
  return parseJson<MemorySessionsListResponse>(res);
}

export async function fetchMemorySessionDetail(
  sessionId: string
): Promise<MemorySessionDetailResponse> {
  const res = await fetch(
    `${getApiBaseUrl()}/api/memory/sessions/${encodeURIComponent(sessionId)}`
  );
  if (!res.ok) {
    const t = await res.text().catch(() => "");
    throw new Error(
      `Memory session detail: ${res.status} ${t ? t.slice(0, 200) : res.statusText}`
    );
  }
  return parseJson<MemorySessionDetailResponse>(res);
}
