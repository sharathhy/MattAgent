/** Every page in the spec. `phase` marks capabilities not built yet; those render "Coming soon". */
export interface NavItem {
  path: string;
  label: string;
  phase?: number;
  description: string;
}

export const NAV: NavItem[] = [
  { path: "/command-center", label: "Command Center", description: "Company overview" },
  { path: "/workforce", label: "Workforce Map", description: "AI organisation chart" },
  { path: "/agents", label: "Agents", description: "Agent and skill registry" },
  { path: "/tasks", label: "Tasks", phase: 2, description: "Task queue and execution history" },
  { path: "/workflows", label: "Workflows", phase: 2, description: "Multi-agent workflows" },
  { path: "/tools", label: "Tools", phase: 2, description: "Tool registry" },
  { path: "/approvals", label: "Approvals", phase: 3, description: "Human approval gate" },
  { path: "/analytics", label: "Analytics", phase: 3, description: "Performance analytics" },
  { path: "/opportunities", label: "Opportunities", phase: 4, description: "Opportunity engine" },
  { path: "/businesses", label: "Businesses", phase: 4, description: "Business discovery" },
  { path: "/leads", label: "Leads", phase: 4, description: "Lead pipeline" },
  { path: "/customers", label: "Customers", phase: 5, description: "Customer records" },
  { path: "/products", label: "Products", phase: 5, description: "AI SaaS factory" },
  { path: "/revenue", label: "Revenue", phase: 5, description: "Revenue portfolio" },
  { path: "/experiments", label: "Experiments", phase: 5, description: "Business experiments" },
  { path: "/memory", label: "Memory", phase: 7, description: "Knowledge and memory" },
  { path: "/audit-log", label: "Audit Log", description: "Traceable record of every change" },
  { path: "/settings", label: "Settings", phase: 8, description: "System configuration" },
];

export const PHASE_NAMES: Record<number, string> = {
  2: "Agent orchestration",
  3: "Command center",
  4: "Business intelligence",
  5: "Revenue engines",
  6: "Voice",
  7: "Self-evolving workforce",
  8: "Production hardening",
};
