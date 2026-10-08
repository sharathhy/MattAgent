import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import { ErrorState, Loading, Panel, StatusBadge } from "../components/ui";
import { formatDate, titleCase } from "../lib/format";

function Tags({ items }: { items: string[] }) {
  if (items.length === 0) return <span className="text-sm text-muted">None</span>;
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((i) => (
        <li key={i} className="rounded-md border border-line bg-slate-900/60 px-2 py-0.5 text-xs">{i}</li>
      ))}
    </ul>
  );
}

/** Shows a measured value, or says plainly that nothing has been measured. */
function Measured({ value, suffix = "" }: { value: number | null; suffix?: string }) {
  return value === null ? <span className="text-muted">No data yet</span> : <>{value}{suffix}</>;
}

export function AgentDetailPage() {
  const { slug = "" } = useParams();
  const agent = useQuery({ queryKey: ["agent", slug], queryFn: () => api.agent(slug) });

  if (agent.isPending) return <Loading />;
  if (agent.isError) return <ErrorState error={agent.error} />;
  const a = agent.data;

  return (
    <div className="space-y-5">
      <Link to="/agents" className="label hover:text-accent">← Agents</Link>
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">{a.name}</h1>
        <StatusBadge status={a.status} />
        <span className="font-mono text-xs text-muted">v{a.version} · {a.level}</span>
      </header>
      <p className="max-w-3xl text-slate-300">{a.description}</p>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Profile">
          <dl className="space-y-2 text-sm">
            <Row k="Role" v={a.role} />
            <Row k="Kind" v={titleCase(a.kind)} />
            <Row k="Department" v={titleCase(a.department)} />
            <Row k="Reports to" v={a.parent_slug ? <Link className="text-accent hover:underline" to={`/agents/${a.parent_slug}`}>{a.parent_slug}</Link> : "Owner"} />
            <Row k="Direct reports" v={a.report_slugs.length} />
            <Row k="Cost tier" v={a.cost_tier} />
            <Row k="Created" v={formatDate(a.created_at)} />
            <Row k="Last upgrade" v={a.last_upgraded_at ? formatDate(a.last_upgraded_at) : "Never"} />
          </dl>
        </Panel>
        <Panel title="Performance">
          <dl className="space-y-2 text-sm">
            <Row k="Performance score" v={<Measured value={a.performance_score} />} />
            <Row k="Success rate" v={<Measured value={a.success_rate} suffix="%" />} />
            <Row k="Tasks completed" v={a.tasks_completed} />
            <Row k="Tasks failed" v={a.tasks_failed} />
            <Row k="Revenue contribution" v={`₹${a.revenue_contribution}`} />
          </dl>
          <p className="mt-3 text-xs text-muted">Recorded facts only, updated as this agent finishes tasks.</p>
        </Panel>
        <Panel title="Permissions">
          <Tags items={a.permissions} />
          {a.requires_approval && (
            <p className="mt-3 text-xs text-warn">Holds a high-risk permission. Every use requires owner approval.</p>
          )}
          <p className="mt-3 text-xs text-muted">Only the owner can change permissions; agents can never change their own.</p>
        </Panel>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Capabilities"><Tags items={a.capabilities} /></Panel>
        <Panel title="Tools"><Tags items={a.tools} /></Panel>
        <Panel title="Inputs"><Tags items={a.inputs} /></Panel>
        <Panel title="Outputs"><Tags items={a.outputs} /></Panel>
        <Panel title="Dependencies"><Tags items={a.dependencies} /></Panel>
        <Panel title="Version history">
          <ol className="space-y-2 text-sm">
            {a.versions.map((v) => (
              <li key={v.version + v.created_at}>
                <span className="font-mono text-accent">v{v.version}</span> {v.change_summary}
                <div className="text-xs text-muted">{formatDate(v.created_at)} · {v.created_by}</div>
              </li>
            ))}
          </ol>
        </Panel>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted">{k}</dt>
      <dd className="text-right">{v}</dd>
    </div>
  );
}
