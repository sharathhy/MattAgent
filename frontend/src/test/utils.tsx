import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { App } from "../App";
import { AuthProvider } from "../lib/auth";

type Routes = Record<string, unknown | ((init?: RequestInit) => { status: number; body: unknown })>;

/** Stub fetch with a map of `/api/...` path -> JSON body (or a responder for status codes). */
export function mockApi(routes: Routes) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const path = url.replace(/^\/api/, "").split("?")[0] ?? "";
    const route = routes[path];
    if (route === undefined) return new Response(JSON.stringify({ detail: "not mocked" }), { status: 404 });
    const { status, body } = typeof route === "function" ? route(init) : { status: 200, body: route };
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function renderApp(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export const OWNER = { id: 1, email: "owner@example.com", full_name: "Owner", role: "owner", is_active: true };
