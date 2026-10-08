import { useQuery } from "@tanstack/react-query";
import { IndianRupee, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import { inr } from "../kit";

/** Money first: today's revenue, current earnings and the skills that are earning. All from the revenue ledger. */
export function RevenuePanel() {
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard, refetchInterval: 5000 });
  const r = dash.data?.revenue;
  const skills = r?.earning_skills ?? [];
  const loading = !r;

  return (
    <section aria-label="Revenue" className="panel p-4">
      <div className="flex items-center justify-between">
        <h2 className="label flex items-center gap-1.5">
          <IndianRupee className="h-3.5 w-3.5 text-ok" aria-hidden /> Daily revenue
        </h2>
        <span className="font-mono text-[10px] uppercase tracking-wider text-emerald-300">fact · ledger</span>
      </div>
      <div className="hud-num glow mt-2 text-4xl text-emerald-300" aria-label="Revenue today">
        {loading ? "…" : r.today_inr === undefined ? "—" : inr(r.today_inr)}
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 border-t border-line pt-3 text-center">
        <Mini label="This month" value={loading ? "…" : inr(r.month_inr)} />
        <Mini label="All time" value={loading ? "…" : inr(r.total_inr)} />
        <Mini label="Profit (mo)" value={loading ? "…" : inr(r.profit_month_inr)} tone={r && r.profit_month_inr < 0 ? "text-danger" : undefined} />
      </div>

      <h3 className="label mt-5 mb-2 flex items-center gap-1.5">
        <TrendingUp className="h-3.5 w-3.5 text-hot" aria-hidden /> Earning skills
      </h3>
      {skills.length === 0 ? (
        <p className="text-sm text-muted">
          No skill has earned money yet. Revenue you record in <Link to="/revenue" className="text-accent hover:underline">Revenue</Link> is
          credited to the skill that won it.
        </p>
      ) : (
        <ul className="space-y-2">
          {skills.slice(0, 6).map((s) => {
            const top = skills[0]?.revenue_inr || 1;
            return (
              <li key={s.slug} className="text-sm">
                <div className="flex items-baseline justify-between gap-2">
                  <Link to={`/agents/${s.slug}`} className="truncate hover:text-accent">
                    <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-ok shadow-[0_0_6px_var(--color-ok)]" aria-hidden />
                    {s.name}
                  </Link>
                  <span className="hud-num shrink-0 text-xs text-emerald-200">
                    {inr(s.revenue_inr)}
                    {s.revenue_today_inr > 0 && <span className="ml-1 text-ok">+{inr(s.revenue_today_inr)}</span>}
                  </span>
                </div>
                <div className="mt-1 h-1 rounded bg-slate-800">
                  <div className="h-full rounded bg-gradient-to-r from-ok to-accent" style={{ width: `${(s.revenue_inr / top) * 100}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Mini({ label, value, tone = "text-cyan-100" }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className={`hud-num text-sm ${tone}`}>{value}</div>
      <div className="mt-0.5 text-[10px] uppercase tracking-wider text-muted">{label}</div>
    </div>
  );
}
