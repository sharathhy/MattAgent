import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "../api/client";
import type { WorkflowInfo } from "../api/types";
import { ActionError, Badge, Field, PageHeader, useAction, useCan } from "../components/kit";
import { ErrorState, Loading, Panel } from "../components/ui";
import { formatDate, titleCase } from "../lib/format";

export const CATEGORIES = [
  "restaurants", "gyms", "dentists", "salons", "real estate", "construction", "law firms", "accountants",
  "clinics", "hotels", "retail", "logistics", "education", "automotive", "home services", "professional services",
];

export function WorkflowsPage() {
  const workflows = useQuery({ queryKey: ["workflows"], queryFn: api.workflows });
  const runs = useQuery({ queryKey: ["tasks", "workflows"], queryFn: () => api.tasks(), refetchInterval: 3000 });
  const recent = runs.data?.filter((t) => t.kind === "workflow").slice(0, 15);
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Orchestration" title="Workflows" />
      {workflows.isPending && <Loading />}
      {workflows.isError && <ErrorState error={workflows.error} />}
      <div className="grid gap-4 lg:grid-cols-2">
        {workflows.data?.map((w) => <WorkflowCard key={w.slug} workflow={w} />)}
      </div>
      <Panel title="Recent runs">
        {recent?.length === 0 && <p className="text-sm text-muted">No workflow has run yet.</p>}
        <ul className="divide-y divide-line/50">
          {recent?.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
              <Badge value={t.status} />
              <span className="flex-1">{t.objective}</span>
              <span className="text-xs text-muted">{t.output ?? t.error ?? ""}</span>
              <span className="text-xs text-muted">{formatDate(t.created_at)}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

function WorkflowCard({ workflow }: { workflow: WorkflowInfo }) {
  const canRun = useCan("operator");
  const run = useAction((params: Record<string, unknown>) => api.runWorkflow(workflow.slug, params), [["tasks"]]);
  const [city, setCity] = useState("");
  const [category, setCategory] = useState(CATEGORIES[0] ?? "gyms");
  const [url, setUrl] = useState("");
  const [focus, setFocus] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (workflow.slug === "website_opportunities") run.mutate({ city, category, limit: 10 });
    else if (workflow.slug === "audit_website") run.mutate({ url });
    else run.mutate({ focus });
  }

  return (
    <Panel>
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-semibold">{titleCase(workflow.slug)}</h2>
        {workflow.needs_ai_model && <Badge value={workflow.ready ? "ai model ready" : "needs ai key"} />}
      </div>
      <p className="mt-1 text-sm text-muted">{workflow.description}</p>
      {workflow.slug === "draft_outreach" ? (
        <p className="mt-3 text-xs text-muted">Start this from a lead on the Leads page.</p>
      ) : (
        canRun && (
          <form onSubmit={submit} className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            {workflow.slug === "website_opportunities" && (
              <>
                <Field label="City">
                  <input className="input" required value={city} onChange={(e) => setCity(e.target.value)} placeholder="Mysore" />
                </Field>
                <Field label="Category">
                  <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
                    {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </Field>
              </>
            )}
            {workflow.slug === "audit_website" && (
              <div className="sm:col-span-2">
                <Field label="Website">
                  <input className="input" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="example.com" />
                </Field>
              </div>
            )}
            {workflow.slug === "opportunity_research" && (
              <div className="sm:col-span-2">
                <Field label="Focus">
                  <input className="input" value={focus} onChange={(e) => setFocus(e.target.value)} placeholder="AI services for clinics in India" />
                </Field>
              </div>
            )}
            <button type="submit" className="btn" disabled={run.isPending || !workflow.ready}>Run</button>
          </form>
        )
      )}
      {run.isSuccess && <p className="mt-2 text-xs text-ok">Queued as task #{run.data.id}. Progress shows below.</p>}
      <ActionError error={run.error} />
    </Panel>
  );
}
