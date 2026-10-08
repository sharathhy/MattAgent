import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { Empty, PageHeader, Table, Truth, inr } from "../components/kit";
import { ErrorState, Loading, Panel, Stat } from "../components/ui";

export function AnalyticsPage() {
  const data = useQuery({ queryKey: ["analytics"], queryFn: api.analytics, refetchInterval: 15000 });
  if (data.isPending) return <Loading />;
  if (data.isError) return <ErrorState error={data.error} />;
  const a = data.data;
  const maxDay = Math.max(1, ...a.tasks_daily.map((d) => d.total));
  const revenue = a.ledger_monthly.filter((r) => r.kind === "revenue").reduce((s, r) => s + r.amount_inr, 0);
  const expense = a.ledger_monthly.filter((r) => r.kind === "expense").reduce((s, r) => s + r.amount_inr, 0);
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Performance" title="Analytics" />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Recorded revenue" value={inr(revenue)} hint="Fact · from the ledger" />
        <Stat label="Recorded expenses" value={inr(expense)} hint="Fact · from the ledger" />
        <Stat label="AI calls" value={a.models.reduce((s, m) => s + m.calls, 0)} hint={inr(a.models.reduce((s, m) => s + m.cost_inr, 0)) + " spent"} />
        <Stat label="Avg website score" value={a.website_scores.average ?? "—"} hint={`Estimate · ${a.website_scores.count} audited, ${a.website_scores.below_50} below 50`} />
      </div>
      <Panel title="Tasks, last 14 days">
        {a.tasks_daily.length === 0 ? (
          <p className="text-sm text-muted">No tasks in the last 14 days.</p>
        ) : (
          <div className="flex h-40 items-end gap-2">
            {a.tasks_daily.map((d) => (
              <div key={d.day} className="flex flex-1 flex-col items-center gap-1" title={`${d.day}: ${d.succeeded} ok, ${d.failed} failed`}>
                <div className="flex w-full flex-1 flex-col justify-end">
                  <div className="w-full rounded-t bg-rose-400/80" style={{ height: `${(d.failed / maxDay) * 100}%` }} />
                  <div className="w-full bg-cyan-400/80" style={{ height: `${((d.total - d.failed) / maxDay) * 100}%` }} />
                </div>
                <span className="font-mono text-[9px] text-muted">{d.day.slice(5)}</span>
              </div>
            ))}
          </div>
        )}
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Lead funnel">
          {Object.keys(a.lead_funnel).length === 0 ? <p className="text-sm text-muted">No leads yet.</p> : (
            <ul className="space-y-1 text-sm">
              {Object.entries(a.lead_funnel).map(([k, v]) => (
                <li key={k} className="flex justify-between"><span>{k}</span><span className="font-mono">{v}</span></li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Agent performance">
          {a.agents.length === 0 ? <p className="text-sm text-muted">No agent has finished a task yet.</p> : (
            <ul className="space-y-1 text-sm">
              {a.agents.map((g) => (
                <li key={g.slug} className="flex justify-between gap-2">
                  <span>{g.name}</span>
                  <span className="font-mono text-xs text-muted">{g.completed} done · {g.failed} failed · {g.success_rate === null ? "—" : `${Math.round(g.success_rate * 100)}%`}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <h2 className="label">AI model usage</h2>
      {a.models.length === 0 ? <Empty>No AI calls yet.</Empty> : (
        <Table head={["Model", "Calls", "Failures", "Tokens", "Cost", "Avg latency"]}>
          {a.models.map((m) => (
            <tr key={m.model} className="border-b border-line/50">
              <td className="p-3 font-mono text-xs">{m.provider}/{m.model}</td>
              <td className="p-3">{m.calls}</td>
              <td className="p-3">{m.failures}</td>
              <td className="p-3">{m.tokens.toLocaleString()}</td>
              <td className="p-3">{inr(m.cost_inr)}</td>
              <td className="p-3">{m.avg_latency_ms} ms</td>
            </tr>
          ))}
        </Table>
      )}
      <h2 className="label flex gap-2">Ledger by month <Truth value="fact" /></h2>
      {a.ledger_monthly.length === 0 ? <Empty>No revenue or expenses recorded yet. Add them on the Revenue page.</Empty> : (
        <Table head={["Month", "Type", "Category", "Amount"]}>
          {a.ledger_monthly.map((r) => (
            <tr key={`${r.month}-${r.kind}-${r.category}`} className="border-b border-line/50">
              <td className="p-3 font-mono text-xs">{r.month}</td>
              <td className="p-3">{r.kind}</td>
              <td className="p-3">{r.category}</td>
              <td className="p-3">{inr(r.amount_inr)}</td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
