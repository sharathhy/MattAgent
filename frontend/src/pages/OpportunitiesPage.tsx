import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "../api/client";
import type { Opportunity } from "../api/types";
import { ActionError, Badge, Empty, Field, PageHeader, ScoreBar, Truth, useAction, useCan } from "../components/kit";
import { ErrorState, Loading, Panel } from "../components/ui";
import { titleCase } from "../lib/format";

const POSITIVE = ["market_demand", "revenue_potential", "competition_advantage", "execution_feasibility", "recurring_revenue", "automation_potential"];
const NEGATIVE = ["cost", "risk", "time_to_revenue"];
const STATUSES = ["proposed", "validating", "approved", "rejected", "launched"];

export function OpportunitiesPage() {
  const opps = useQuery({ queryKey: ["opportunities"], queryFn: api.opportunities, refetchInterval: 5000 });
  const workflows = useQuery({ queryKey: ["workflows"], queryFn: api.workflows });
  const canRun = useCan("operator");
  const research = useAction(() => api.runWorkflow("opportunity_research", {}), [["tasks"]]);
  const aiReady = workflows.data?.find((w) => w.slug === "opportunity_research")?.ready ?? false;
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Opportunity engine" title="Opportunities">
        {canRun && (
          <button type="button" className="btn" disabled={!aiReady || research.isPending} onClick={() => research.mutate(undefined)}
            title={aiReady ? undefined : "Needs an AI model key"}>
            Research with AI
          </button>
        )}
      </PageHeader>
      <p className="text-sm text-muted">
        Score = demand + revenue + competition advantage + feasibility + recurring + automation − cost − risk − time to
        revenue, each rated 0–10 and scaled to 0–100. Ratings are estimates; AI-researched items are unverified until you
        validate them.
      </p>
      {research.isSuccess && <p className="text-xs text-ok">Research queued. New opportunities will appear below.</p>}
      <ActionError error={research.error} />
      {canRun && <NewOpportunity />}
      {opps.isPending && <Loading />}
      {opps.isError && <ErrorState error={opps.error} />}
      {opps.data?.length === 0 && <Empty>No opportunities yet. Add one above or run AI research.</Empty>}
      <div className="space-y-2">{opps.data?.map((o) => <OpportunityRow key={o.id} opp={o} canEdit={canRun} />)}</div>
    </div>
  );
}

function NewOpportunity() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [factors, setFactors] = useState<Record<string, number>>(
    Object.fromEntries([...POSITIVE, ...NEGATIVE].map((f) => [f, 5])),
  );
  const create = useAction(api.createOpportunity, [["opportunities"]]);
  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate({ title, description, category: "other", factors }, { onSuccess: () => { setTitle(""); setDescription(""); } });
  }
  return (
    <Panel title="Score an opportunity">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Title"><input className="input" required minLength={3} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
          <Field label="Description"><input className="input" value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        </div>
        <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
          {[...POSITIVE, ...NEGATIVE].map((f) => (
            <label key={f} className="flex items-center gap-3 text-xs">
              <span className={`w-40 ${NEGATIVE.includes(f) ? "text-rose-300" : "text-slate-300"}`}>{titleCase(f)}</span>
              <input type="range" min={0} max={10} value={factors[f]} aria-label={titleCase(f)}
                onChange={(e) => setFactors({ ...factors, [f]: Number(e.target.value) })} className="flex-1 accent-cyan-400" />
              <span className="w-5 font-mono">{factors[f]}</span>
            </label>
          ))}
        </div>
        <button type="submit" className="btn" disabled={create.isPending}>Add and score</button>
        <ActionError error={create.error} />
      </form>
    </Panel>
  );
}

function OpportunityRow({ opp, canEdit }: { opp: Opportunity; canEdit: boolean }) {
  const [open, setOpen] = useState(false);
  const update = useAction((status: string) => api.updateOpportunity(opp.id, { status }), [["opportunities"]]);
  return (
    <article className="panel p-4">
      <div className="flex flex-wrap items-center gap-4">
        <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
          <div className="font-medium">{opp.title}</div>
          <div className="text-xs text-muted">{titleCase(opp.category)} · {opp.source}</div>
        </button>
        <div className="w-36"><div className="label flex gap-2">Score <Truth value={opp.truth} /></div><ScoreBar value={opp.score} /></div>
        {canEdit ? (
          <select className="input w-36" aria-label={`Status of ${opp.title}`} value={opp.status} onChange={(e) => update.mutate(e.target.value)}>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        ) : (
          <Badge value={opp.status} />
        )}
      </div>
      {open && (
        <div className="mt-3 space-y-2 border-t border-line pt-3 text-sm">
          {opp.description && <p>{opp.description}</p>}
          {opp.evidence && <p className="text-xs text-muted">Evidence: {opp.evidence}</p>}
          <div className="grid gap-1 font-mono text-xs sm:grid-cols-3">
            {Object.entries(opp.factors).map(([k, v]) => (
              <span key={k} className={NEGATIVE.includes(k) ? "text-rose-300" : "text-slate-300"}>{titleCase(k)}: {v}</span>
            ))}
          </div>
        </div>
      )}
      <ActionError error={update.error} />
    </article>
  );
}
