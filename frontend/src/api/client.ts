import type {
  AgentDetail,
  AuthStatus,
  AgentSummary,
  AuditLog,
  Health,
  HierarchyNode,
  RegistrySummary,
  User,
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
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

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
};
