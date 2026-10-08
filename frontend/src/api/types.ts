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

export type TaskStatus = "queued" | "running" | "waiting_approval" | "succeeded" | "failed" | "cancelled";

export interface Task {
  id: number;
  kind: "agent" | "workflow" | "command";
  objective: string;
  agent_slug: string | null;
  parent_id: number | null;
  status: TaskStatus;
  priority: number;
  input: Record<string, unknown>;
  output: string | null;
  output_data: Record<string, unknown> | null;
  error: string | null;
  attempts: number;
  max_attempts: number;
  next_attempt_at: string | null;
  model: string | null;
  cost_inr: string;
  tokens: number;
  created_by: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface CommandResponse {
  reply: string;
  intent: string;
  task_id: number | null;
  data: Record<string, unknown>;
}

export interface WorkflowInfo {
  slug: string;
  description: string;
  needs_ai_model: boolean;
  ready: boolean;
}

export interface Tool {
  slug: string;
  name: string;
  description: string;
  provider: string;
  cost_tier: string;
  permission: Permission;
  risk_level: "low" | "medium" | "high";
  input_schema: Record<string, unknown>;
  available: boolean;
  version: string;
}

export interface Approval {
  id: number;
  task_id: number | null;
  agent_slug: string;
  action: string;
  kind: string;
  details: Record<string, unknown>;
  estimated_cost_inr: string;
  risk_level: "low" | "medium" | "high";
  status: "pending" | "approved" | "rejected";
  decided_by: string | null;
  decided_at: string | null;
  note: string | null;
  created_at: string;
}

export interface MattEvent {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

interface Row {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface WebsiteAudit {
  url: string;
  website_score: number;
  scores: Record<string, number>;
  findings: string[];
  truth: string;
  title?: string;
  response_ms?: number;
}

export interface Business extends Row {
  name: string;
  category: string;
  city: string | null;
  country: string | null;
  location: string | null;
  website: string | null;
  public_phone: string | null;
  public_email: string | null;
  source: string;
  source_url: string | null;
  website_score: number | null;
  opportunity_score: number | null;
  technology_stack: string[];
  social_links: string[];
  audit: WebsiteAudit | null;
  audited_at: string | null;
  lead_status: string | null;
  outreach_status: string | null;
}

export type LeadStatus = "new" | "qualified" | "contacted" | "meeting" | "won" | "lost";

export interface Lead extends Row {
  business_id: number;
  status: LeadStatus;
  service: string;
  estimated_value_min_inr: string | null;
  estimated_value_max_inr: string | null;
  outreach_draft: string | null;
  next_action: string | null;
  notes: string | null;
  business: Business;
}

export interface Opportunity extends Row {
  title: string;
  category: string;
  description: string;
  factors: Record<string, number>;
  score: number;
  truth: string;
  status: string;
  evidence: string | null;
  source: string;
  task_id: number | null;
}

export interface Customer extends Row {
  name: string;
  company: string | null;
  email: string | null;
  status: string;
  notes: string | null;
}

export interface Product extends Row {
  name: string;
  kind: string;
  description: string;
  price_inr: string | null;
  billing: string | null;
  status: string;
  url: string | null;
}

export interface LedgerEntry extends Row {
  kind: "revenue" | "expense";
  amount_inr: string;
  category: string;
  description: string;
  occurred_on: string;
  recurring: boolean;
  agent_slug: string | null;
  recorded_by: string;
}

export interface Experiment extends Row {
  name: string;
  hypothesis: string;
  target: string | null;
  expected: string | null;
  budget_inr: string;
  result: string | null;
  decision: string | null;
  status: string;
}

export interface Knowledge extends Row {
  kind: string;
  title: string;
  content: string;
  tags: string[];
  agent_slug: string | null;
  source: string;
  expires_at: string | null;
}

export interface EarningSkill {
  slug: string;
  name: string;
  revenue_inr: number;
  revenue_today_inr: number;
  revenue_month_inr: number;
}

export interface Earnings {
  truth: string;
  timezone: string;
  date: string;
  today_inr: number;
  expenses_today_inr: number;
  week_inr: number;
  month_inr: number;
  total_inr: number;
  daily: { day: string; revenue_inr: number; expense_inr: number }[];
  by_stream: { category: string; month_inr: number; total_inr: number }[];
  earning_agents: { slug: string; name: string; today_inr: number; month_inr: number; total_inr: number; last_earned_on: string }[];
}

export interface Dashboard {
  earnings: Earnings;
  autopilot: Pick<AutopilotStatus, "enabled" | "last_action" | "last_cycle_at" | "next_cycle_at" | "cycles_today" | "active" | "ai_model_available">;
  revenue: {
    truth: string;
    today_inr: number;
    week_inr: number;
    earning_skills: EarningSkill[];
    month_inr: number;
    total_inr: number;
    expenses_month_inr: number;
    profit_month_inr: number;
    entries: number;
  };
  tasks: {
    by_status: Record<string, number>;
    active: number;
    recent: { id: number; objective: string; status: TaskStatus; agent: string | null; kind: string; created_at: string }[];
  };
  approvals_pending: number;
  pipeline: {
    businesses: number;
    audited: number;
    leads_by_status: Record<string, number>;
    pipeline_value_inr: { truth: string; min: number; max: number };
  };
  workforce: {
    agents: number;
    agents_with_work: number;
    top: { slug: string; name: string; tasks_completed: number; success_rate: number | null }[];
  };
  ai: {
    model_available: boolean;
    spent_today_inr: number;
    spent_month_inr: number;
    daily_budget_inr: number;
    monthly_budget_inr: number;
    calls_today: number;
  };
  opportunities: { id: number; title: string; score: number; truth: string }[];
}

export interface Analytics {
  tasks_daily: { day: string; total: number; succeeded: number; failed: number }[];
  ledger_monthly: { month: string; kind: string; category: string; amount_inr: number }[];
  models: { provider: string; model: string; calls: number; failures: number; tokens: number; cost_inr: number; avg_latency_ms: number }[];
  agents: { slug: string; name: string; completed: number; failed: number; success_rate: number | null }[];
  lead_funnel: Record<string, number>;
  website_scores: { truth: string; count: number; average: number | null; below_50: number };
  generated_at: string;
}

export interface SystemSettings {
  environment: string;
  owner_email: string | null;
  google_sign_in: boolean;
  models: { provider: string; model: string; tier: string; quality: number; paid: boolean; rate_limit: string; enabled: boolean }[];
  model_keys: Record<string, boolean>;
  free_models_only: boolean;
  allow_premium_models: boolean;
  daily_ai_budget_inr: number;
  monthly_ai_budget_inr: number;
  worker_enabled: boolean;
  email_sending: boolean;
}

export interface AutopilotStatus {
  enabled: boolean;
  cities: string[];
  categories: string[];
  interval_minutes: number;
  daily_outreach_drafts: number;
  daily_bot_tasks: number;
  bots_today: number;
  last_tick_at: string | null;
  free_models_only: boolean;
  last_cycle_at: string | null;
  next_cycle_at: string | null;
  last_action: string | null;
  cycles_today: number;
  active: number;
  ai_model_available: boolean;
  available_categories: string[];
  recent: { task_id: number; action: string; status: TaskStatus; result: string | null; created_at: string }[];
  latest_report: { title: string; content: string; created_at: string } | null;
}

export interface FreeModelSource {
  slug: string;
  name: string;
  env_var: string;
  signup_url: string;
  free_limits: string;
  note: string;
  recommended: boolean;
  connected: boolean;
  model: string | null;
  status: "ok" | "not_connected" | "error" | "no_free_model" | "not_checked";
  free_models: number;
  error: string | null;
  checked_at: string | null;
  calls_24h: number;
  failures_24h: number;
}
