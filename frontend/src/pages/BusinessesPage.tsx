import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { Business } from "../api/types";
import { ActionError, Badge, Empty, PageHeader, ScoreBar, Truth, useAction, useCan } from "../components/kit";
import { ErrorState, Loading } from "../components/ui";
import { formatDate, titleCase } from "../lib/format";

export function BusinessesPage() {
  const [q, setQ] = useState("");
  const businesses = useQuery({ queryKey: ["businesses", q], queryFn: () => api.businesses({ q }), refetchInterval: 5000 });
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Business intelligence" title="Businesses">
        <input className="input w-64" placeholder="Search by name" aria-label="Search businesses" value={q} onChange={(e) => setQ(e.target.value)} />
      </PageHeader>
      <p className="text-sm text-muted">
        Public business listings from OpenStreetMap (© OpenStreetMap contributors, ODbL). Website scores are automated
        estimates from the home page only.
      </p>
      {businesses.isPending && <Loading />}
      {businesses.isError && <ErrorState error={businesses.error} />}
      {businesses.data?.length === 0 && (
        <Empty>No businesses yet. Run “Website Opportunities” on the Workflows page, or tell MATT “find gyms in Mysore”.</Empty>
      )}
      <div className="space-y-2">
        {businesses.data?.map((b) => <BusinessRow key={b.id} business={b} />)}
      </div>
    </div>
  );
}

function BusinessRow({ business: b }: { business: Business }) {
  const [open, setOpen] = useState(false);
  const canRun = useCan("operator");
  const canDelete = useCan("admin");
  const audit = useAction(api.auditBusiness, [["tasks"]]);
  const remove = useAction(api.deleteBusiness, [["businesses"], ["leads"]]);
  return (
    <article className="panel p-4">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full flex-wrap items-center gap-4 text-left">
        <div className="min-w-0 flex-1">
          <div className="font-medium">{b.name}</div>
          <div className="text-xs text-muted">{[titleCase(b.category), b.location ?? b.city].filter(Boolean).join(" · ")}</div>
        </div>
        <div className="w-36"><div className="label">Website</div><ScoreBar value={b.website_score} /></div>
        <div className="w-36"><div className="label">Opportunity</div><ScoreBar value={b.opportunity_score} /></div>
        {b.lead_status && <Badge value={b.lead_status} />}
      </button>
      {open && (
        <div className="mt-3 grid gap-4 border-t border-line pt-3 text-sm md:grid-cols-2">
          <dl className="space-y-1">
            <Row label="Website" value={b.website ? <a className="text-accent hover:underline" href={b.website} target="_blank" rel="noreferrer noopener">{b.website}</a> : "None listed (verify before assuming)"} />
            <Row label="Phone" value={b.public_phone} />
            <Row label="Email" value={b.public_email} />
            <Row label="Tech" value={b.technology_stack.join(", ") || null} />
            <Row label="Source" value={b.source_url ? <a className="text-accent hover:underline" href={b.source_url} target="_blank" rel="noreferrer noopener">{b.source}</a> : b.source} />
            {b.audited_at && <Row label="Audited" value={formatDate(b.audited_at)} />}
          </dl>
          <div>
            {b.audit ? (
              <>
                <div className="mb-2 flex items-center gap-2"><span className="label">Audit</span><Truth value={b.audit.truth} /></div>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(b.audit.scores).map(([k, v]) => (
                    <div key={k}><div className="text-xs text-muted">{titleCase(k)}</div><ScoreBar value={v} /></div>
                  ))}
                </div>
                <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-300">
                  {b.audit.findings.map((f) => <li key={f}>{f}</li>)}
                </ul>
              </>
            ) : (
              <p className="text-muted">Not audited.</p>
            )}
            <div className="mt-3 flex gap-2">
              {canRun && b.website && <button type="button" className="btn" onClick={() => audit.mutate(b.id)} disabled={audit.isPending}>Re-audit</button>}
              {canDelete && (
                <button type="button" className="btn bg-slate-700 text-slate-100" onClick={() => remove.mutate(b.id)}>
                  Delete record
                </button>
              )}
            </div>
            {audit.isSuccess && <p className="mt-1 text-xs text-ok">Audit queued.</p>}
            <ActionError error={audit.error ?? remove.error} />
          </div>
        </div>
      )}
    </article>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="label w-16 shrink-0 pt-0.5">{label}</dt>
      <dd className="min-w-0 break-words">{value ?? <span className="text-muted">—</span>}</dd>
    </div>
  );
}
