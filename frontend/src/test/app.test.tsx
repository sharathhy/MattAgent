import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../api/client";
import { OWNER, mockApi, renderApp } from "./utils";

const SUMMARY = {
  total: 120,
  by_kind: { ceo: 1, executive: 9, skill: 100, meta: 10 },
  by_department: { sales: 11, marketing: 21 },
  by_status: { designed: 120 },
};

const AGENT = {
  slug: "lead-qualifier", name: "Lead Qualifier", role: "Lead Qualifier", kind: "skill",
  department: "sales", status: "designed", level: "standard", version: "1.0.0", cost_tier: "low",
  permissions: ["read", "write"], performance_score: null, success_rate: null, requires_approval: false,
  description: "Scores leads for fit and intent.", capabilities: ["lead scoring"], inputs: [], outputs: [],
  tools: ["crm"], dependencies: ["lead-researcher"], parent_slug: "cro", report_slugs: [],
  revenue_contribution: "0.00", tasks_completed: 0, tasks_failed: 0,
  created_at: "2026-10-08T00:00:00Z", last_upgraded_at: null,
  versions: [{ version: "1.0.0", change_summary: "Registered", created_by: "system:catalog", created_at: "2026-10-08T00:00:00Z" }],
};

afterEach(() => vi.unstubAllGlobals());

describe("authentication", () => {
  it("offers owner bootstrap on a fresh install", async () => {
    mockApi({ "/auth/status": { bootstrap_required: true, setup_code_required: false, web_bootstrap_enabled: true } });
    renderApp("/command-center");
    expect(await screen.findByText("Initialise owner account")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create owner and sign in" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Setup code")).not.toBeInTheDocument();
  });

  it("asks for the setup code on a public deployment", async () => {
    mockApi({ "/auth/status": { bootstrap_required: true, setup_code_required: true, web_bootstrap_enabled: true } });
    renderApp("/login");
    expect(await screen.findByLabelText("Setup code")).toBeRequired();
  });

  it("signs in and lands on the command center", async () => {
    mockApi({
      "/auth/status": { bootstrap_required: false, setup_code_required: false, web_bootstrap_enabled: true },
      "/auth/login": { access_token: "tok" },
      "/auth/me": OWNER,
      "/agents/summary": SUMMARY,
      "/health": { status: "ok", database: "ok", env: "test" },
    });
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "owner@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("MATT COMMAND CENTER")).toBeInTheDocument();
    expect(tokenStore.get()).toBe("tok");
  });

  it("signs the owner in with Google on a locked-down install", async () => {
    let callback: ((r: { credential: string }) => void) | undefined;
    vi.stubGlobal("google", {
      accounts: {
        id: {
          initialize: (c: { callback: typeof callback }) => (callback = c.callback),
          renderButton: (el: HTMLElement) => {
            const b = document.createElement("button");
            b.textContent = "Sign in with Google";
            b.onclick = () => callback?.({ credential: "google-id-token" });
            el.appendChild(b);
          },
        },
      },
    });
    const fetchMock = mockApi({
      "/auth/status": { bootstrap_required: true, setup_code_required: false, web_bootstrap_enabled: false, google_client_id: "cid" },
      "/auth/google": { access_token: "tok" },
      "/auth/me": OWNER,
      "/agents/summary": SUMMARY,
      "/health": { status: "ok", database: "ok", env: "test" },
    });
    renderApp("/login");
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: "Sign in with Google" }));
    expect(await screen.findByText("MATT COMMAND CENTER")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/auth/google"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ credential: "google-id-token" });
  });

  it("returns to login when the session is rejected", async () => {
    tokenStore.set("expired");
    mockApi({
      "/auth/me": () => ({ status: 401, body: { detail: "Not authenticated" } }),
      "/auth/status": { bootstrap_required: false, setup_code_required: false, web_bootstrap_enabled: true },
    });
    renderApp("/command-center");
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(tokenStore.get()).toBeNull();
  });
});

const DASHBOARD = {
  earnings: { truth: "fact", timezone: "Asia/Kolkata", date: "2026-10-08", today_inr: 5000, expenses_today_inr: 0,
    week_inr: 25000, month_inr: 25000, total_inr: 25000, daily: [], by_stream: [], earning_agents: [] },
  revenue: { truth: "fact", today_inr: 5000, week_inr: 25000,
    earning_skills: [{ slug: "sales-copywriter", name: "Sales Copywriter", revenue_inr: 25000, revenue_today_inr: 5000, revenue_month_inr: 25000 }],
    month_inr: 25000, total_inr: 25000, expenses_month_inr: 5000, profit_month_inr: 20000, entries: 2 },
  tasks: { by_status: { succeeded: 3, failed: 1 }, active: 2, recent: [
    { id: 7, objective: "Find gyms in Mysore", status: "running", agent: null, kind: "workflow", created_at: "2026-10-08T00:00:00Z" },
  ] },
  approvals_pending: 1,
  pipeline: { businesses: 10, audited: 6, leads_by_status: { new: 4 }, pipeline_value_inr: { truth: "assumption", min: 40000, max: 160000 } },
  workforce: { agents: 120, agents_with_work: 3, top: [] },
  ai: { model_available: false, spent_today_inr: 0, spent_month_inr: 0, daily_budget_inr: 0, monthly_budget_inr: 0, calls_today: 0 },
  opportunities: [],
};

const AUTOPILOT = {
  enabled: true, cities: ["Mysuru"], categories: ["gyms"], interval_minutes: 15, daily_outreach_drafts: 5, daily_bot_tasks: 48, bots_today: 2,
  last_tick_at: "2026-10-08T10:00:00Z", free_models_only: true,
  last_cycle_at: null, next_cycle_at: null, last_action: "Find gyms in Mysuru and rank website opportunities",
  cycles_today: 3, active: 1, ai_model_available: false, available_categories: ["gyms", "clinics"],
  recent: [], latest_report: null,
};

describe("command center", () => {
  it("shows live numbers computed from records", async () => {
    tokenStore.set("tok");
    mockApi({
      "/auth/me": OWNER,
      "/agents/summary": SUMMARY,
      "/dashboard": DASHBOARD,
      "/autopilot": AUTOPILOT,
      "/health": { status: "ok", database: "ok", env: "test" },
    });
    renderApp("/command-center");
    const tile = (await screen.findByText("Registered Agents")).parentElement;
    expect(tile).toHaveTextContent("120");
    await waitFor(() => expect(screen.getByText("Revenue This Month").parentElement).toHaveTextContent("₹25,000"));
    expect(screen.getByText("Profit This Month").parentElement).toHaveTextContent("₹20,000");
    expect(screen.getByText("Revenue Today").parentElement).toHaveTextContent("₹5,000");
    expect(screen.getByText("Skills Earning").parentElement).toHaveTextContent("Sales Copywriter");
    expect(screen.getByText("Pipeline").parentElement).toHaveTextContent(/Assumption/);
    expect(screen.getByText("AI Cost Today").parentElement).toHaveTextContent("No AI model key set");
    expect(screen.getByText("Find gyms in Mysore")).toBeInTheDocument();
    expect(await screen.findByText("Autopilot on")).toBeInTheDocument();
    expect(screen.getByText(/AI: free-tier models only/)).toBeInTheDocument();
    expect(screen.getByText(/2 skill-bot turns/)).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Autopilot" })).toHaveAttribute("aria-checked", "true");
    await waitFor(() => expect(screen.getByText(/Core ok/)).toBeInTheDocument());
    // HUD revenue panel: today's money and the skills earning it.
    expect(screen.getByLabelText("Revenue today")).toHaveTextContent("₹5,000");
    expect(screen.getByRole("region", { name: "Revenue" })).toHaveTextContent("Sales Copywriter");
  });
});

describe("agent detail", () => {
  it("states that no performance data exists instead of showing a score", async () => {
    tokenStore.set("tok");
    mockApi({ "/auth/me": OWNER, "/agents/lead-qualifier": AGENT });
    renderApp("/agents/lead-qualifier");
    expect(await screen.findByRole("heading", { name: "Lead Qualifier" })).toBeInTheDocument();
    expect(screen.getAllByText("No data yet")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "cro" })).toHaveAttribute("href", "/agents/cro");
  });
});

describe("working pages", () => {
  it("has no Coming soon page left", async () => {
    tokenStore.set("tok");
    const { NAV } = await import("../lib/navigation");
    expect(NAV.filter((n) => n.phase)).toEqual([]);
  });

  it("lets the owner approve an outreach draft", async () => {
    tokenStore.set("tok");
    const approval = {
      id: 3, task_id: 9, agent_slug: "sales-copywriter", action: "Send outreach email to Iron Gym", kind: "outreach",
      details: { lead_id: 1, to: "hi@iron.example", draft: "Subject: Your website" }, estimated_cost_inr: "0",
      risk_level: "high", status: "pending", decided_by: null, decided_at: null, note: null, created_at: "2026-10-08T00:00:00Z",
    };
    const fetchMock = mockApi({
      "/auth/me": OWNER,
      "/approvals": [approval],
      "/approvals/3/decide": { ...approval, status: "approved" },
    });
    renderApp("/approvals");
    expect(await screen.findByText("Subject: Your website")).toBeInTheDocument();
    expect(screen.getByText(/no email provider connected/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/approvals/3/decide"));
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ approve: true, note: null });
    });
  });

  it("hides approval buttons from people who cannot decide", async () => {
    tokenStore.set("tok");
    mockApi({
      "/auth/me": { ...OWNER, role: "admin" },
      "/approvals": [{ id: 3, task_id: null, agent_slug: "x", action: "Send email", kind: "outreach", details: {},
        estimated_cost_inr: "0", risk_level: "high", status: "pending", decided_by: null, decided_at: null, note: null,
        created_at: "2026-10-08T00:00:00Z" }],
    });
    renderApp("/approvals");
    expect(await screen.findByText("Only the owner can decide this.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("records revenue as a fact from the form", async () => {
    tokenStore.set("tok");
    const fetchMock = mockApi({
      "/auth/me": OWNER,
      "/ledger": (init?: RequestInit) =>
        init?.method === "POST" ? { status: 201, body: { id: 1 } } : { status: 200, body: [] },
    });
    renderApp("/revenue");
    expect(await screen.findByText("No revenue or expenses recorded yet.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Amount (₹)"), "25000");
    await userEvent.type(screen.getByLabelText("Description"), "Website for Iron Gym");
    await userEvent.type(screen.getByLabelText("Date"), "2026-10-01");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/ledger") && init?.method === "POST");
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        kind: "revenue", amount_inr: "25000", category: "websites", occurred_on: "2026-10-01", recurring: false,
      });
    });
  });

  it("asks customers to pay the owner's UPI ID and records money only when the owner confirms", async () => {
    tokenStore.set("tok");
    const fetchMock = mockApi({
      "/auth/me": OWNER,
      "/ledger": [{ id: 9, kind: "revenue", amount_inr: "100", category: "websites", description: "Earlier", occurred_on: "2026-10-01",
        recurring: false, customer_id: null, product_id: null, agent_slug: null, recorded_by: "1", created_at: "2026-10-01T00:00:00Z" }],
      "/payments/config": { money_rule: "receive_only", rule: "MATT only receives money.", configured: true, upi_id: "owner.test@ybl",
        payee_name: "MATT", problem: null, verification: "Mark it received once it shows in PhonePe." },
      "/payments": [{ id: 3, reference: "MATT000003", amount_inr: "15000.00", purpose: "Website for Mysore Dental", customer_id: null,
        category: "websites", status: "requested", upi_id: "owner.test@ybl", upi_link: "upi://pay?pa=owner.test%40ybl&am=15000.00&cu=INR",
        qr_svg: "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>", ledger_entry_id: null, created_at: "2026-10-08T00:00:00Z", received_at: null }],
      "/payments/3/received": { status: 200, body: {} },
    });
    renderApp("/revenue");
    expect(await screen.findByText("Website for Mysore Dental")).toBeInTheDocument();
    expect(screen.getAllByText("owner.test@ybl").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "Show QR" }));
    expect(screen.getByRole("img", { name: "UPI QR code for MATT000003" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in a UPI app" })).toHaveAttribute("href", expect.stringContaining("upi://pay"));
    await userEvent.click(screen.getByRole("button", { name: "Money received" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/payments/3/received") && init?.method === "POST")).toBe(true),
    );
  });

  it("lists tasks with their outcome", async () => {
    tokenStore.set("tok");
    mockApi({
      "/auth/me": OWNER,
      "/agents": [],
      "/tasks": [{
        id: 5, kind: "agent", objective: "Plan the launch", agent_slug: "ceo", parent_id: null, status: "failed",
        priority: 5, input: {}, output: null, output_data: null, error: "No AI model is configured", attempts: 1,
        max_attempts: 3, next_attempt_at: null, model: null, cost_inr: "0", tokens: 0, created_by: "1",
        created_at: "2026-10-08T00:00:00Z", started_at: null, finished_at: null,
      }],
    });
    renderApp("/tasks");
    await userEvent.click(await screen.findByText("Plan the launch"));
    expect(screen.getByText("No AI model is configured")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("shows what the Free Model Scout found and where to get missing keys", async () => {
    tokenStore.set("tok");
    mockApi({
      "/auth/me": OWNER,
      "/autopilot": AUTOPILOT,
      "/settings": {
        environment: "production", owner_email: "owner@example.com", google_sign_in: true, models: [],
        model_keys: { MATT_GEMINI_API_KEY: true }, free_models_only: true, allow_premium_models: false,
        daily_ai_budget_inr: 0, monthly_ai_budget_inr: 0, worker_enabled: true, email_sending: false,
      },
      "/models/free-sources": [
        { slug: "gemini", name: "Google Gemini (AI Studio)", env_var: "MATT_GEMINI_API_KEY", signup_url: "https://aistudio.google.com/apikey",
          free_limits: "Free tier", note: "", recommended: true, connected: true, model: "gemini-3.8-flash", status: "ok",
          free_models: 4, error: null, checked_at: "2026-10-08T10:00:00Z", calls_24h: 12, failures_24h: 1 },
        { slug: "groq", name: "Groq", env_var: "MATT_GROQ_API_KEY", signup_url: "https://console.groq.com/keys",
          free_limits: "1,000 a day", note: "", recommended: true, connected: false, model: null, status: "not_connected",
          free_models: 0, error: null, checked_at: null, calls_24h: 0, failures_24h: 0 },
      ],
    });
    renderApp("/settings");
    expect(await screen.findByText("gemini-3.8-flash")).toBeInTheDocument();
    expect(screen.getByText("(1 failed)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get a free key" })).toHaveAttribute("href", "https://console.groq.com/keys");
    expect(screen.getByRole("button", { name: "Scan now" })).toBeInTheDocument();
  });
});
