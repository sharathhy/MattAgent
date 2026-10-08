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

describe("command center", () => {
  it("shows real registry counts and never invents business metrics", async () => {
    tokenStore.set("tok");
    mockApi({
      "/auth/me": OWNER,
      "/agents/summary": SUMMARY,
      "/health": { status: "ok", database: "ok", env: "test" },
    });
    renderApp("/command-center");
    const tile = (await screen.findByText("Registered Agents")).parentElement;
    expect(tile).toHaveTextContent("120");
    const revenue = screen.getByText("Revenue Today").parentElement;
    expect(revenue).toHaveTextContent("Coming soon");
    expect(screen.queryByText(/₹/)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/System ok/)).toBeInTheDocument());
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

describe("unbuilt capabilities", () => {
  it("renders Coming soon for pages from later phases", async () => {
    tokenStore.set("tok");
    mockApi({ "/auth/me": OWNER });
    renderApp("/revenue");
    expect(await screen.findByRole("heading", { name: "Revenue" })).toBeInTheDocument();
    expect(screen.getByText(/Phase 5/)).toBeInTheDocument();
    expect(screen.getByText(/nothing here is simulated/)).toBeInTheDocument();
  });
});
