import { Route, Routes } from "react-router-dom";
import { AdminLayout } from "./layout/AdminLayout";
import { AudioPage } from "./pages/AudioPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { ExitPage } from "./pages/ExitPage";
import { ImagesPage } from "./pages/ImagesPage";
import { LogsPage } from "./pages/LogsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RagPage } from "./pages/RagPage";
import { SummaryPage } from "./pages/SummaryPage";
import { TextPage } from "./pages/TextPage";

export default function App() {
  return (
    <Routes>
      <Route path="exit" element={<ExitPage />} />
      <Route element={<AdminLayout />}>
        <Route index element={<OverviewPage />} />
        <Route path="summary" element={<SummaryPage />} />
        <Route path="text" element={<TextPage />} />
        <Route path="rag" element={<RagPage />} />
        <Route path="images" element={<ImagesPage />} />
        <Route path="audio" element={<AudioPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="logs" element={<LogsPage />} />
      </Route>
    </Routes>
  );
}
