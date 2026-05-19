import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Topbar() {
  const {
    authenticated,
    email,
    platformRole,
    authMode,
    loginAvailable,
    needsLogin,
    logout,
  } = useAuth();

  return (
    <header className="admin-shell__topbar">
      <div className="admin-shell__topbar-left">
        <h1 className="admin-shell__app-title">Admin console</h1>
        <span className="admin-shell__app-meta muted">
          FastAPI · консоль наблюдаемости · auth {authMode}
        </span>
      </div>
      <div className="admin-shell__topbar-right-col">
        {loginAvailable && !needsLogin ? (
          <div className="admin-shell__auth-meta">
            {authenticated && email ? (
              <span className="admin-shell__auth-user" title={platformRole ?? ""}>
                {email}
                {platformRole ? ` · ${platformRole}` : ""}
              </span>
            ) : (
              <span className="muted">без сессии</span>
            )}
            {authenticated && authMode !== "disabled" ? (
              <button
                type="button"
                className="admin-shell__auth-logout"
                onClick={() => void logout()}
              >
                Выйти
              </button>
            ) : null}
            {!authenticated && authMode !== "disabled" ? (
              <Link to="/login" className="admin-shell__auth-login-link">
                Войти
              </Link>
            ) : null}
          </div>
        ) : null}
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
