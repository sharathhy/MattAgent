import { useQuery } from "@tanstack/react-query";
import { ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { ErrorState, Loading, StatusBadge } from "../components/ui";
import { titleCase } from "../lib/format";

const KINDS = ["ceo", "executive", "skill", "meta"];

export function AgentsPage() {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [department, setDepartment] = useState("");
  const summary = useQuery({ queryKey: ["registry-summary"], queryFn: api.registrySummary });
  const agents = useQuery({
    queryKey: ["agents", { q, kind, department }],
    queryFn: () => api.agents({ q, kind, department }),
    placeholderData: (prev) => prev,
  });
  const departments = Object.keys(summary.data?.by_department ?? {}).sort();

  return (
    <div className="space-y-5">
      <header>
        <div className="label">Registry</div>
        <h1 className="mt-1 text-2xl font-semibold">Agents & Skills</h1>
      </header>
      <div className="flex flex-wrap gap-3">
        <input className="input max-w-xs" placeholder="Search agents" aria-label="Search agents" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input w-auto" aria-label="Kind" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">All kinds</option>
          {KINDS.map((k) => <option key={k} value={k}>{titleCase(k)}</option>)}
        </select>
        <select className="input w-auto" aria-label="Department" value={department} onChange={(e) => setDepartment(e.target.value)}>
          <option value="">All departments</option>
          {departments.map((d) => <option key={d} value={d}>{titleCase(d)}</option>)}
        </select>
      </div>
      {agents.isPending && <Loading />}
      {agents.isError && <ErrorState error={agents.error} />}
      {agents.data && (
        <>
          <div className="label">{agents.data.length} agents</div>
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {agents.data.map((a) => (
              <li key={a.slug}>
                <Link to={`/agents/${a.slug}`} className="panel block p-4 transition hover:border-accent/50">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate font-medium">{a.name}</div>
                      <div className="text-xs text-muted">{titleCase(a.department)} · {titleCase(a.kind)}</div>
                    </div>
                    <StatusBadge status={a.status} />
                  </div>
                  <div className="mt-3 flex items-center gap-3 font-mono text-[11px] text-muted">
                    <span>v{a.version}</span>
                    <span>cost: {a.cost_tier}</span>
                    {a.requires_approval && (
                      <span className="flex items-center gap-1 text-warn" title="Holds a high-risk permission; uses require owner approval">
                        <ShieldAlert className="h-3 w-3" aria-hidden /> approval-gated
                      </span>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
