import { useEffect, useMemo, useState } from "react";
import {
  fetchSummary,
  type SummaryLifecycleRow,
  type SummaryResponse,
} from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { MetricCard } from "../components/MetricCard";
import { SectionCard } from "../components/SectionCard";
import { StatusBadge } from "../components/StatusBadge";

const HOUR_OPTIONS = [24, 48, 168];

export function SummaryPage() {
  const [hours, setHours] = useState(24);
  const [data, setData] = useState<SummaryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const s = await fetchSummary(hours);
        if (!cancelled) setData(s);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load summary");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [hours]);

  const eventsChecksum = useMemo(() => {
    const ev = data?.events;
    if (!ev) return null;
    const sum = ev.success + ev.error + ev.other;
    return sum === ev.total;
  }, [data]);

  const topProviders = useMemo(() => {
    const raw = data?.telemetry_sample?.by_provider_row_counts ?? {};
    return Object.entries(raw)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
  }, [data]);

  if (loading) {
    return (
      <div className="page">
        <h1 className="page__title">Summary</h1>
        <LoadingState label="Loading summary…" />
        <div className="skeleton-grid page__mt">
          <div className="skeleton skeleton--card" />
          <div className="skeleton skeleton--card" />
          <div className="skeleton skeleton--wide" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <h1 className="page__title">Summary</h1>
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      </div>
    );
  }

  if (!data?.events || !data.sessions || !data.routes) {
    return (
      <div className="page">
        <h1 className="page__title">Summary</h1>
        <EmptyState message="Summary payload incomplete." />
      </div>
    );
  }

  const ev = data.events;
  const sess = data.sessions;
  const routes = data.routes;
  const tel = data.telemetry_sample ?? {};
  const lifecycle = data.lifecycle_events ?? [];
  const audioDet = data.audio_voice_counts ?? {
    sessions_route_bucket: 0,
    voice_pipeline_stage_events: 0,
  };

  return (
    <div className="page">
      <div className="summary-head">
        <div>
          <h1 className="page__title">Summary</h1>
          <p className="page__lead muted">
            Rolling window from <code>/api/summary</code> · log-derived metrics
          </p>
        </div>
        <label className="summary-hours">
          <span className="muted">Window</span>
          <select
            className="summary-hours__select"
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            aria-label="Time window (hours)"
          >
            {HOUR_OPTIONS.map((h) => (
              <option key={h} value={h}>
                {h === 168 ? "7d" : `${h}h`}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="page__grid">
        <MetricCard title="Events (rows)">
          <p className="metric-sub muted">
            Total log rows vs terminal outcomes ·{" "}
            <code>other</code> = non-success/error statuses
          </p>
          <div className="stat-grid page__mt-sm">
            <div className="stat-chip">
              <div className="stat-chip__lbl">Total</div>
              <div className="stat-chip__val">{ev.total}</div>
            </div>
            <div className="stat-chip">
              <div className="stat-chip__lbl">Success</div>
              <div className="stat-chip__val">{ev.success}</div>
            </div>
            <div className="stat-chip">
              <div className="stat-chip__lbl">Error</div>
              <div className="stat-chip__val">{ev.error}</div>
            </div>
            <div className="stat-chip">
              <div className="stat-chip__lbl">Other</div>
              <div className="stat-chip__val">{ev.other}</div>
            </div>
          </div>
          <p className="checksum-line muted">
            checksum{" "}
            {eventsChecksum ? (
              <StatusBadge status="ok" />
            ) : (
              <StatusBadge status="error" />
            )}
          </p>
        </MetricCard>

        <MetricCard title="Sessions">
          <p className="metric-sub muted">
            Distinct <code>execution_id</code> in window
          </p>
          <div className="stat-grid page__mt-sm">
            <div className="stat-chip">
              <div className="stat-chip__lbl">Unique IDs</div>
              <div className="stat-chip__val">{sess.unique_execution_ids}</div>
            </div>
          </div>
        </MetricCard>

        <MetricCard title="Routes (sessions)">
          <p className="metric-sub muted">
            One bucket per request · unknown reconciles to session total
          </p>
          <div className="stat-grid page__mt-sm">
            <div className="stat-chip">
              <div className="stat-chip__lbl">Text</div>
              <div className="stat-chip__val">{routes.text}</div>
            </div>
            <div className="stat-chip">
              <div className="stat-chip__lbl">RAG</div>
              <div className="stat-chip__val">{routes.rag}</div>
            </div>
            <div className="stat-chip">
              <div className="stat-chip__lbl">Images</div>
              <div className="stat-chip__val">{routes.images}</div>
            </div>
            <div className="stat-chip">
              <div className="stat-chip__lbl">Audio / voice</div>
              <div className="stat-chip__val">{routes.audio_voice}</div>
            </div>
            <div className="stat-chip">
              <div className="stat-chip__lbl">Other / unknown</div>
              <div className="stat-chip__val">{routes.other_unknown}</div>
            </div>
          </div>
        </MetricCard>
      </div>

      <div className="page__grid page__mt">
        <MetricCard title="Admin &amp; audio detail">
          <dl className="kv">
            <dt>Admin events</dt>
            <dd>{formatNum(data.admin_events)}</dd>
            <dt>Reindex starts</dt>
            <dd>{formatNum(data.reindex_starts)}</dd>
            <dt>Audio route sessions</dt>
            <dd>{formatNum(audioDet.sessions_route_bucket)}</dd>
            <dt>Voice pipeline rows</dt>
            <dd>{formatNum(audioDet.voice_pipeline_stage_events)}</dd>
          </dl>
        </MetricCard>

        <SectionCard
          title="Telemetry sample"
          description="Recent capped log tail filtered into the window — row counts by provider, not traffic share."
        >
          <dl className="kv">
            <dt>Rows (window)</dt>
            <dd>{formatNum(tel.rows_in_window)}</dd>
            <dt>Sample cap</dt>
            <dd>{formatNum(tel.cap)}</dd>
            <dt>Exec IDs in sample</dt>
            <dd>{formatNum(tel.unique_execution_ids_in_sample)}</dd>
            <dt>Tokens (sample)</dt>
            <dd>{tel.tokens_total ?? "—"}</dd>
            <dt>Avg latency</dt>
            <dd>
              {tel.avg_latency_ms != null ? `${tel.avg_latency_ms} ms` : "—"}
            </dd>
            <dt>Max latency</dt>
            <dd>
              {tel.max_latency_ms != null ? `${tel.max_latency_ms} ms` : "—"}
            </dd>
            <dt>Top pair</dt>
            <dd className="mono break-all">{tel.top_provider_model ?? "—"}</dd>
          </dl>
          <div className="telemetry-providers page__mt-sm">
            {topProviders.length === 0 ? (
              <span className="muted">No provider-tagged rows in sample.</span>
            ) : (
              topProviders.map(([name, n]) => (
                <span key={name} className="mini-badge">
                  {name}: {n}
                </span>
              ))
            )}
          </div>
        </SectionCard>
      </div>

      <SectionCard
        title="Lifecycle (event rows)"
        description="Selected stages · counts are rows in processing_logs, not HTTP requests."
        className="page__mt"
      >
        {lifecycle.length === 0 ? (
          <p className="muted">No matching stages in this window.</p>
        ) : (
          <LifecycleTags rows={lifecycle} />
        )}
      </SectionCard>
    </div>
  );
}

function LifecycleTags({ rows }: { rows: SummaryLifecycleRow[] }) {
  return (
    <div className="lifecycle-tags">
      {rows.map((r) => (
        <span key={r.stage} className="mini-badge mini-badge--mode">
          <span className="mono">{r.stage}</span>
          <span className="muted"> · {r.events}</span>
        </span>
      ))}
    </div>
  );
}

function formatNum(v: unknown): string {
  if (v === null || v === undefined) return "—";
  return String(v);
}
