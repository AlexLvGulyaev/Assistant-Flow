import { NavLink } from "react-router-dom";
import { NAV_ITEMS } from "../navigation/routes";

export function Sidebar() {
  return (
    <aside className="admin-shell__sidebar" aria-label="Основная навигация">
      <div className="admin-shell__brand">
        <span className="admin-shell__brand-title">Assistant Flow</span>
        <span className="admin-shell__brand-sub">Операции</span>
      </div>
      <nav className="admin-shell__nav">
        {NAV_ITEMS.map((item) => (
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
    </aside>
  );
}
