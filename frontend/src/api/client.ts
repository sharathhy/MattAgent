import type {
  AiTest,
  AutopilotStatus,
  Diagnostics,
  SalesDesk,
  SalesOffer,
  ChangeConfig,
  ChangeRequest,
  AgentDetail,
  AgentSummary,
  Analytics,
  Approval,
  AuditLog,
  AuthStatus,
  Business,
  CommandResponse,
  Dashboard,
  FreeModelSource,
  Health,
  HierarchyNode,
  Lead,
  MattEvent,
  Opportunity,
  PaymentConfig,
  PaymentRequest,
  ReceivingAccount,
  RegistrySummary,
  SystemSettings,
  Task,
  Tool,
  User,
  WorkflowInfo,
} from "./types";

const TOKEN_KEY = "matt.token";

export const tokenStore = {
  get: (): string | null => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Called when the API rejects the session, so the app can return to the login screen. */
let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (fn: () => void) => {
  onUnauthorized = fn;
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`/api${path}`, { ...init, headers });
  if (res.status === 401 && token) {
    tokenStore.clear();
    onUnauthorized();
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail = typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
const send = <T>(method: "PUT" | "PATCH", path: string, body: unknown) =>
  request<T>(path, { method, body: JSON.stringify(body) });

const query = (params: Record<string, string | number | undefined>) => {
  const qs = new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => [k, String(v)]),
  ).toString();
  return qs ? `?${qs}` : "";
};

/** Simple record collections served by the generic CRUD endpoints. */
export type Collection = "customers" | "products" | "ledger" | "experiments" | "knowledge";

export interface AgentFilters {
  kind?: string;
  department?: string;
  status?: string;
  q?: string;
}

export const api = {
  health: () => request<Health>("/health"),
  authStatus: () => request<AuthStatus>("/auth/status"),
  bootstrap: (body: { email: string; password: string; full_name: string; setup_code?: string }) =>
    post<User>("/auth/bootstrap", body),
  login: (email: string, password: string) =>
    post<{ access_token: string }>("/auth/login", { email, password }),
  googleSignIn: (credential: string) =>
    post<{ access_token: string }>("/auth/google", { credential }),
  me: () => request<User>("/auth/me"),
  agents: (filters: AgentFilters = {}) => {
    const params = new URLSearchParams(
      Object.entries(filters).filter((e): e is [string, string] => Boolean(e[1])),
    );
    const qs = params.toString();
    return request<AgentSummary[]>(`/agents${qs ? `?${qs}` : ""}`);
  },
  agent: (slug: string) => request<AgentDetail>(`/agents/${encodeURIComponent(slug)}`),
  registrySummary: () => request<RegistrySummary>("/agents/summary"),
  hierarchy: () => request<HierarchyNode[]>("/agents/hierarchy"),
  auditLogs: () => request<AuditLog[]>("/audit-logs"),

  command: (text: string) => post<CommandResponse>("/command", { text }),
  dashboard: () => request<Dashboard>("/dashboard"),
  analytics: () => request<Analytics>("/analytics"),
  events: (afterId = 0) => request<MattEvent[]>(`/events${query({ after_id: afterId })}`),
  settings: () => request<SystemSettings>("/settings"),
  autopilot: () => request<AutopilotStatus>("/autopilot"),
  updateAutopilot: (body: Partial<Pick<AutopilotStatus, "enabled" | "cities" | "categories" | "interval_minutes" | "daily_outreach_drafts">>) =>
    send<AutopilotStatus>("PUT", "/autopilot", body),
  runAutopilot: () => post<Task | null>("/autopilot/run", {}),
  diagnostics: () => request<Diagnostics>("/diagnostics"),
  salesDesk: () => request<SalesDesk>("/sales"),
  priceOffer: (leadId: number, amount_inr: number) => post<SalesOffer>(`/sales/${leadId}/price`, { amount_inr }),
  offerSent: (leadId: number) => post<SalesOffer>(`/sales/${leadId}/sent`, {}),
  offerPaid: (leadId: number) => post<SalesOffer>(`/sales/${leadId}/paid`, {}),
  testAi: () => post<AiTest[]>("/diagnostics/test-ai", {}),
  paymentConfig: () => request<PaymentConfig>("/payments/config"),
  paymentRequests: () => request<PaymentRequest[]>("/payments"),
  requestPayment: (body: { amount_inr: number; purpose: string; category: string }) =>
    post<PaymentRequest>("/payments", body),
  paymentReceived: (id: number) => post<PaymentRequest>(`/payments/${id}/received`, {}),
  receivingAccounts: () => request<ReceivingAccount[]>("/payments/accounts"),
  addReceivingAccount: (body: Record<string, unknown>) => post<ReceivingAccount>("/payments/accounts", body),
  makePrimaryAccount: (id: number) => post<ReceivingAccount>(`/payments/accounts/${id}/primary`, {}),
  removeReceivingAccount: (id: number) => request<null>(`/payments/accounts/${id}`, { method: "DELETE" }),
  cancelPayment: (id: number) => post<PaymentRequest>(`/payments/${id}/cancel`, {}),
  changeConfig: () => request<ChangeConfig>("/changes/config"),
  changes: () => request<ChangeRequest[]>("/changes"),
  requestChange: (text: string) => post<ChangeRequest>("/changes", { request: text }),
  freeSources: () => request<FreeModelSource[]>("/models/free-sources"),
  runScout: () => post<FreeModelSource[]>("/models/scout", {}),

  tasks: (filters: { status?: string; agent?: string } = {}) => request<Task[]>(`/tasks${query(filters)}`),
  task: (id: number) => request<Task>(`/tasks/${id}`),
  createTask: (body: { objective: string; agent_slug: string; priority?: number }) => post<Task>("/tasks", body),
  cancelTask: (id: number) => post<Task>(`/tasks/${id}/cancel`, {}),
  retryTask: (id: number) => post<Task>(`/tasks/${id}/retry`, {}),

  workflows: () => request<WorkflowInfo[]>("/workflows"),
  runWorkflow: (slug: string, params: Record<string, unknown>) => post<Task>(`/workflows/${slug}/run`, { params }),
  tools: () => request<Tool[]>("/tools"),

  approvals: (status?: string) => request<Approval[]>(`/approvals${query({ status })}`),
  decideApproval: (id: number, approve: boolean, note?: string) =>
    post<Approval>(`/approvals/${id}/decide`, { approve, note: note ?? null }),

  businesses: (filters: { city?: string; category?: string; q?: string } = {}) =>
    request<Business[]>(`/businesses${query(filters)}`),
  auditBusiness: (id: number) => post<Task>(`/businesses/${id}/audit`, {}),
  deleteBusiness: (id: number) => request<undefined>(`/businesses/${id}`, { method: "DELETE" }),
  leads: (status?: string) => request<Lead[]>(`/leads${query({ status })}`),
  updateLead: (id: number, body: Partial<Pick<Lead, "status" | "next_action" | "notes">>) =>
    send<Lead>("PATCH", `/leads/${id}`, body),
  draftOutreach: (id: number) => post<Task>(`/leads/${id}/draft-outreach`, {}),
  opportunities: () => request<Opportunity[]>("/opportunities"),
  createOpportunity: (body: { title: string; category: string; description: string; factors: Record<string, number>; evidence?: string }) =>
    post<Opportunity>("/opportunities", body),
  updateOpportunity: (id: number, body: { status?: string; factors?: Record<string, number> }) =>
    send<Opportunity>("PATCH", `/opportunities/${id}`, body),

  list: <T>(collection: Collection) => request<T[]>(`/${collection}`),
  create: <T>(collection: Collection, body: Record<string, unknown>) => post<T>(`/${collection}`, body),
  update: <T>(collection: Collection, id: number, body: Record<string, unknown>) =>
    send<T>("PUT", `/${collection}/${id}`, body),
  remove: (collection: Collection, id: number) => request<undefined>(`/${collection}/${id}`, { method: "DELETE" }),
};
