import { Fragment, useEffect, useMemo, useState } from "react";
import {
  fetchSummary,
  type SummaryResponse,
} from "../api/client";
import { LoadingState } from "../components/LoadingState";
import { OperationalRefreshButton } from "../components/OperationalRefreshButton";
import { OperationalSessionEmptyHint } from "../components/OperationalSessionEmptyHint";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";
import { stageToActionRu } from "../utils/operationalLabels";

const HOUR_OPTIONS = [24, 48, 168];

export function SummaryPage() {
  const [hours, setHours] = useState(24);
  const [data, setData] = useState<SummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const s = await fetchSummary(hours);
        if (!cancelled) setData(s);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Не удалось загрузить сводку");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [hours, refreshNonce]);

  const summaryHead = (
    <div className="summary-head">
      <div>
        <h1 className="page__title">Сводка</h1>
        <p className="page__lead muted">
          Скользящее окно <code>/api/summary</code> · метрики из логов
        </p>
      </div>
      <div className="summary-head__actions">
        <label className="summary-hours">
          <span className="muted">Период</span>
          <select
            className="summary-hours__select"
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            aria-label="Период в часах"
            disabled={loading}
          >
            {HOUR_OPTIONS.map((h) => (
              <option key={h} value={h}>
                {h === 168 ? "7d" : `${h}h`}
              </option>
            ))}
          </select>
        </label>
        <OperationalRefreshButton
          loading={loading}
          onClick={() => setRefreshNonce((n) => n + 1)}
        />
      </div>
    </div>
  );

  const eventsChecksum = useMemo(() => {
    const ev = data?.events;
    if (!ev) return null;
    return ev.total === ev.success + ev.error + ev.other;
  }, [data]);

  const topProviders = useMemo(() => {
    const raw = data?.telemetry_sample?.by_provider_row_counts ?? {};
    return Object.entries(raw).sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [data]);

  if (loading) {
    return (
      <div className="page summary-page">
        {summaryHead}
        <LoadingState label="Загрузка сводки…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="page summary-page">
        {summaryHead}
        <div className="panel panel--error overview-tight" role="alert">
          {error}
        </div>
        <p className="muted overview-tight metric-sub">
          Проверьте доступность API и выбранный период, затем нажмите «Обновить».
        </p>
      </div>
    );
  }

  if (!data?.events || !data.sessions || !data.routes) {
    return (
      <div className="page summary-page">
        {summaryHead}
        <OperationalSessionEmptyHint
          title="Сводка получена не полностью."
          hint="Ответ /api/summary не содержит ожидаемых блоков. Попробуйте другой период или нажмите «Обновить»."
        />
      </div>
    );
  }

  const ev = data.events;
  const sess = data.sessions;
  const routes = data.routes;
  const tel = data.telemetry_sample ?? {};
  const tokEcon = data.token_economy ?? null;
  const tokByStage: Array<[string, { total_tokens: number; rows_with_tokens: number; events: number }]> =
    Object.entries(tokEcon?.by_stage ?? {})
      .filter(([, row]) => row.total_tokens > 0 || row.rows_with_tokens > 0)
      .sort((a, b) => b[1].total_tokens - a[1].total_tokens);
  const tokByModel: Array<[string, { total_tokens: number }]> = Object.entries(
    tokEcon?.by_model ?? {}
  ).sort((a, b) => b[1].total_tokens - a[1].total_tokens);
  const lifecycle = data.lifecycle_events ?? [];
  const lifecycleMap = new Map(lifecycle.map((x) => [x.stage, x.events]));
  const audioDet = data.audio_voice_counts ?? {
    sessions_route_bucket: 0,
    voice_pipeline_stage_events: 0,
  };
  const lastAdminStage =
    lifecycle.find(
      (x) => x.stage.startsWith("admin_") || x.stage.startsWith("document")
    )?.stage ?? "—";
  const lastAdminStageLabel =
    lastAdminStage === "—" ? "—" : stageToActionRu(lastAdminStage, null);

  return (
    <div className="page summary-page">
      {summaryHead}

      <div className="page__grid summary-panel-grid">
        <SectionCard
          title="A. События за период"
          description="События считаются как строки processing_logs."
        >
          <dl className="kv summary-kv">
            <dt>Всего</dt>
            <dd>{ev.total}</dd>
            <dt>Успешно</dt>
            <dd>{ev.success}</dd>
            <dt>Ошибка</dt>
            <dd>{ev.error}</dd>
            <dt>Прочие</dt>
            <dd>{ev.other}</dd>
            <dt>Контрольная сумма</dt>
            <dd>
              <StatusBadge status={eventsChecksum ? "ok" : "error"} />
            </dd>
          </dl>
        </SectionCard>

        <SectionCard
          title="B. Сессии / маршруты"
          description="Сессии = unique execution_id в окне."
        >
          <dl className="kv summary-kv">
            <dt>Сессий / execution_id</dt>
            <dd>{sess.unique_execution_ids}</dd>
            <dt>Текст</dt>
            <dd>{routes.text}</dd>
            <dt>RAG</dt>
            <dd>{routes.rag}</dd>
            <dt>Изображения</dt>
            <dd>{routes.images}</dd>
            <dt>Аудио / voice</dt>
            <dd>{routes.audio_voice}</dd>
            <dt>Документ</dt>
            <dd>{formatNum(routes.documents ?? 0)}</dd>
            <dt>Прочие / без маршрута</dt>
            <dd>{routes.other_unknown}</dd>
          </dl>
        </SectionCard>

        <SectionCard
          title="C. Этапы обработки"
          description="События lifecycle (только ненулевые строки)."
        >
          {lifecycle.length === 0 ? (
            <p className="muted">Нет ненулевых этапов в текущем окне.</p>
          ) : (
            <dl className="kv summary-kv">
              {lifecycle.map((row) => (
                <Fragment key={row.stage}>
                  <dt className="mono" title={row.stage}>
                    {stageToActionRu(row.stage, null)}
                  </dt>
                  <dd>{row.events}</dd>
                </Fragment>
              ))}
            </dl>
          )}
        </SectionCard>

        <SectionCard
          title="D. Провайдеры и телеметрия"
          description="Данные по выборке sample, не доля трафика."
        >
          <dl className="kv summary-kv">
            <dt>Топ provider/model</dt>
            <dd className="mono break-all">{tel.top_provider_model ?? "—"}</dd>
            <dt>Токены (sample)</dt>
            <dd>{formatNum(tel.tokens_total)}</dd>
            <dt>Средняя задержка</dt>
            <dd>{tel.avg_latency_ms != null ? `${tel.avg_latency_ms} ms` : "—"}</dd>
            <dt>Макс. задержка</dt>
            <dd>{tel.max_latency_ms != null ? `${tel.max_latency_ms} ms` : "—"}</dd>
            <dt>Строк в окне</dt>
            <dd>{formatNum(tel.rows_in_window)}</dd>
            <dt>Лимит выборки</dt>
            <dd>{formatNum(tel.cap)}</dd>
            <dt>Сессий в sample</dt>
            <dd>{formatNum(tel.unique_execution_ids_in_sample)}</dd>
          </dl>
          <div className="telemetry-providers summary-tight-sm">
            {topProviders.length === 0 ? (
              <span className="muted">Нет provider-tagged строк в sample.</span>
            ) : (
              topProviders.map(([name, n]) => (
                <span key={name} className="mini-badge">
                  {name}: {n}
                </span>
              ))
            )}
          </div>
        </SectionCard>

        <SectionCard
          title="E. Админ / документы / индексация"
          description="Операционные admin_* метрики и активности."
        >
          <dl className="kv summary-kv">
            <dt>Админ-события</dt>
            <dd>{formatNum(data.admin_events)}</dd>
            <dt>Запуски переиндексации</dt>
            <dd>{formatNum(data.reindex_starts)}</dd>
            <dt>Загрузки документов (pipeline)</dt>
            <dd>
              {formatNum(
                lifecycleMap.get("document_upload_pipeline_done") ??
                  lifecycleMap.get("admin_document_uploaded") ??
                  0
              )}
            </dd>
            <dt>Последнее событие admin/reindex</dt>
            <dd className="mono" title={lastAdminStage}>
              {lastAdminStageLabel}
            </dd>
            <dt>Сессии аудио-маршрута</dt>
            <dd>{formatNum(audioDet.sessions_route_bucket)}</dd>
            <dt>События voice pipeline</dt>
            <dd>{formatNum(audioDet.voice_pipeline_stage_events)}</dd>
          </dl>
        </SectionCard>

        <SectionCard
          title="F. Токен-экономика (точное окно)"
          description="SQL-агрегация processing_logs за период — не выборка. Проверено суммой токенов."
        >
          {tokEcon && tokEcon.grand_total_tokens != null ? (
            <>
              <dl className="kv summary-kv">
                <dt>Всего токенов за окно</dt>
                <dd className="mono">{formatNum(tokEcon.grand_total_tokens)}</dd>
              </dl>
              {tokByStage.length > 0 && (
                <dl className="kv summary-kv">
                  {tokByStage.map(([stage, row]) => (
                    <Fragment key={stage}>
                      <dt className="mono" title={stage}>
                        {stageToActionRu(stage, null)}
                      </dt>
                      <dd>
                        {formatNum(row.total_tokens)}{" "}
                        <span className="muted">
                          ({row.rows_with_tokens}/{row.events})
                        </span>
                      </dd>
                    </Fragment>
                  ))}
                </dl>
              )}
              {tokByModel.length > 0 && (
                <dl className="kv summary-kv">
                  <dt>По модели</dt>
                  <dd className="muted">токены</dd>
                  {tokByModel.map(([model, row]) => (
                    <Fragment key={model}>
                      <dt className="mono">{model}</dt>
                      <dd>{formatNum(row.total_tokens)}</dd>
                    </Fragment>
                  ))}
                </dl>
              )}
            </>
          ) : (
            <p className="muted">
              Токен-агрегация недоступна (нет данных или БД не настроена).
            </p>
          )}
        </SectionCard>
      </div>
    </div>
  );
}

function formatNum(v: unknown): string {
  if (v === null || v === undefined) return "—";
  return String(v);
}
