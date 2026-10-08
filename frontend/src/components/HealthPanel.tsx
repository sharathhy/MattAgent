import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { ActionError, Badge, useAction } from "./kit";
import { formatDate } from "../lib/format";
import { ErrorState, Panel } from "./ui";

const TONE = { error: "border-rose-400/40 text-rose-200", warn: "border-amber-400/40 text-amber-200", info: "border-sky-400/40 text-sky-200" };

/** Admin view of why the bots are or aren't working, with the fix for each problem, so no logs are needed. */
export function HealthPanel() {
  const report = useQuery({ queryKey: ["diagnostics"], queryFn: api.diagnostics, refetchInterval: 15000 });
  const test = useAction(() => api.testAi(), [["diagnostics"]]);
  if (report.isError) return <ErrorState error={report.error} />;
  const d = report.data;
  return (
    <Panel title="System health">
      {!d ? (
        <p className="text-sm text-muted">Checking…</p>
      ) : (
        <div className="space-y-3 text-sm">
          <p className={d.healthy ? "text-ok" : "text-rose-300"}>
            {d.healthy ? "Everything needed for the bots is working." : "Something is stopping the bots. Fix the red items first."}
          </p>
          {d.problems.length > 0 && (
            <ul className="space-y-2">
              {d.problems.map((p, i) => (
                <li key={i} className={`rounded-lg border p-3 ${TONE[p.level]}`}>
                  <p>{p.text}</p>
                  <p className="mt-1 text-xs text-slate-300">Fix: {p.fix}</p>
                </li>
              ))}
            </ul>
          )}
          <dl className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
            <Item label="Worker heartbeat" value={d.worker.last_heartbeat_at ? formatDate(d.worker.last_heartbeat_at) : "never"} />
            <Item label="AI answers, last hour" value={String(d.ai_answers_last_hour)} />
            <Item label="Tasks waiting / running" value={`${d.worker.queued} / ${d.worker.running}`} />
            <Item label="Failed tasks, 24h" value={String(d.worker.failed_24h)} />
          </dl>
          <div>
            <div className="label mb-1">Free AI models</div>
            {d.models.length === 0 && <p className="text-xs text-muted">None connected.</p>}
            <ul className="space-y-1 text-xs">
              {d.models.map((m) => (
                <li key={m.provider}>
                  <span className="font-mono">{m.provider}</span>: {m.calls_24h - m.failures_24h} of {m.calls_24h} calls worked in 24h
                  {m.last_error && <span className="block truncate text-rose-300">Last error: {m.last_error}</span>}
                </li>
              ))}
            </ul>
            <button type="button" className="btn mt-2 px-2.5 py-1 text-xs" disabled={test.isPending} onClick={() => test.mutate(undefined)}>
              {test.isPending ? "Testing…" : "Test AI now"}
            </button>
            {test.data && (
              <ul className="mt-2 space-y-1 text-xs">
                {test.data.length === 0 && <li className="text-rose-300">No free AI model is connected.</li>}
                {test.data.map((t) => (
                  <li key={t.provider} className={t.ok ? "text-ok" : "text-rose-300"}>
                    {t.provider} ({t.model}): {t.ok ? `answered "${t.reply}" in ${t.latency_ms} ms` : t.error}
                  </li>
                ))}
              </ul>
            )}
            <ActionError error={test.error} />
          </div>
          {d.bots.length > 0 && (
            <div>
              <div className="label mb-1">Latest bot turns</div>
              <ul className="space-y-1 text-xs">
                {d.bots.slice(0, 6).map((b) => (
                  <li key={b.task_id} className="flex items-start gap-2">
                    <Badge value={b.status} />
                    <span className="min-w-0 flex-1">
                      {b.agent}
                      {b.provider && <span className="text-muted"> on {b.provider}</span>}
                      {(b.error ?? b.result) && <span className={`block truncate ${b.error ? "text-rose-300" : "text-muted"}`}>{b.error ?? b.result}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {d.ready_for_you.length > 0 && (
            <div>
              <div className="label mb-1">Ready for you to launch</div>
              <ul className="space-y-1 text-xs">
                {d.ready_for_you.map((x) => (
                  <li key={x.id}>
                    <span className="font-semibold">{x.name}</span>
                    {x.next_step && <span className="block text-muted">{x.next_step}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line/60 p-2">
      <dt className="text-muted">{label}</dt>
      <dd className="font-mono">{value}</dd>
    </div>
  );
}
