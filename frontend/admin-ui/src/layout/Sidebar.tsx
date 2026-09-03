import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../hooks/useTheme";
import { navGroupsForPermissions } from "../navigation/routes";

export function Sidebar() {
  const {
    hasPermission,
    authenticated,
    email,
    displayName,
    platformRole,
    authMode,
    loginAvailable,
    needsLogin,
    logout,
  } = useAuth();
  // Тема день/ночь (канон APL): кнопка внизу сайдбара, полная ширина.
  const { theme, toggle: toggleTheme } = useTheme();
  const sessionLabel = displayName ?? email;
  const groups = navGroupsForPermissions(hasPermission);

  return (
    <aside className="admin-shell__sidebar" aria-label="Основная навигация">
      <div className="admin-shell__brand">
        <span className="admin-shell__brand-title">Assistant Flow</span>
        <span className="admin-shell__brand-sub">Операции</span>
      </div>
      {/* Демо-бейдж — канон RF .op-sidebar-demo / AIC / MAB: под брендом,
          виден только в демо-сессии (роль demo, read-only). */}
      {platformRole === "demo" ? (
        <div className="admin-shell__sidebar-demo">🔒 Демо-режим: только просмотр</div>
      ) : null}
      <nav className="admin-shell__nav admin-shell__nav--main">
        {/* Меню-канон APL: группы с заголовками, пункты = эмодзи + текст. */}
        {groups.map((group) => (
          <div key={group.title} className="admin-shell__nav-group">
            <div className="admin-shell__nav-group-title">{group.title}</div>
            {group.items.map((item) => (
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
                  {item.icon}
                </span>
                <span className="admin-shell__nav-label">{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      {loginAvailable && !needsLogin ? (
        <div className="admin-shell__sidebar-footer">
          <button
            type="button"
            className="admin-shell__sidebar-btn"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему"}
          >
            <span aria-hidden>{theme === "dark" ? "☀️" : "🌙"}</span>
            {theme === "dark" ? "Светлая тема" : "Тёмная тема"}
          </button>
          <div className="admin-shell__sidebar-session" aria-label="Сессия Assistant Flow">
            {authenticated && sessionLabel ? (
              <span className="admin-shell__sidebar-user-email" title={sessionLabel}>
                {sessionLabel}
              </span>
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