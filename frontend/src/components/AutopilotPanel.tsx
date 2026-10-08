import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { AutopilotStatus } from "../api/types";
import { ActionError, Badge, Field, useAction, useCan } from "./kit";
import { formatDate } from "../lib/format";
import { ErrorState, Panel } from "./ui";

/** On/off switch and live feed for MATT's self-directed work. `full` adds targeting settings. */
export function AutopilotPanel({ full = false }: { full?: boolean }) {
  const status = useQuery({ queryKey: ["autopilot"], queryFn: api.autopilot, refetchInterval: 5000 });
  const isOwner = useCan("owner");
  const canRun = useCan("admin");
  const toggle = useAction((enabled: boolean) => api.updateAutopilot({ enabled }), [["autopilot"], ["dashboard"]]);
  const runNow = useAction(() => api.runAutopilot(), [["autopilot"], ["tasks"]]);
  if (status.isError) return <ErrorState error={status.error} />;
  const s = status.data;
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-3">
        <span className={`h-2.5 w-2.5 rounded-full ${s?.enabled ? "animate-pulse bg-ok shadow-[0_0_10px_var(--color-ok)]" : "bg-slate-600"}`} aria-hidden />
        <h2 className="font-semibold">Autopilot {s ? (s.enabled ? "on" : "off") : ""}</h2>
        <span className="min-w-0 flex-1 truncate text-sm text-muted">
          {s?.enabled
            ? `${s.last_action ?? "Starting"} · ${s.cycles_today} actions today${s.next_cycle_at ? ` · next ${formatDate(s.next_cycle_at)}` : ""}`
            : "MATT works only when you ask."}
        </span>
        {canRun && s?.enabled && (
          <button type="button" className="btn bg-slate-700 text-slate-100" onClick={() => runNow.mutate(undefined)} disabled={runNow.isPending}>
            Run next step now
          </button>
        )}
        {isOwner && s && (
          <button
            type="button"
            role="switch"
            aria-checked={s.enabled}
            aria-label="Autopilot"
            onClick={() => toggle.mutate(!s.enabled)}
            disabled={toggle.isPending}
            className={`relative h-7 w-12 rounded-full transition ${s.enabled ? "bg-accent" : "bg-slate-700"}`}
          >
            <span className={`absolute top-1 h-5 w-5 rounded-full bg-white transition-all ${s.enabled ? "left-6" : "left-1"}`} />
          </button>
        )}
      </div>
      <p className="mt-2 text-xs text-muted">
        When on, the CEO picks the most valuable next step on a schedule: the daily report, finding and auditing leads,
        researching opportunities{s && !s.ai_model_available ? " (needs an AI key)" : ""}, and drafting pitches that wait
        in Approvals. It never sends, spends or publishes on its own.
      </p>
      <ActionError error={toggle.error ?? runNow.error} />
      {full && s && <Targets status={s} canEdit={isOwner} />}
      {s && s.recent.length > 0 && (
        <ul className="mt-3 space-y-1.5 text-sm">
          {s.recent.slice(0, full ? 10 : 4).map((r) => (
            <li key={r.task_id} className="flex items-center gap-3">
              <Badge value={r.status} />
              <span className="min-w-0 flex-1 truncate">{r.action}</span>
              <span className="hidden max-w-xs truncate text-xs text-muted md:inline">{r.result ?? ""}</span>
            </li>
          ))}
        </ul>
      )}
      {full && s?.latest_report && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm text-accent">{s.latest_report.title}</summary>
          <pre className="mt-2 whitespace-pre-wrap font-sans text-sm text-slate-300">{s.latest_report.content}</pre>
        </details>
      )}
    </Panel>
  );
}

function Targets({ status, canEdit }: { status: AutopilotStatus; canEdit: boolean }) {
  const [cities, setCities] = useState(status.cities.join(", "));
  const [categories, setCategories] = useState(status.categories);
  const [minutes, setMinutes] = useState(status.interval_minutes);
  const [drafts, setDrafts] = useState(status.daily_outreach_drafts);
  const save = useAction(
    () =>
      api.updateAutopilot({
        cities: cities.split(",").map((c) => c.trim()).filter(Boolean),
        categories,
        interval_minutes: minutes,
        daily_outreach_drafts: drafts,
      }),
    [["autopilot"]],
  );
  return (
    <div className="mt-4 space-y-3 border-t border-line pt-4">
      <div className="grid gap-3 md:grid-cols-3">
        <Field label="Cities (comma separated)">
          <input className="input" value={cities} disabled={!canEdit} onChange={(e) => setCities(e.target.value)} />
        </Field>
        <Field label="Minutes between steps">
          <input className="input" type="number" min={10} max={1440} value={minutes} disabled={!canEdit} onChange={(e) => setMinutes(Number(e.target.value))} />
        </Field>
        <Field label="Outreach drafts per day">
          <input className="input" type="number" min={0} max={50} value={drafts} disabled={!canEdit} onChange={(e) => setDrafts(Number(e.target.value))} />
        </Field>
      </div>
      <div>
        <div className="label mb-2">Niches</div>
        <div className="flex flex-wrap gap-2">
          {status.available_categories.map((c) => {
            const on = categories.includes(c);
            return (
              <button
                key={c}
                type="button"
                disabled={!canEdit}
                aria-pressed={on}
                onClick={() => setCategories(on ? categories.filter((x) => x !== c) : [...categories, c])}
                className={`rounded-full border px-3 py-1 text-xs ${on ? "border-accent bg-accent/15 text-accent" : "border-line text-slate-400"}`}
              >
                {c}
              </button>
            );
          })}
        </div>
      </div>
      {canEdit && (
        <button type="button" className="btn" onClick={() => save.mutate(undefined)} disabled={save.isPending || categories.length === 0}>
          Save targets
        </button>
      )}
      {save.isSuccess && <p className="text-xs text-ok">Saved.</p>}
      <ActionError error={save.error} />
    </div>
  );
}
