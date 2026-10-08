import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { ComingSoon, Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import { NAV } from "./lib/navigation";
import { AgentDetailPage } from "./pages/AgentDetailPage";
import { AgentsPage } from "./pages/AgentsPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { CommandCenterPage } from "./pages/CommandCenterPage";
import { LoginPage } from "./pages/LoginPage";
import { WorkforcePage } from "./pages/WorkforcePage";

function RequireAuth() {
  const { user, loading } = useAuth();
  if (loading) return <Loading label="Authenticating" />;
  if (!user) return <Navigate to="/login" replace />;
  return <Layout />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route index element={<Navigate to="/command-center" replace />} />
        <Route path="/command-center" element={<CommandCenterPage />} />
        <Route path="/workforce" element={<WorkforcePage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/agents/:slug" element={<AgentDetailPage />} />
        <Route path="/audit-log" element={<AuditLogPage />} />
        {NAV.map(
          (n) =>
            n.phase && (
              <Route
                key={n.path}
                path={n.path}
                element={<ComingSoon title={n.label} phase={n.phase} description={n.description} />}
              />
            ),
        )}
        <Route path="*" element={<Navigate to="/command-center" replace />} />
      </Route>
    </Routes>
  );
}
