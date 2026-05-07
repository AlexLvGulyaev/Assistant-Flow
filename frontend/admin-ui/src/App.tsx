import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { OverviewPage } from "./pages/OverviewPage";
import { LogsPage } from "./pages/LogsPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/logs" element={<LogsPage />} />
      </Routes>
    </Layout>
  );
}
