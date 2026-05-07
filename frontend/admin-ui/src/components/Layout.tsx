import { Link, NavLink } from "react-router-dom";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { fetchHealth, type HealthResponse } from "../api/client";
import { StatusBadge } from "./StatusBadge";

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const h = await fetchHealth();
        if (!cancelled) {
          setHealth(h);
          setHealthError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setHealth(null);
          setHealthError(e instanceof Error ? e.message : "Health fetch failed");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    const id = setInterval(async () => {
      try {
        const h = await fetchHealth();
        if (!cancelled) {
          setHealth(h);
          setHealthError(null);
        }
      } catch {
        if (!cancelled)
          setHealthError((prev) => prev ?? "Health poll failed");
      }
    }, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const statusLabel = loading
    ? "…"
    : healthError
      ? "unreachable"
      : health?.status ?? "—";

  return (
    <div className="layout">
      <aside className="layout__sidebar" aria-label="Primary navigation">
        <div className="layout__brand">
          <Link to="/" className="layout__brand-link">
            Assistant Flow
          </Link>
          <span className="layout__brand-sub">Admin console</span>
        </div>
        <nav className="layout__nav">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              "layout__nav-link" + (isActive ? " layout__nav-link--active" : "")
            }
          >
            Overview
          </NavLink>
          <NavLink
            to="/logs"
            className={({ isActive }) =>
              "layout__nav-link" + (isActive ? " layout__nav-link--active" : "")
            }
          >
            Logs
          </NavLink>
        </nav>
      </aside>
      <div className="layout__main">
        <header className="layout__topbar">
          <div className="layout__topbar-spacer" />
          <div className="layout__health">
            <span className="layout__health-label">API</span>
            <StatusBadge status={statusLabel} />
            {health?.version ? (
              <span className="layout__meta muted">{health.version}</span>
            ) : null}
            {healthError ? (
              <span className="layout__meta layout__meta--warn" title={healthError}>
                {healthError.length > 40
                  ? healthError.slice(0, 40) + "…"
                  : healthError}
              </span>
            ) : null}
          </div>
        </header>
        <main className="layout__content">{children}</main>
      </div>
    </div>
  );
}
