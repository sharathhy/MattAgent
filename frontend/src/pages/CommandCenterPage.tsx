import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { BootSequence } from "../components/hud/BootSequence";
import { BrainCore } from "../components/hud/BrainCore";
import { CommsPanel } from "../components/hud/CommsPanel";
import { EventFeed } from "../components/hud/EventFeed";
import { HudClock } from "../components/hud/HudClock";
import { RevenuePanel } from "../components/hud/RevenuePanel";
import { LiveMetrics } from "../components/LiveMetrics";
import { ErrorState, Loading, Panel, Stat } from "../components/ui";
import { VoiceLockPanel } from "../components/VoiceLockPanel";
import { titleCase } from "../lib/format";
import { useVoice } from "../voice/VoiceProvider";

export function CommandCenterPage() {
  const summary = useQuery({ queryKey: ["registry-summary"], queryFn: api.registrySummary });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 30_000 });
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 5000 });
  const voice = useVoice();

  return (
    <div className="space-y-6">
      <BootSequence />
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="label">Autonomous company operating system</div>
          <h1 className="hud-title mt-1 text-xl font-bold md:text-2xl">MATT COMMAND CENTER</h1>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <Chip ok={health.data?.status === "ok"} label={`Core ${health.data ? health.data.status : health.isError ? "offline" : "…"}`} />
            <Chip ok={health.data?.database === "ok"} label={`Database ${health.data?.database ?? "…"}`} />
            <Chip ok={dash.data?.ai.model_available} label={dash.data ? (dash.data.ai.model_available ? "AI model online" : "No AI model key") : "AI …"} />
            <Chip ok={!["off", "unsupported", "error", "blocked"].includes(voice.state)} label={`Voice ${voice.state}`} />
            {dash.data && <Chip ok label={`${dash.data.workforce.agents} agents · ${dash.data.tasks.active} tasks live`} />}
          </div>
        </div>
        <HudClock />
      </header>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(260px,320px)_minmax(0,1fr)_minmax(300px,380px)]">
        <div className="order-3 space-y-5 lg:order-1">
          <RevenuePanel />
        </div>
        <div className="order-1 lg:order-2">
          <BrainCore />
        </div>
        <div className="order-2 space-y-5 lg:order-3">
          <CommsPanel />
          <EventFeed />
        </div>
      </div>

      <h2 className="label border-t border-line pt-5">Operations</h2>
      <LiveMetrics />

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
                Lifecycle stages track how far each agent has been tested. Any agent can take tasks today.{" "}
                <Link to="/workforce" className="text-accent hover:underline">Open the workforce map</Link>
              </p>
            </Panel>
          </div>
        </>
      )}

      <VoiceLockPanel />
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

function Chip({ ok, label }: { ok: boolean | undefined; label: string }) {
  return (
    <span className="flex items-center gap-1.5 rounded border border-line bg-slate-950/50 px-2 py-0.5 font-mono uppercase tracking-wider text-slate-300">
      <span
        className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-ok shadow-[0_0_6px_var(--color-ok)]" : ok === undefined ? "bg-slate-500" : "bg-danger"}`}
        aria-hidden
      />
      {label}
    </span>
  );
}
