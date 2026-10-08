import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { useAuth } from "./lib/auth";
import { AgentDetailPage } from "./pages/AgentDetailPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { BusinessesPage } from "./pages/BusinessesPage";
import { LeadsPage } from "./pages/LeadsPage";
import { OpportunitiesPage } from "./pages/OpportunitiesPage";
import { CustomersPage, ExperimentsPage, MemoryPage, ProductsPage, RevenuePage } from "./pages/RecordPages";
import { SalesDeskPage } from "./pages/SalesDeskPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TasksPage } from "./pages/TasksPage";
import { ToolsPage } from "./pages/ToolsPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";
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
        <Route path="/tasks" element={<TasksPage />} />
        <Route path="/workflows" element={<WorkflowsPage />} />
        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/opportunities" element={<OpportunitiesPage />} />
        <Route path="/businesses" element={<BusinessesPage />} />
        <Route path="/sales" element={<SalesDeskPage />} />
        <Route path="/leads" element={<LeadsPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/products" element={<ProductsPage />} />
        <Route path="/revenue" element={<RevenuePage />} />
        <Route path="/experiments" element={<ExperimentsPage />} />
        <Route path="/memory" element={<MemoryPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/command-center" replace />} />
      </Route>
    </Routes>
  );
}
