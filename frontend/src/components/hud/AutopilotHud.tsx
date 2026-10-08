import { useQuery } from "@tanstack/react-query";
import { Bot, FastForward } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { ActionError, Badge, useAction, useCan } from "../kit";

function countdown(iso: string | null, now: number): string {
  if (!iso) return "—";
  const s = Math.max(0, Math.round((new Date(iso).getTime() - now) / 1000));
  if (s === 0) return "now";
  const m = Math.floor(s / 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}:${String(s % 60).padStart(2, "0")}`;
}

function ago(iso: string, now: number): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  return s < 60 ? `${s}s ago` : s < 3600 ? `${Math.floor(s / 60)}m ago` : `${Math.floor(s / 3600)}h ago`;
}

/** The scheduler heartbeats every minute or so; a long silence means the server is asleep or stuck. */
const heartbeatOk = (iso: string | null, now: number) => iso !== null && now - new Date(iso).getTime() < 5 * 60_000;

/** Autopilot under the brain: the big engage switch, what MATT is doing on its own, and when it acts next. */
export function AutopilotHud() {
  const status = useQuery({ queryKey: ["autopilot"], queryFn: api.autopilot, refetchInterval: 5000 });
  const isOwner = useCan("owner");
  const canRun = useCan("admin");
  const toggle = useAction((enabled: boolean) => api.updateAutopilot({ enabled }), [["autopilot"], ["dashboard"]]);
  const runNow = useAction(() => api.runAutopilot(), [["autopilot"], ["tasks"], ["dashboard"]]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const s = status.data;
  const on = s?.enabled ?? false;

  return (
    <section
      aria-label="Autopilot"
      className={`panel mt-4 w-full max-w-2xl p-4 transition-shadow ${on ? "shadow-[0_0_40px_rgb(251_146_60/0.18)]" : ""}`}
    >
      <div className="flex flex-wrap items-center gap-3">
        <Bot className={`h-6 w-6 ${on ? "text-hot" : "text-slate-500"}`} aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className={`hud-title text-sm ${on ? "!text-hot" : "!text-slate-400 [text-shadow:none]"}`}>
            Autopilot {s ? (on ? "on" : "off") : ""}
          </h2>
          <p className="truncate text-sm text-slate-300">
            {!s ? "…" : on ? (s.last_action ?? "Choosing the most valuable next step…") : "MATT works only when you ask."}
          </p>
        </div>
        {isOwner && s && (
          <button
            type="button"
            role="switch"
            aria-checked={on}
            aria-label="Autopilot"
            onClick={() => toggle.mutate(!on)}
            disabled={toggle.isPending}
            className={`hud-title relative rounded-md border px-4 py-2 text-xs transition ${
              on
                ? "border-hot/70 bg-hot/15 !text-hot shadow-[0_0_18px_rgb(251_146_60/0.4)]"
                : "border-accent/60 bg-accent/10 hover:bg-accent/25"
            }`}
          >
            {on ? "Engaged" : "Engage"}
          </button>
        )}
      </div>

      {s && on && (
        <div className="mt-3 grid grid-cols-2 gap-2 border-t border-line pt-3 text-center sm:grid-cols-4">
          <Readout label="Next step in" value={countdown(s.next_cycle_at, now)} />
          <Readout label="Actions today" value={String(s.cycles_today)} />
          <Readout label={`${s.bots_today} skill-bot turns`} value={`${s.bots_today}/${s.daily_bot_tasks}`} />
          <Readout label="Running now" value={String(s.active)} />
        </div>
      )}

      {s && on && s.recent.length > 0 && (
        <ul className="mt-3 space-y-1.5 text-sm">
          {s.recent.slice(0, 3).map((r) => (
            <li key={r.task_id} className="flex items-center gap-2">
              <Badge value={r.status} />
              <span className="min-w-0 flex-1 truncate">{r.action}</span>
            </li>
          ))}
        </ul>
      )}

      {s && (
        <p className="mt-2 flex items-center gap-1.5 font-mono text-[11px] text-muted">
          <span className={`h-1.5 w-1.5 rounded-full ${heartbeatOk(s.last_tick_at, now) ? "animate-pulse bg-ok" : "bg-warn"}`} aria-hidden />
          Scheduler {s.last_tick_at ? `last checked in ${ago(s.last_tick_at, now)}` : "hasn't checked in yet"}
          <span className={`ml-auto ${s.free_models_only ? "text-emerald-300" : "text-warn"}`}>
            {s.free_models_only ? "AI: free-tier models only" : "AI: paid models allowed within budget"}
          </span>
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
        <span className="min-w-0 flex-1">
          Finds and audits leads, researches opportunities{s && !s.ai_model_available ? " (needs an AI key)" : ""}, writes the
          daily report and drafts pitches for your approval. It never sends, spends or publishes on its own.
        </span>
        {canRun && on && (
          <button type="button" className="btn px-2.5 py-1 text-[11px]" onClick={() => runNow.mutate(undefined)} disabled={runNow.isPending}>
            <FastForward className="h-3.5 w-3.5" aria-hidden /> Run next step
          </button>
        )}
        <Link to="/settings" className="text-accent hover:underline">
          Targets
        </Link>
      </div>
      <ActionError error={toggle.error ?? runNow.error} />
    </section>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="hud-num text-lg text-orange-200">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
    </div>
  );
}
