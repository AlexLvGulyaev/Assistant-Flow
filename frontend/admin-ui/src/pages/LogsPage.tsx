import { useEffect, useState } from "react";
import { fetchRecentLogs, type LogItem } from "../api/client";
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
      <h1 className="page__title">Recent logs</h1>
      <p className="page__lead muted">
        Last {PAGE_LIMIT} rows from <code>/api/logs/recent</code>
      </p>

      {loading ? (
        <div className="skeleton skeleton--wide" />
      ) : error ? (
        <div className="panel panel--error" role="alert">
          {error}
        </div>
      ) : items.length === 0 ? (
        <MetricCard title="Events">
          <p className="muted">No log entries in this window.</p>
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
                  <th>Route</th>
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
                    <td className="mono">
                      {row.route ?? "—"}
                      {row.mode ? ` / ${row.mode}` : ""}
                    </td>
                    <td className="mono truncate" title={row.execution_id ?? ""}>
                      {shortId(row.execution_id)}
                    </td>
                    <td className="details-preview">
                      {previewDetails(row.details)}
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

function previewDetails(d: LogItem["details"]): string {
  if (d == null) return "—";
  if (typeof d === "string") return d.length > 120 ? d.slice(0, 120) + "…" : d;
  try {
    const s = JSON.stringify(d);
    return s.length > 120 ? s.slice(0, 120) + "…" : s;
  } catch {
    return "—";
  }
}
