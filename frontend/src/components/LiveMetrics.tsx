import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { Badge, inr } from "./kit";
import { ErrorState, Stat } from "./ui";

/** Command Center tiles. Every number comes from stored records via /api/dashboard. */
export function LiveMetrics() {
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 5000 });
  if (dash.isError) return <ErrorState error={dash.error} />;
  const d = dash.data;
  const v = (x: string | number | undefined) => (d ? x : "…");
  const leads = d ? Object.values(d.pipeline.leads_by_status).reduce((a, b) => a + b, 0) : 0;
  return (
    <div className="space-y-4">
      <section aria-label="Business metrics" className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-5">
        <Stat label="Revenue Today" value={v(inr(d?.revenue.today_inr))} hint="Fact · recorded today" />
        <Stat label="Revenue This Month" value={v(inr(d?.revenue.month_inr))} hint="Fact · recorded in Revenue" />
        <Stat label="Profit This Month" value={v(inr(d?.revenue.profit_month_inr))} hint="Fact · revenue minus expenses" />
        <Stat
          label="Pipeline"
          value={v(d && d.pipeline.pipeline_value_inr.max ? `${inr(d.pipeline.pipeline_value_inr.min)}–${inr(d.pipeline.pipeline_value_inr.max)}` : inr(0))}
          hint={`Assumption · ${leads} leads`}
        />
        <Stat label="Businesses Analysed" value={v(d?.pipeline.audited)} hint={`${d?.pipeline.businesses ?? 0} discovered`} />
        <Stat label="Tasks Running" value={v(d?.tasks.active)} hint="Queued or in progress" />
        <Stat label="Tasks Completed" value={v(d?.tasks.by_status.succeeded ?? 0)} hint={`${d?.tasks.by_status.failed ?? 0} failed`} />
        <Stat label="Human Approvals" value={v(d?.approvals_pending)} hint="Waiting for you" />
        <Stat
          label="AI Cost Today"
          value={v(inr(d?.ai.spent_today_inr))}
          hint={d ? (d.ai.model_available ? `${d.ai.calls_today} calls · limit ${inr(d.ai.daily_budget_inr)} paid` : "No AI model key set") : ""}
        />
        <Stat
          label="Skills Earning"
          value={v(d?.revenue.earning_skills.length)}
          hint={d?.revenue.earning_skills[0] ? `Top: ${d.revenue.earning_skills[0].name}` : "None recorded yet"}
        />
      </section>
      {d && d.tasks.recent.length > 0 && (
        <section className="panel p-4" aria-label="Recent activity">
          <div className="mb-2 flex justify-between">
            <h2 className="label">Recent activity</h2>
            <Link to="/tasks" className="text-xs text-accent hover:underline">All tasks</Link>
          </div>
          <ul className="space-y-1.5 text-sm">
            {d.tasks.recent.map((t) => (
              <li key={t.id} className="flex items-center gap-3">
                <Badge value={t.status} />
                <span className="min-w-0 flex-1 truncate">{t.objective}</span>
                <span className="font-mono text-xs text-muted">{t.agent ?? t.kind}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
