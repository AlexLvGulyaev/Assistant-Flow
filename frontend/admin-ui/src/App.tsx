import { Route, Routes } from "react-router-dom";
import { AdminLayout } from "./layout/AdminLayout";
import { AudioPage } from "./pages/AudioPage";
import { ImagesPage } from "./pages/ImagesPage";
import { LogsPage } from "./pages/LogsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { SummaryPage } from "./pages/SummaryPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="summary" element={<SummaryPage />} />
        <Route path="text" element={<PlaceholderPage title="Text" />} />
        <Route path="rag" element={<PlaceholderPage title="RAG" />} />
        <Route path="images" element={<ImagesPage />} />
        <Route path="audio" element={<AudioPage />} />
        <Route
          path="documents"
          element={<PlaceholderPage title="Documents" />}
        />
        <Route path="logs" element={<LogsPage />} />
      </Route>
    </Routes>
  );
}
