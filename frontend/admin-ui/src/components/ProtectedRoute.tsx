import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { LoadingState } from "./LoadingState";

export function ProtectedRoute() {
  const { loading, needsLogin } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="auth-gate">
        <LoadingState label="Проверка сессии…" />
      </div>
    );
  }

  if (needsLogin) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
