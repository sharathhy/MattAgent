/** Every page in the spec. */
export interface NavItem {
  path: string;
  label: string;
  /** Set only for pages that are not built yet (none at the moment). */
  phase?: number;
  description: string;
}

export const NAV: NavItem[] = [
  { path: "/command-center", label: "Command Center", description: "Company overview" },
  { path: "/workforce", label: "Workforce Map", description: "AI organisation chart" },
  { path: "/agents", label: "Agents", description: "Agent and skill registry" },
  { path: "/tasks", label: "Tasks", description: "Task queue and execution history" },
  { path: "/workflows", label: "Workflows", description: "Multi-agent workflows" },
  { path: "/tools", label: "Tools", description: "Tool registry" },
  { path: "/approvals", label: "Approvals", description: "Human approval gate" },
  { path: "/analytics", label: "Analytics", description: "Performance analytics" },
  { path: "/opportunities", label: "Opportunities", description: "Opportunity engine" },
  { path: "/businesses", label: "Businesses", description: "Business discovery" },
  { path: "/leads", label: "Leads", description: "Lead pipeline" },
  { path: "/customers", label: "Customers", description: "Customer records" },
  { path: "/products", label: "Products", description: "AI SaaS factory" },
  { path: "/revenue", label: "Revenue", description: "Revenue portfolio" },
  { path: "/trading", label: "Trading", description: "300-bot trading desk and demat account" },
  { path: "/experiments", label: "Experiments", description: "Business experiments" },
  { path: "/memory", label: "Memory", description: "Knowledge and memory" },
  { path: "/audit-log", label: "Audit Log", description: "Traceable record of every change" },
  { path: "/settings", label: "Settings", description: "System configuration" },
];
