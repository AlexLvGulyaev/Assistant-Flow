import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { navItemsForPermissions } from "../navigation/routes";

export function Sidebar() {
  const {
    hasPermission,
    authenticated,
    email,
    displayName,
    platformRole,
    isDemo,
    authMode,
    loginAvailable,
    needsLogin,
    logout,
  } = useAuth();
  // Демо-стандарт APL: роль demo помечается эмодзи-маской 🎭 (канон LQ/RF).
  const sessionLabel = displayName ?? email;
  const items = navItemsForPermissions(hasPermission);

  return (
    <aside className="admin-shell__sidebar" aria-label="Основная навигация">
      <div className="admin-shell__brand">
        <span className="admin-shell__brand-title">Assistant Flow</span>
        <span className="admin-shell__brand-sub">Операции</span>
      </div>
      <nav className="admin-shell__nav admin-shell__nav--main">
        {items.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.end ?? false}
            className={({ isActive }) =>
              "admin-shell__nav-link" +
              (isActive ? " admin-shell__nav-link--active" : "") +
              (item.placeholder ? " admin-shell__nav-link--placeholder" : "")
            }
          >
            <span className="admin-shell__nav-icon" aria-hidden>
              ◇
            </span>
            <span className="admin-shell__nav-label">{item.label}</span>
          </NavLink>
        ))}
      </nav>
      {loginAvailable && !needsLogin ? (
        <div className="admin-shell__sidebar-footer">
          <div className="admin-shell__sidebar-session" aria-label="Сессия Assistant Flow">
            {authenticated && sessionLabel ? (
              <>
                <span className="admin-shell__sidebar-user-email" title={sessionLabel}>
                  {isDemo ? `🎭 ${sessionLabel}` : sessionLabel}
                </span>
                {platformRole ? (
                  <span className="admin-shell__sidebar-user-role muted">{platformRole}</span>
                ) : null}
              </>
            ) : (
              <span className="admin-shell__sidebar-user-email muted">без сессии</span>
            )}
            {authenticated && authMode !== "disabled" ? (
              <button
                type="button"
                className="admin-shell__sidebar-logout"
                onClick={() => void logout()}
              >
                Выйти
              </button>
            ) : null}
            {!authenticated && authMode !== "disabled" ? (
              <Link to="/login" className="admin-shell__sidebar-login-link">
                Войти
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </aside>
  );
}
