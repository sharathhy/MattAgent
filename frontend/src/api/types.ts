export type Role = "owner" | "admin" | "operator" | "viewer";
export type Permission = "read" | "write" | "external_action" | "financial" | "admin";
export type AgentKind = "ceo" | "executive" | "skill" | "meta";
export type AgentStatus =
  | "discovered"
  | "designed"
  | "built"
  | "testing"
  | "evaluated"
  | "deployed"
  | "upgrading"
  | "retired";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
}

export interface AgentSummary {
  slug: string;
  name: string;
  role: string;
  kind: AgentKind;
  department: string;
  status: AgentStatus;
  level: string;
  version: string;
  cost_tier: string;
  permissions: Permission[];
  performance_score: number | null;
  success_rate: number | null;
  requires_approval: boolean;
}

export interface AgentVersion {
  version: string;
  change_summary: string;
  created_by: string;
  created_at: string;
}

export interface AgentDetail extends AgentSummary {
  description: string;
  capabilities: string[];
  inputs: string[];
  outputs: string[];
  tools: string[];
  dependencies: string[];
  parent_slug: string | null;
  report_slugs: string[];
  revenue_contribution: string;
  tasks_completed: number;
  tasks_failed: number;
  created_at: string;
  last_upgraded_at: string | null;
  versions: AgentVersion[];
}

export interface HierarchyNode {
  slug: string;
  name: string;
  role: string;
  kind: AgentKind;
  department: string;
  status: AgentStatus;
  children: HierarchyNode[];
}

export interface RegistrySummary {
  total: number;
  by_kind: Record<string, number>;
  by_department: Record<string, number>;
  by_status: Record<string, number>;
}

export interface Health {
  status: "ok" | "degraded";
  database: string;
  env: string;
}

export interface AuditLog {
  id: number;
  actor_type: string;
  actor_id: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
  request_id: string | null;
  created_at: string;
}

export interface AuthStatus {
  bootstrap_required: boolean;
  setup_code_required: boolean;
  web_bootstrap_enabled: boolean;
  google_client_id: string | null;
}
