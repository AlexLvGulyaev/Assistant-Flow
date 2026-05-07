import { useEffect, useState } from "react";
import { fetchRecentLogs, type LogItem } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { MetricCard } from "../components/MetricCard";
import { StatusBadge } from "../components/StatusBadge";

const PAGE_LIMIT = 20;

export function LogsPage() {
  const [items, setItems] = useState<LogItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchRecentLogs(PAGE_LIMIT);
        if (!cancelled) setItems(res.items ?? []);
      } catch (e) {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load logs");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="page">
      <h1 className="page__title">Logs</h1>
      <p className="page__lead muted">
        Last {PAGE_LIMIT} rows · <code>/api/logs/recent</code>
      </p>

      {loading ? (
        <LoadingState label="Loading log entries…" />
      ) : error ? (
        <div className="panel panel--error page__mt" role="alert">
          {error}
        </div>
      ) : items.length === 0 ? (
        <MetricCard title="Events">
          <EmptyState message="No log entries returned for this request." />
        </MetricCard>
      ) : (
        <MetricCard title={`Events (${items.length})`}>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Stage</th>
                  <th>Status</th>
                  <th>Route / mode</th>
                  <th>Execution</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row, i) => (
                  <tr key={`${row.execution_id ?? ""}-${i}`}>
                    <td className="mono nowrap">{fmtTime(row.created_at)}</td>
                    <td className="mono">{row.stage ?? "—"}</td>
                    <td>
                      <StatusBadge status={row.status ?? "—"} />
                    </td>
                    <td>
                      <div className="route-mode-cell">
                        {row.route ? (
                          <span className="mini-badge mini-badge--route">
                            {row.route}
                          </span>
                        ) : (
                          <span className="muted">—</span>
                        )}
                        {row.mode ? (
                          <span className="mini-badge mini-badge--mode">
                            {row.mode}
                          </span>
                        ) : null}
                      </div>
                    </td>
                    <td className="mono truncate" title={row.execution_id ?? ""}>
                      {shortId(row.execution_id)}
                    </td>
                    <td className="log-details-cell">
                      <details className="log-details">
                        <summary className="log-details__summary mono">
                          {previewSummary(row.details)}
                        </summary>
                        <pre className="log-details__json mono">
                          {formatDetailsJson(row.details)}
                        </pre>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </MetricCard>
      )}
    </div>
  );
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
  } catch {
    return iso.slice(0, 19);
  }
}

function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.length > 12 ? id.slice(0, 8) + "…" : id;
}

function previewSummary(d: LogItem["details"]): string {
  if (d == null) return "∅ empty";
  if (typeof d === "string") return d.length > 56 ? d.slice(0, 56) + "…" : d;
  try {
    const s = JSON.stringify(d);
    return s.length > 56 ? s.slice(0, 56) + "…" : s || "{}";
  } catch {
    return "?";
  }
}

function formatDetailsJson(d: LogItem["details"]): string {
  if (d == null) return "null";
  if (typeof d === "string") return d;
  try {
    return JSON.stringify(d, null, 2);
  } catch {
    return String(d);
  }
}
