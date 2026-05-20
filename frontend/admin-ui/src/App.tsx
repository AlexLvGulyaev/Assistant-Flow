import { useEffect } from "react";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AdminLayout } from "./layout/AdminLayout";
import { AuditPage } from "./pages/AuditPage";
import { AudioPage } from "./pages/AudioPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ExitPage } from "./pages/ExitPage";
import { ImagesPage } from "./pages/ImagesPage";
import { LoginPage } from "./pages/LoginPage";
import { LogsPage } from "./pages/LogsPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { MemoryPage } from "./pages/MemoryPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RagPage } from "./pages/RagPage";
import { RetrievalSettingsPage } from "./pages/RetrievalSettingsPage";
import { SummaryPage } from "./pages/SummaryPage";
import { TextPage } from "./pages/TextPage";

function AuthSessionGuard() {
  const { loading, needsLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    if (!loading && needsLogin && location.pathname !== "/login") {
      navigate("/login", {
        replace: true,
        state: { from: location.pathname },
      });
    }
  }, [loading, needsLogin, location.pathname, navigate]);
  return null;
}

export default function App() {
  return (
    <>
      <AuthSessionGuard />
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route path="exit" element={<ExitPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AdminLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="summary" element={<SummaryPage />} />
          <Route path="text" element={<TextPage />} />
          <Route path="rag" element={<RagPage />} />
          <Route path="images" element={<ImagesPage />} />
          <Route path="audio" element={<AudioPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="retrieval" element={<RetrievalSettingsPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="memory" element={<MemoryPage />} />
          <Route path="evaluation" element={<EvaluationPage />} />
          <Route path="audit" element={<AuditPage />} />
        </Route>
      </Route>
    </Routes>
    </>
  );
}
