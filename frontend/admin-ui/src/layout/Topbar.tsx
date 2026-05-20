import { useAuth } from "../auth/AuthContext";

export function Topbar() {
  const { authMode } = useAuth();

  return (
    <header className="admin-shell__topbar">
      <div className="admin-shell__topbar-left">
        <h1 className="admin-shell__app-title">Admin console</h1>
        <span className="admin-shell__app-meta muted">
          FastAPI · консоль наблюдаемости · auth {authMode}
        </span>
      </div>
      <div className="admin-shell__topbar-right-col">
        <span className="admin-shell__topbar-zerocoder" title="Zerocoder">
          Zerocoder
        </span>
        <span className="admin-shell__topbar-zerocoder-rail" aria-hidden="true">
          &nbsp;
        </span>
      </div>
    </header>
  );
}
