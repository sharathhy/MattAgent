import { useQuery } from "@tanstack/react-query";
import { Mic } from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { ErrorState, Loading, Panel, PendingStat, Stat } from "../components/ui";
import { titleCase } from "../lib/format";

export function CommandCenterPage() {
  const summary = useQuery({ queryKey: ["registry-summary"], queryFn: api.registrySummary });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 30_000 });

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="label">Autonomous company operating system</div>
          <h1 className="mt-1 font-mono text-2xl font-bold tracking-[0.25em] text-accent md:text-3xl">
            MATT COMMAND CENTER
          </h1>
        </div>
        <div className="panel flex items-center gap-2 px-3 py-2 text-xs">
          <span
            className={`h-2 w-2 rounded-full ${health.data?.status === "ok" ? "bg-ok shadow-[0_0_8px_var(--color-ok)]" : "bg-danger"}`}
            aria-hidden
          />
          System {health.data ? health.data.status : health.isError ? "unreachable" : "checking"}
          {health.data && <span className="text-muted">· DB {health.data.database} · {health.data.env}</span>}
        </div>
      </header>

      <section aria-label="Business metrics" className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <PendingStat label="Company Value" phase={5} />
        <PendingStat label="Revenue Today" phase={5} />
        <PendingStat label="Revenue This Month" phase={5} />
        <PendingStat label="Profit" phase={5} />
        <PendingStat label="Pipeline" phase={4} />
        <PendingStat label="Active Opportunities" phase={4} />
        <PendingStat label="Tasks Running" phase={2} />
        <PendingStat label="Tasks Completed" phase={2} />
        <PendingStat label="AI Cost" phase={2} />
        <PendingStat label="Human Approvals" phase={3} />
      </section>

      {summary.isPending && <Loading label="Loading workforce" />}
      {summary.isError && <ErrorState error={summary.error} />}
      {summary.data && (
        <>
          <section aria-label="Workforce" className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Registered Agents" value={summary.data.total} hint="CEO, executives, skills, meta-skills" />
            <Stat label="Executives" value={summary.data.by_kind.executive ?? 0} />
            <Stat label="Skills" value={summary.data.by_kind.skill ?? 0} />
            <Stat label="Self-upgrade Skills" value={summary.data.by_kind.meta ?? 0} />
          </section>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Workforce by department">
              <BarList data={summary.data.by_department} total={summary.data.total} />
            </Panel>
            <Panel title="Lifecycle status">
              <BarList data={summary.data.by_status} total={summary.data.total} />
              <p className="mt-4 text-xs text-muted">
                Agents are registered definitions. None executes work until the orchestrator ships in Phase 2, so
                no agent is shown as active. <Link to="/workforce" className="text-accent hover:underline">Open the workforce map</Link>
              </p>
            </Panel>
          </div>
        </>
      )}

      <Panel title="Command console">
        <div className="flex items-center gap-3">
          <input className="input" disabled placeholder="Matt, what should we do next?" aria-label="Command" />
          <button type="button" className="btn" disabled aria-label="Voice command">
            <Mic className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <p className="mt-2 text-xs text-muted">Coming soon · commands in Phase 2 (orchestrator), voice in Phase 6.</p>
      </Panel>
    </div>
  );
}

function BarList({ data, total }: { data: Record<string, number>; total: number }) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  return (
    <ul className="space-y-2">
      {rows.map(([key, n]) => (
        <li key={key} className="text-sm">
          <div className="flex justify-between">
            <span>{titleCase(key)}</span>
            <span className="font-mono text-muted">{n}</span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-slate-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-accent to-accent-2 transition-[width] duration-700"
              style={{ width: `${total ? (n / total) * 100 : 0}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
