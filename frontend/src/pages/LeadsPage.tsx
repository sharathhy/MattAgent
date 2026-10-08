import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { Lead, LeadStatus } from "../api/types";
import { ActionError, Badge, Empty, PageHeader, ScoreBar, inr, useAction, useCan } from "../components/kit";
import { ErrorState, Loading } from "../components/ui";

const STATUSES: LeadStatus[] = ["new", "qualified", "contacted", "meeting", "won", "lost"];

export function LeadsPage() {
  const leads = useQuery({ queryKey: ["leads"], queryFn: () => api.leads(), refetchInterval: 5000 });
  const counts = Object.fromEntries(STATUSES.map((s) => [s, leads.data?.filter((l) => l.status === s).length ?? 0]));
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Pipeline" title="Leads" />
      <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
        {STATUSES.map((s) => (
          <div key={s} className="panel p-3 text-center">
            <div className="label">{s}</div>
            <div className="mt-1 font-mono text-xl">{counts[s]}</div>
          </div>
        ))}
      </div>
      {leads.isPending && <Loading />}
      {leads.isError && <ErrorState error={leads.error} />}
      {leads.data?.length === 0 && <Empty>No leads yet. Leads are created when a discovered business needs a website or a better one.</Empty>}
      <div className="space-y-2">{leads.data?.map((l) => <LeadRow key={l.id} lead={l} />)}</div>
      <p className="text-xs text-muted">
        Value ranges are assumptions based on typical small-business website pricing, not quotes. Outreach is drafted for
        your approval and must follow anti-spam rules: one honest message, a clear opt-out, no follow-up after “stop”.
      </p>
    </div>
  );
}

function LeadRow({ lead }: { lead: Lead }) {
  const [open, setOpen] = useState(false);
  const canEdit = useCan("operator");
  const update = useAction((status: LeadStatus) => api.updateLead(lead.id, { status }), [["leads"], ["dashboard"]]);
  const draft = useAction(() => api.draftOutreach(lead.id), [["tasks"]]);
  const b = lead.business;
  return (
    <article className="panel p-4">
      <div className="flex flex-wrap items-center gap-4">
        <button type="button" className="min-w-0 flex-1 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
          <div className="font-medium">{b.name}</div>
          <div className="text-xs text-muted">{lead.service} · {b.city} · {inr(lead.estimated_value_min_inr)}–{inr(lead.estimated_value_max_inr)} (assumption)</div>
        </button>
        <div className="w-32"><div className="label">Opportunity</div><ScoreBar value={b.opportunity_score} /></div>
        {b.outreach_status && <Badge value={b.outreach_status} />}
        {canEdit ? (
          <select className="input w-36" aria-label={`Status of ${b.name}`} value={lead.status} onChange={(e) => update.mutate(e.target.value as LeadStatus)}>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        ) : (
          <Badge value={lead.status} />
        )}
      </div>
      {open && (
        <div className="mt-3 space-y-3 border-t border-line pt-3 text-sm">
          {lead.next_action && <p><span className="label">Next</span> {lead.next_action}</p>}
          <p className="text-xs text-muted">
            {b.public_email ?? "No public email"} · {b.public_phone ?? "No public phone"} · {b.website ?? "No website listed"}
          </p>
          {lead.outreach_draft && (
            <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950/60 p-4 font-sans">{lead.outreach_draft}</pre>
          )}
          {canEdit && (
            <button type="button" className="btn" onClick={() => draft.mutate(undefined)} disabled={draft.isPending}>
              {lead.outreach_draft ? "Redraft outreach" : "Draft outreach"}
            </button>
          )}
          {draft.isSuccess && <p className="text-xs text-ok">Drafting. It will appear in Approvals for your review.</p>}
          <ActionError error={draft.error ?? update.error} />
        </div>
      )}
    </article>
  );
}
