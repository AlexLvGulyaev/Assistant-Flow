import { useCallback, useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";

function formatCheckedAt(d: Date): string {
  return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
}

export function Topbar() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastOkAt, setLastOkAt] = useState<Date | null>(null);

  const loadHealth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const h = await fetchHealth();
      setHealth(h);
      setLastOkAt(new Date());
    } catch (e) {
      setHealth(null);
      setError(e instanceof Error ? e.message : "Ошибка проверки health");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHealth();
  }, [loadHealth]);

  const pg =
    health?.dependencies &&
    typeof health.dependencies === "object" &&
    "postgres" in health.dependencies
      ? (health.dependencies as Record<string, { status?: string }>).postgres
      : undefined;

  const backendLabel = loading
    ? "checking"
    : error
      ? "unreachable"
      : health?.status ?? "—";

  return (
    <header className="admin-shell__topbar">
      <div className="admin-shell__topbar-left">
        <h1 className="admin-shell__app-title">Admin console</h1>
        <span className="admin-shell__app-meta muted">
          FastAPI · консоль наблюдаемости
        </span>
      </div>
      <div className="admin-shell__topbar-right">
        {pg?.status ? (
          <span className="admin-shell__topbar-kv muted">
            Postgres{" "}
            <StatusBadge status={pg.status} />
          </span>
        ) : null}
        <span className="admin-shell__topbar-kv muted">
          Бэкенд <StatusBadge status={backendLabel} />
        </span>
        {health?.timestamp ? (
          <span className="admin-shell__topbar-kv muted mono" title="Время сервера">
            API {health.timestamp.slice(0, 19)}
          </span>
        ) : null}
        {lastOkAt ? (
          <span className="admin-shell__topbar-kv muted mono" title="Последнее успешное обновление">
            Проверено {formatCheckedAt(lastOkAt)}
          </span>
        ) : null}
        <button
          type="button"
          className="admin-shell__refresh"
          onClick={() => void loadHealth()}
          disabled={loading}
        >
          Обновить health
        </button>
        {error ? (
          <span className="admin-shell__topbar-err" title={error}>
            {error.length > 48 ? error.slice(0, 48) + "…" : error}
          </span>
        ) : null}
      </div>
    </header>
  );
}
