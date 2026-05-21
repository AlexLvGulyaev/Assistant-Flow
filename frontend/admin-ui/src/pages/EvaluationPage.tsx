import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  fetchEvaluationRagTurnDetail,
  fetchEvaluationRagTurns,
  fetchEvaluationRunDetail,
  fetchEvaluationRuns,
  patchEvaluationItem,
  postEvaluationImport,
  postEvaluationRagasRun,
  type EvaluationRunDetailResponse,
  type EvaluationRunItem,
  type EvaluationRunListItem,
  type RagTurnDetailResponse,
  type RagTurnListItem,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { OperationalListPagination } from "../components/OperationalListPagination";
import { OperationalModalityBadge } from "../components/OperationalModalityBadge";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { OperationalRetrievalChunksSection } from "../components/OperationalRetrievalChunksSection";
import { SessionJsonSnapshot } from "../components/SessionJsonSnapshot";
import { EvaluationCachePolicyPanel } from "../components/EvaluationCachePolicyPanel";
import { StatusBadge } from "../components/StatusBadge";
import { useAuth } from "../auth/AuthContext";
import { PERM } from "../auth/permissions";
import { formatRetrievalBackendTitle, formatTimestampMsk } from "../utils/operationalLabels";
import { chunkFromEvalDiagnostic } from "../utils/retrievalChunks";

type TabId = "turns" | "runs";
type WindowLabel = "24h" | "48h" | "7d";

const PAGE_SIZE = 10;

const WINDOW_HOURS: Record<WindowLabel, number> = {
  "24h": 24,
  "48h": 48,
  "7d": 24 * 7,
};

function shortId(id: string | undefined, n = 10): string {
  if (!id) return "—";
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

function asRecord(v: unknown): Record<string, unknown> | undefined {
  if (!v || typeof v !== "object" || Array.isArray(v)) return undefined;
  return v as Record<string, unknown>;
}

function metricVal(
  metrics: EvaluationRunItem["metrics"] | undefined,
  key: string
): string {
  const m = metrics?.[key];
  if (!m) return "—";
  if (m.numeric != null && !Number.isNaN(Number(m.numeric))) {
    return Number(m.numeric).toFixed(3);
  }
  if (m.json?.status === "not_collected") return "не оценено";
  return "—";
}

function metricNumeric(
  metrics: EvaluationRunItem["metrics"] | undefined,
  key: string
): number | null {
  const n = metrics?.[key]?.numeric;
  if (n == null || Number.isNaN(Number(n))) return null;
  return Number(n);
}

function hasWeakMetric(metrics: EvaluationRunItem["metrics"] | undefined): boolean {
  const tracked = [
    "ragas.faithfulness",
    "ragas.answer_relevancy",
    "ragas.context_precision",
  ];
  return tracked.some((key) => {
    const val = metricNumeric(metrics, key);
    return val != null && val < 0.7;
  });
}

function pickDefaultRunItem(items: EvaluationRunItem[]): EvaluationRunItem | null {
  if (!items.length) return null;
  const missingGroundTruth = items.find((it) => !(it.ground_truth || "").trim());
  if (missingGroundTruth) return missingGroundTruth;
  const weakMetricItem = items.find((it) => hasWeakMetric(it.metrics));
  if (weakMetricItem) return weakMetricItem;
  return items[0] ?? null;
}

function metricToneClass(
  metrics: EvaluationRunItem["metrics"] | undefined,
  key: string
): string {
  const val = metricNumeric(metrics, key);
  if (val == null) return " eval-metric-chip--muted";
  if (val < 0.7) return " eval-metric-chip--warn";
  return " eval-metric-chip--ok";
}

function OpsRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function RagTurnRow({
  row,
  selected,
  checked,
  showImportCheckbox,
  onSelect,
  onToggle,
}: {
  row: RagTurnListItem;
  selected: boolean;
  checked: boolean;
  showImportCheckbox: boolean;
  onSelect: () => void;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={`logs-item${selected ? " logs-item--selected" : ""}`}
      data-eval-turn-id={row.execution_id}
      onClick={onSelect}
    >
      {showImportCheckbox ? (
        <span className="eval-row-check" onClick={(e) => e.stopPropagation()}>
          <input
            type="checkbox"
            className="eval-checkbox"
            checked={checked}
            onChange={onToggle}
            aria-label="Выбрать сессию"
          />
        </span>
      ) : null}
      <span className="logs-item__row logs-item__row--tight">
        <span className="mono logs-item__ts">{formatTimestampMsk(row.created_at)}</span>
        <OperationalModalityBadge modality="rag" />
        <StatusBadge status={row.status || "—"} />
      </span>
      <span className="logs-item__preview">
        {row.query?.slice(0, 96) || "запрос не найден в логах"}
      </span>
      <span className="logs-item__row logs-item__meta muted">
        <span className="mono truncate" title={row.execution_id}>
          {shortId(row.execution_id)}
        </span>
        <span>
          {[
            `k=${row.top_k ?? "—"}`,
            `ret=${row.retrieved_count ?? "—"}`,
            row.has_ragas_metrics ? "RAGAS: да" : null,
          ]
            .filter(Boolean)
            .join(" · ")}
        </span>
      </span>
    </button>
  );
}

function RunRow({
  row,
  selected,
  onSelect,
}: {
  row: EvaluationRunListItem;
  selected: boolean;
  onSelect: () => void;
}) {
  const ragasStatus = (row.ragas as { status?: string } | null)?.status;
  return (
    <button
      type="button"
      className={`logs-item${selected ? " logs-item--selected" : ""}`}
      data-eval-run-id={row.id}
      onClick={onSelect}
    >
      <span className="logs-item__main">
        <span className="logs-item__title">{row.name || shortId(row.id)}</span>
        <span className="logs-item__meta muted">
          {formatTimestampMsk(row.created_at)} · RAG-сессий={row.item_count ?? 0} ·{" "}
          {row.import_mode || "—"}
        </span>
      </span>
      {ragasStatus ? <StatusBadge status={ragasStatus} /> : null}
    </button>
  );
}

function TurnDetailPanel({
  detail,
  listRow,
}: {
  detail: RagTurnDetailResponse;
  listRow?: RagTurnListItem | null;
}) {
  const rd = asRecord(detail.retrieval_diag) ?? {};
  const gd = asRecord(detail.generation_diag) ?? {};
  const meta = detail.metadata ?? {};
  const rawChunks = (detail.retrieved_chunks ?? []) as Record<string, unknown>[];
  const sharedChunks = useMemo(
    () => rawChunks.map((c, i) => chunkFromEvalDiagnostic(c, i)),
    [rawChunks]
  );
  const relevanceThreshold = (() => {
    const t = rd.relevance_threshold ?? meta.relevance_threshold;
    if (typeof t === "number" && Number.isFinite(t)) return t;
    if (typeof t === "string" && t.trim() !== "" && !Number.isNaN(Number(t))) {
      return Number(t);
    }
    return null;
  })();
  const fallback = String(
    rd.fallback_reason || listRow?.fallback_reason || meta.fallback_reason || ""
  ).trim();
  const createdAt = listRow?.created_at || meta.interaction_at;
  const backend = String(
    meta.retrieval_backend || rd.retrieval_backend || rd.active_backend || listRow?.backend || "—"
  );
  const topK = meta.top_k ?? rd.top_k ?? listRow?.top_k;
  const retrieved = rd.retrieved_count ?? listRow?.retrieved_count;
  const uniqueSources = rd.unique_sources_count;
  const tokens =
    gd.total_tokens ??
    listRow?.token_usage?.total_tokens ??
    (gd.input_tokens != null && gd.output_tokens != null
      ? Number(gd.input_tokens) + Number(gd.output_tokens)
      : null);

  return (
    <div className="logs-detail rag-modality-detail eval-detail-scroll">
      <div className="modality-card__head">
        <h2 className="modality-card__title">RAG-сессия</h2>
        <div className="eval-detail-head__badges">
          {fallback ? <StatusBadge status={fallback === "none" ? "ok" : "warning"} /> : null}
          <StatusBadge status={detail.has_ragas_metrics ? "ok" : "—"} />
        </div>
      </div>
      <p className="eval-detail-head__sub muted mono">
        {shortId(detail.execution_id, 14)} · {formatTimestampMsk(createdAt as string)}
      </p>

      <EvaluationCachePolicyPanel retrievalDiag={rd} />

      <div className="modality-ops-panels modality-ops-panels--rag-split modality-ops-panels--eval-top eval-top-panels">
        <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--stack modality-ops-panels__rag-col--session">
          <div className="modality-ops-panel">
            <div className="modality-ops-panel__name">Сессия</div>
            <dl className="kv modality-ops-panel__kv">
              <OpsRow
                label="execution_id"
                value={<span className="mono">{detail.execution_id}</span>}
              />
              <OpsRow label="Backend" value={backend} />
              <OpsRow label="top_k" value={String(topK ?? "—")} />
              <OpsRow
                label="Задержка, мс"
                value={String(detail.latency_ms_total ?? gd.rag_pipeline_wall_ms ?? "—")}
              />
              <OpsRow label="Токены" value={tokens != null ? String(tokens) : "—"} />
            </dl>
          </div>
        </div>
        <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--stack">
          <div className="modality-ops-panel">
            <div className="modality-ops-panel__name">Retrieval</div>
            <dl className="kv modality-ops-panel__kv">
              <OpsRow label="Найдено чанков" value={String(retrieved ?? "—")} />
              <OpsRow
                label="Причина fallback"
                value={fallback || "—"}
              />
              <OpsRow
                label="Уникальных источников"
                value={String(uniqueSources ?? "—")}
              />
            </dl>
          </div>
          <div className="modality-ops-panel">
            <div className="modality-ops-panel__name">RAGAS</div>
            <dl className="kv modality-ops-panel__kv">
              <OpsRow
                label="Оценка выполнена"
                value={detail.has_ragas_metrics ? "Да" : "Нет"}
              />
            </dl>
          </div>
        </div>
      </div>

      <div className="logs-detail-grid logs-detail-grid--dense rag-io-grid">
        <div className="logs-detail-block">
          <h3 className="logs-detail-block__title">ЧТО СПРОСИЛ ПОЛЬЗОВАТЕЛЬ</h3>
          <pre className="logs-pre logs-pre--compact mono">
            {detail.query || "—"}
          </pre>
        </div>
        <div className="logs-detail-block">
          <h3 className="logs-detail-block__title">ЧТО ОТВЕТИЛА СИСТЕМА</h3>
          <pre className="logs-pre logs-pre--compact mono">
            {detail.answer || "—"}
          </pre>
        </div>
      </div>

      <OperationalRetrievalChunksSection
        title={`Найденные чанки (${sharedChunks.length})`}
        chunks={sharedChunks}
        relevanceThreshold={relevanceThreshold}
        getBackendTitle={(chunk) =>
          formatRetrievalBackendTitle(
            chunk.backend || backend || undefined
          )
        }
        emptyMessage="Чанки не найдены в diagnostics."
      />

      <SessionJsonSnapshot
        className="page__mt"
        body={JSON.stringify(
          {
            retrieval: detail.retrieval_diag,
            generation: detail.generation_diag,
            metadata: detail.metadata,
          },
          null,
          2
        )}
      />
    </div>
  );
}

function EvaluationMetricChip({
  label,
  metrics,
  metricKey,
}: {
  label: string;
  metrics: EvaluationRunItem["metrics"] | undefined;
  metricKey: string;
}) {
  return (
    <span className={`eval-metric-chip${metricToneClass(metrics, metricKey)}`}>
      {label}: {metricVal(metrics, metricKey)}
    </span>
  );
}

function RunItemNavRow({
  item,
  selected,
  onSelect,
}: {
  item: EvaluationRunItem;
  selected: boolean;
  onSelect: () => void;
}) {
  const missingGroundTruth = !(item.ground_truth || "").trim();
  const weakMetrics = hasWeakMetric(item.metrics);
  const hasWarning = missingGroundTruth || weakMetrics || item.status === "error";
  return (
    <button
      type="button"
      className={`eval-item-nav-row${selected ? " eval-item-nav-row--selected" : ""}`}
      onClick={onSelect}
    >
      <div className="eval-item-nav-row__head">
        <span className="mono eval-item-nav-row__ordinal">#{item.ordinal ?? "—"}</span>
        <StatusBadge status={item.status || "—"} />
        {hasWarning ? <span className="eval-item-nav-row__warn">внимание</span> : null}
      </div>
      <p className="eval-item-nav-row__query">{item.query?.slice(0, 140) || "—"}</p>
      <div className="eval-item-nav-row__meta muted">
        <span>{missingGroundTruth ? "эталон: не задан" : "эталон: задан"}</span>
        <span className="mono">{shortId(item.execution_id || undefined, 12)}</span>
      </div>
      <div className="eval-item-nav-row__chips">
        <EvaluationMetricChip
          label="faith"
          metrics={item.metrics}
          metricKey="ragas.faithfulness"
        />
        <EvaluationMetricChip
          label="ans.rel"
          metrics={item.metrics}
          metricKey="ragas.answer_relevancy"
        />
        <EvaluationMetricChip
          label="ctx.prec"
          metrics={item.metrics}
          metricKey="ragas.context_precision"
        />
      </div>
    </button>
  );
}

function SelectedItemForensicPanel({
  item,
  canEvalWrite,
  onSaved,
}: {
  item: EvaluationRunItem;
  canEvalWrite: boolean;
  onSaved: () => void;
}) {
  const [gt, setGt] = useState(item.ground_truth ?? "");
  const [notes, setNotes] = useState("");
  const [score, setScore] = useState(
    item.metrics?.["manual.overall"]?.numeric != null
      ? String(item.metrics["manual.overall"].numeric)
      : ""
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setGt(item.ground_truth ?? "");
    setNotes("");
    setScore(
      item.metrics?.["manual.overall"]?.numeric != null
        ? String(item.metrics["manual.overall"].numeric)
        : ""
    );
  }, [item.id, item.ground_truth, item.metrics]);

  const save = async () => {
    if (!canEvalWrite) return;
    setSaving(true);
    setErr(null);
    try {
      const body: {
        ground_truth?: string;
        notes?: string;
        manual_score?: number;
      } = { ground_truth: gt };
      if (notes.trim()) body.notes = notes.trim();
      if (score.trim() !== "") body.manual_score = Number(score);
      await patchEvaluationItem(item.id, body);
      onSaved();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  const rd = asRecord(item.retrieval_diag) ?? {};
  const gd = asRecord(item.generation_diag) ?? {};
  const rawChunks = (item.retrieved_chunks ?? []) as Record<string, unknown>[];
  const sharedChunks = useMemo(
    () => rawChunks.map((c, i) => chunkFromEvalDiagnostic(c, i)),
    [rawChunks]
  );
  const thresholdRaw = rd.relevance_threshold;
  const relevanceThreshold =
    typeof thresholdRaw === "number" && Number.isFinite(thresholdRaw)
      ? thresholdRaw
      : typeof thresholdRaw === "string" &&
          thresholdRaw.trim() &&
          !Number.isNaN(Number(thresholdRaw))
        ? Number(thresholdRaw)
        : null;
  const fallback = String(rd.fallback_reason || "").trim();
  const backend = String(rd.retrieval_backend || rd.active_backend || "—");
  const totalTokens =
    gd.total_tokens != null && !Number.isNaN(Number(gd.total_tokens))
      ? Number(gd.total_tokens)
      : null;

  return (
    <div className="eval-item-forensic-panel">
      <div className="eval-item-identity">
        <div className="eval-item-identity__left">
          <span className="mono">RAG-сессия #{item.ordinal ?? "—"}</span>
          <StatusBadge status={item.status || "—"} />
          {!gt.trim() ? <span className="eval-item-nav-row__warn">эталон не задан</span> : null}
        </div>
        <p className="eval-item-identity__meta muted mono">
          {shortId(item.execution_id || undefined, 14)} · latency={item.latency_ms_total ?? "—"}ms ·
          tokens={totalTokens ?? "—"}
        </p>
      </div>

      <EvaluationCachePolicyPanel retrievalDiag={rd} />

      <section className="logs-detail-block">
        <h3 className="logs-detail-block__title">Что спросил пользователь</h3>
        <pre className="logs-pre logs-pre--compact mono">{item.query || "—"}</pre>
      </section>

      <div className="eval-answer-compare-grid">
        <section className="logs-detail-block">
          <h3 className="logs-detail-block__title">Что ответила система</h3>
          <pre className="logs-pre logs-pre--compact mono">{item.answer || "—"}</pre>
          {fallback ? <p className="muted eval-item-fallback">fallback_reason: {fallback}</p> : null}
        </section>

        <section className="logs-detail-block">
          <h3 className="logs-detail-block__title">Эталон / ручная оценка</h3>
          <textarea
            className="logs-search eval-item-edit__textarea"
            rows={4}
            value={gt}
            onChange={(e) => setGt(e.target.value)}
            readOnly={!canEvalWrite}
            disabled={!canEvalWrite}
            placeholder="Эталонный ответ"
          />
          <div className="eval-item-edit__row">
            <input
              className="logs-search eval-item-edit__input"
              value={score}
              onChange={(e) => setScore(e.target.value)}
              readOnly={!canEvalWrite}
              disabled={!canEvalWrite}
              placeholder="ручная 0 / 0.5 / 1"
            />
            <input
              className="logs-search eval-item-edit__input eval-item-edit__input--wide"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              readOnly={!canEvalWrite}
              disabled={!canEvalWrite}
              placeholder="заметки"
            />
            {canEvalWrite ? (
              <button
                type="button"
                className="logs-page-btn"
                disabled={saving}
                onClick={save}
              >
                {saving ? "…" : "Сохранить"}
              </button>
            ) : null}
          </div>
          {err ? <p className="panel panel--error eval-item-edit__err">{err}</p> : null}
        </section>
      </div>

      <section className="logs-detail-block">
        <h3 className="logs-detail-block__title">Метрики</h3>
        <div className="eval-item-nav-row__chips">
          <EvaluationMetricChip
            label="faithfulness"
            metrics={item.metrics}
            metricKey="ragas.faithfulness"
          />
          <EvaluationMetricChip
            label="answer_relevancy"
            metrics={item.metrics}
            metricKey="ragas.answer_relevancy"
          />
          <EvaluationMetricChip
            label="context_precision"
            metrics={item.metrics}
            metricKey="ragas.context_precision"
          />
          <EvaluationMetricChip
            label="manual.overall"
            metrics={item.metrics}
            metricKey="manual.overall"
          />
        </div>
      </section>

      <OperationalRetrievalChunksSection
        title={`Найденные чанки (${sharedChunks.length})`}
        chunks={sharedChunks}
        relevanceThreshold={relevanceThreshold}
        getBackendTitle={(chunk) =>
          formatRetrievalBackendTitle(chunk.backend || backend || undefined)
        }
        emptyMessage="Чанки не найдены для выбранной RAG-сессии."
      />

      <SessionJsonSnapshot
        className="page__mt-sm"
        body={JSON.stringify(
          {
            retrieval: item.retrieval_diag,
            generation: item.generation_diag,
          },
          null,
          2
        )}
      />
    </div>
  );
}

function RunDetailPanel({
  run,
  canEvalWrite,
  ragasBusy,
  ragasResult,
  onRunRagas,
  onRefreshRun,
}: {
  run: EvaluationRunDetailResponse;
  canEvalWrite: boolean;
  ragasBusy: boolean;
  ragasResult: Record<string, unknown> | null;
  onRunRagas: () => void;
  onRefreshRun: () => void;
}) {
  const items = run.items ?? [];
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const ragasBlock = (ragasResult ||
    (run.ragas as Record<string, unknown> | undefined)) as
    | Record<string, unknown>
    | undefined;
  const runMeans = (ragasBlock?.run_means || {}) as Record<string, number | null>;
  const unavailable = (ragasBlock?.unavailable_metrics || []) as string[];
  const snap = run.config_snapshot ?? {};

  useEffect(() => {
    setSelectedItemId((prev) => {
      if (prev && items.some((it) => it.id === prev)) return prev;
      return pickDefaultRunItem(items)?.id ?? null;
    });
  }, [run.id, items]);

  const selectedItem = useMemo(
    () => items.find((it) => it.id === selectedItemId) ?? null,
    [items, selectedItemId]
  );

  return (
    <div className="logs-detail rag-modality-detail eval-detail-scroll">
      <div className="modality-card__head eval-run-head">
        <div>
          <h2 className="modality-card__title">
            Анализ набора: {run.name || shortId(run.id)}
          </h2>
          <p className="eval-detail-head__sub muted mono">
            {shortId(run.id, 14)} · {formatTimestampMsk(run.created_at)}
          </p>
        </div>
        <div className="eval-run-head__actions">
          {canEvalWrite ? (
            <button
              type="button"
              className="logs-page-btn"
              disabled={ragasBusy || run.status !== "completed"}
              onClick={onRunRagas}
            >
              {ragasBusy ? "RAGAS…" : "Запустить RAGAS"}
            </button>
          ) : null}
          <OperationalRefreshButton loading={ragasBusy} onClick={onRefreshRun} />
          <StatusBadge status={run.status || "—"} />
        </div>
      </div>

      <div className="modality-ops-panels modality-ops-panels--rag-split modality-ops-panels--eval-top eval-top-panels eval-top-panels--compact">
        <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--stack">
          <div className="modality-ops-panel">
            <div className="modality-ops-panel__name">Параметры запуска</div>
            <dl className="kv modality-ops-panel__kv">
              <OpsRow label="RAG-сессий" value={String(run.item_count ?? items.length)} />
              <OpsRow
                label="Режим импорта"
                value={String(run.import_mode || snap.import_mode || "—")}
              />
              <OpsRow label="Набор" value={String(snap.dataset_slug || "—")} />
              <OpsRow label="top_k retrieval" value={String(snap.top_k ?? "—")} />
            </dl>
          </div>
        </div>
        <div className="modality-ops-panels__rag-col modality-ops-panels__rag-col--stack">
          <div className="modality-ops-panel">
            <div className="modality-ops-panel__name">RAGAS summary</div>
            <dl className="kv modality-ops-panel__kv">
              <OpsRow label="Статус" value={String(ragasBlock?.status ?? "—")} />
              <OpsRow
                label="faithfulness"
                value={String(runMeans["ragas.faithfulness"] ?? "null")}
              />
              <OpsRow
                label="answer_relevancy"
                value={String(runMeans["ragas.answer_relevancy"] ?? "null")}
              />
              <OpsRow
                label="context_precision"
                value={String(runMeans["ragas.context_precision"] ?? "null")}
              />
            </dl>
            {unavailable.length ? (
              <p className="muted eval-ragas-unavail">
                недоступны: {unavailable.join(", ")}
              </p>
            ) : null}
          </div>
        </div>
      </div>

      <div className="eval-run-workspace">
        <aside className="eval-item-nav-panel">
          <div className="eval-item-nav-panel__head">
            <h3 className="logs-timeline-heading">RAG-сессии</h3>
            <span className="muted mono">{items.length}</span>
          </div>
          <div className="eval-item-nav-list">
            {items.map((it) => (
              <RunItemNavRow
                key={it.id}
                item={it}
                selected={selectedItemId === it.id}
                onSelect={() => setSelectedItemId(it.id)}
              />
            ))}
          </div>
        </aside>

        <section className="eval-item-forensic-zone">
          {selectedItem ? (
            <SelectedItemForensicPanel
              item={selectedItem}
              canEvalWrite={canEvalWrite}
              onSaved={onRefreshRun}
            />
          ) : (
            <EmptyState
              title="Нет RAG-сессии для анализа"
              message="Выберите набор с импортированными RAG-сессиями."
            />
          )}
        </section>
      </div>
    </div>
  );
}

export function EvaluationPage() {
  const { hasPermission } = useAuth();
  const canEvalWrite = hasPermission(PERM.settingsWrite);
  const [tab, setTab] = useState<TabId>("turns");
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [windowLabel, setWindowLabel] = useState<WindowLabel>("24h");
  const [search, setSearch] = useState("");
  const [fallbackFilter, setFallbackFilter] = useState("all");
  const [hasMetricsFilter, setHasMetricsFilter] = useState("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importMsg, setImportMsg] = useState<string | null>(null);
  const [runNameInput, setRunNameInput] = useState("");

  const [turns, setTurns] = useState<RagTurnListItem[]>([]);
  const [selectedTurnId, setSelectedTurnId] = useState<string | null>(null);
  const [turnDetail, setTurnDetail] = useState<RagTurnDetailResponse | null>(null);
  const [turnDetailLoading, setTurnDetailLoading] = useState(false);
  const [checkedTurns, setCheckedTurns] = useState<Set<string>>(new Set());

  const [runs, setRuns] = useState<EvaluationRunListItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<EvaluationRunDetailResponse | null>(null);
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const [ragasBusy, setRagasBusy] = useState(false);
  const [ragasResult, setRagasResult] = useState<Record<string, unknown> | null>(null);

  const refresh = useCallback(() => setRefreshNonce((n) => n + 1), []);
  const sinceHours = WINDOW_HOURS[windowLabel];
  const [listPage, setListPage] = useState(0);

  const activeList = tab === "turns" ? turns : runs;
  const totalPagesRaw = Math.ceil(activeList.length / PAGE_SIZE) || 0;
  const pageIndex = Math.min(listPage, Math.max(0, totalPagesRaw - 1));
  const pageItems = useMemo(
    () => activeList.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE),
    [activeList, pageIndex]
  );
  const lastPageIndex = Math.max(0, totalPagesRaw - 1);

  useEffect(() => {
    setListPage(0);
  }, [tab, refreshNonce, sinceHours, fallbackFilter, hasMetricsFilter, search]);

  useEffect(() => {
    if (listPage !== pageIndex) setListPage(pageIndex);
  }, [listPage, pageIndex]);

  const goPrevPage = () => setListPage((p) => Math.max(0, p - 1));
  const goNextPage = () => setListPage((p) => Math.min(lastPageIndex, p + 1));

  const selectedTurnRow = useMemo(
    () => turns.find((t) => t.execution_id === selectedTurnId) ?? null,
    [turns, selectedTurnId]
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        if (tab === "turns") {
          const res = await fetchEvaluationRagTurns({
            limit: 80,
            sinceHours,
            fallback: fallbackFilter === "all" ? undefined : fallbackFilter,
            hasRagasMetrics:
              hasMetricsFilter === "yes"
                ? true
                : hasMetricsFilter === "no"
                  ? false
                  : undefined,
            search,
          });
          if (cancelled) return;
          const items = res.items ?? [];
          setTurns(items);
          setSelectedTurnId((prev) => {
            if (prev && items.some((i) => i.execution_id === prev)) return prev;
            return items[0]?.execution_id ?? null;
          });
        } else {
          const res = await fetchEvaluationRuns({ limit: 80 });
          if (cancelled) return;
          const items = res.items ?? [];
          setRuns(items);
          setSelectedRunId((prev) => {
            if (prev && items.some((i) => i.id === prev)) return prev;
            return items[0]?.id ?? null;
          });
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Ошибка загрузки");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, refreshNonce, sinceHours, fallbackFilter, hasMetricsFilter, search]);

  useEffect(() => {
    if (tab !== "turns" || !selectedTurnId) {
      setTurnDetail(null);
      return;
    }
    let cancelled = false;
    setTurnDetailLoading(true);
    (async () => {
      try {
        const d = await fetchEvaluationRagTurnDetail(selectedTurnId);
        if (!cancelled) setTurnDetail(d);
      } catch {
        if (!cancelled) setTurnDetail(null);
      } finally {
        if (!cancelled) setTurnDetailLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tab, selectedTurnId, refreshNonce]);

  const loadRunDetail = useCallback(async (runId: string) => {
    setRunDetailLoading(true);
    try {
      const d = await fetchEvaluationRunDetail(runId);
      setRunDetail(d);
      setRagasResult((d.ragas as Record<string, unknown>) || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка run detail");
    } finally {
      setRunDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab !== "runs" || !selectedRunId) {
      setRunDetail(null);
      return;
    }
    loadRunDetail(selectedRunId);
  }, [tab, selectedRunId, refreshNonce, loadRunDetail]);

  const toggleTurn = (eid: string) => {
    setCheckedTurns((prev) => {
      const next = new Set(prev);
      if (next.has(eid)) next.delete(eid);
      else next.add(eid);
      return next;
    });
  };

  const doImport = async (ids: string[]) => {
    if (!canEvalWrite || !ids.length) return;
    setImportBusy(true);
    setImportMsg(null);
    try {
      const res = await postEvaluationImport({
        execution_ids: ids,
        dataset: "interactive_eval_ui",
        run_name: runNameInput.trim() || `ui-${ids.length}-turns`,
      });
      setImportMsg(`Импортировано → run ${shortId(res.run_id, 16)}`);
      setTab("runs");
      setSelectedRunId(res.run_id);
      setRefreshNonce((n) => n + 1);
    } catch (e) {
      setImportMsg(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImportBusy(false);
    }
  };

  const importSelected = () => doImport(Array.from(checkedTurns));
  const importLastN = (n: number) =>
    doImport(turns.slice(0, n).map((t) => t.execution_id));

  const runRagas = async () => {
    if (!canEvalWrite || !selectedRunId) return;
    setRagasBusy(true);
    setError(null);
    try {
      const res = await postEvaluationRagasRun(selectedRunId);
      setRagasResult(res);
      await loadRunDetail(selectedRunId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "RAGAS failed");
    } finally {
      setRagasBusy(false);
    }
  };

  const listContent = useMemo(() => {
    if (tab === "turns") {
      return pageItems.map((row) => {
        const turn = row as RagTurnListItem;
        return (
          <RagTurnRow
            key={turn.execution_id}
            row={turn}
            selected={selectedTurnId === turn.execution_id}
            checked={checkedTurns.has(turn.execution_id)}
            showImportCheckbox={canEvalWrite}
            onSelect={() => setSelectedTurnId(turn.execution_id)}
            onToggle={() => toggleTurn(turn.execution_id)}
          />
        );
      });
    }
    return pageItems.map((row) => {
      const run = row as EvaluationRunListItem;
      return (
        <RunRow
          key={run.id}
          row={run}
          selected={selectedRunId === run.id}
          onSelect={() => setSelectedRunId(run.id)}
        />
      );
    });
  }, [tab, pageItems, selectedTurnId, selectedRunId, checkedTurns, canEvalWrite]);

  const rowCount = tab === "turns" ? turns.length : runs.length;
  const selectedCount = tab === "turns" ? checkedTurns.size : selectedRunId ? 1 : 0;

  const rightPanel = (() => {
    if (tab === "turns") {
      if (loading && turns.length === 0) {
        return <LoadingState label="Загрузка…" />;
      }
      if (!turns.length) {
        return (
          <EmptyState
            title="Нет RAG-сессий"
            message="За выбранное окно нет rag_answer_done в логах."
          />
        );
      }
      if (turnDetailLoading && !turnDetail) {
        return <LoadingState label="Детали сессии…" />;
      }
      if (turnDetail) {
        return <TurnDetailPanel detail={turnDetail} listRow={selectedTurnRow} />;
      }
      return <LoadingState label="Детали сессии…" />;
    }
    if (runDetailLoading && !runDetail) {
      return <LoadingState label="Детали набора…" />;
    }
    if (!runs.length) {
      return (
        <EmptyState
          title="Нет наборов анализа"
          message="Импортируйте RAG-сессии с вкладки «Недавние RAG-сессии»."
        />
      );
    }
    if (runDetail) {
      return (
        <RunDetailPanel
          run={runDetail}
          canEvalWrite={canEvalWrite}
          ragasBusy={ragasBusy}
          ragasResult={ragasResult}
          onRunRagas={runRagas}
          onRefreshRun={() => selectedRunId && loadRunDetail(selectedRunId)}
        />
      );
    }
    return <LoadingState label="Детали набора…" />;
  })();

  return (
    <div className="page logs-page rag-page evaluation-page">
      <h1 className="page__title">Анализ качества RAG</h1>
      <p className="page__lead muted">
        Операционная диагностика retrieval и качества ответов
      </p>

      {!canEvalWrite ? (
        <div className="evaluation-page__alert evaluation-page__alert--info" role="status">
          <strong>Режим просмотра:</strong> импорт RAG-сессий, запуск RAGAS и правка эталонов
          недоступны для текущей роли (<code>settings:write</code> требуется для изменений).
        </div>
      ) : null}

      <div className="logs-quick-row eval-console-tabs">
        <button
          type="button"
          className={`logs-chip${tab === "turns" ? " logs-chip--active" : ""}`}
          onClick={() => setTab("turns")}
        >
          Недавние RAG-сессии
        </button>
        <button
          type="button"
          className={`logs-chip${tab === "runs" ? " logs-chip--active" : ""}`}
          onClick={() => setTab("runs")}
        >
          Анализ
        </button>
      </div>

      {importMsg ? <p className="eval-banner">{importMsg}</p> : null}
      {error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : null}

      <div className="logs-console">
        <section className="logs-left card">
          <div className="logs-filters">
            {tab === "turns" ? (
              <>
                <div className="logs-filter-row evaluation-filter-row">
                  <select
                    className="logs-select"
                    value={windowLabel}
                    onChange={(e) =>
                      setWindowLabel(e.target.value as WindowLabel)
                    }
                    aria-label="Окно времени"
                  >
                    <option value="24h">24h</option>
                    <option value="48h">48h</option>
                    <option value="7d">7d</option>
                  </select>
                  <select
                    className="logs-select"
                    value={fallbackFilter}
                    onChange={(e) => setFallbackFilter(e.target.value)}
                    aria-label="Fallback"
                  >
                    <option value="all">все fallback-режимы</option>
                    <option value="none">нет fallback</option>
                  </select>
                  <select
                    className="logs-select"
                    value={hasMetricsFilter}
                    onChange={(e) => setHasMetricsFilter(e.target.value)}
                    aria-label="RAGAS scored"
                  >
                    <option value="all">все оценки</option>
                    <option value="yes">есть метрики</option>
                    <option value="no">нет метрик</option>
                  </select>
                </div>
                <input
                  className="logs-search"
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Поиск: вопрос, ответ, execution_id…"
                />
                <div className="logs-quick-row eval-actions-row">
                  {canEvalWrite ? (
                    <>
                      <input
                        className="logs-search eval-run-name-input"
                        type="text"
                        value={runNameInput}
                        onChange={(e) => setRunNameInput(e.target.value)}
                        placeholder="Имя набора анализа (например: Weaviate c1000 k5 baseline)"
                        aria-label="Имя набора анализа"
                      />
                      <button
                        type="button"
                        className="logs-page-btn"
                        disabled={importBusy || checkedTurns.size === 0}
                        onClick={importSelected}
                      >
                        Импорт выбранных ({checkedTurns.size})
                      </button>
                      <button
                        type="button"
                        className="logs-page-btn logs-page-btn--muted"
                        disabled={importBusy || turns.length === 0}
                        onClick={() => importLastN(5)}
                      >
                        Импорт последних 5
                      </button>
                    </>
                  ) : null}
                  <OperationalRefreshButton loading={loading} onClick={refresh} />
                </div>
              </>
            ) : (
              <div className="logs-quick-row eval-actions-row">
                <OperationalRefreshButton loading={loading} onClick={refresh} />
              </div>
            )}
            <OperationalListPagination
              pageIndex={pageIndex}
              totalPages={totalPagesRaw}
              totalItems={rowCount}
              pageSize={PAGE_SIZE}
              onPrev={goPrevPage}
              onNext={goNextPage}
              disabled={loading}
            />
            {tab === "turns" && canEvalWrite ? (
              <div className="logs-filter-meta muted eval-list-extra-meta">
                <span>выбрано для импорта: {selectedCount}</span>
              </div>
            ) : null}
          </div>
          <div className="logs-list">
            {loading && listContent.length === 0 ? (
              <LoadingState label="Загрузка списка…" />
            ) : listContent.length ? (
              listContent
            ) : (
              <EmptyState
                title="Нет данных"
                message={
                  tab === "turns"
                    ? "Нет RAG-сессий за выбранное окно"
                    : "Нет наборов анализа"
                }
              />
            )}
          </div>
        </section>

        <section className="logs-right card">{rightPanel}</section>
      </div>
    </div>
  );
}
