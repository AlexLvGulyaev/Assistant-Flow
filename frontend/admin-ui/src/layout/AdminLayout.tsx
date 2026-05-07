import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { ContentContainer } from "./ContentContainer";

export function AdminLayout() {
  return (
    <div className="admin-shell">
      <Sidebar />
      <div className="admin-shell__column">
        <Topbar />
        <ContentContainer>
          <Outlet />
        </ContentContainer>
      </div>
    </div>
  );
}
