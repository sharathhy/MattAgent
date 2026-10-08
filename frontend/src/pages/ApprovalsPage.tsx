import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { Approval } from "../api/types";
import { ActionError, Badge, Empty, PageHeader, useAction, useCan } from "../components/kit";
import { ErrorState, Loading, Panel } from "../components/ui";
import { formatDate } from "../lib/format";

export function ApprovalsPage() {
  const approvals = useQuery({ queryKey: ["approvals"], queryFn: () => api.approvals(), refetchInterval: 5000 });
  const pending = approvals.data?.filter((a) => a.status === "pending") ?? [];
  const decided = approvals.data?.filter((a) => a.status !== "pending") ?? [];
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Human in the loop" title="Approvals" />
      <p className="text-sm text-muted">
        MATT never sends, spends or publishes on its own. Anything external, financial or over budget waits here. High-risk
        items need the owner.
      </p>
      {approvals.isPending && <Loading />}
      {approvals.isError && <ErrorState error={approvals.error} />}
      {approvals.data && pending.length === 0 && <Empty>Nothing is waiting for you.</Empty>}
      {pending.map((a) => <PendingApproval key={a.id} approval={a} />)}
      {decided.length > 0 && (
        <Panel title="History">
          <ul className="divide-y divide-line/50 text-sm">
            {decided.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-3 py-2">
                <Badge value={a.status} />
                <span className="flex-1">{a.action}</span>
                {a.note && <span className="text-xs text-muted">“{a.note}”</span>}
                <span className="text-xs text-muted">{a.decided_at && formatDate(a.decided_at)}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function PendingApproval({ approval }: { approval: Approval }) {
  const canDecide = useCan(approval.risk_level === "high" ? "owner" : "admin");
  const [note, setNote] = useState("");
  const decide = useAction(
    (approve: boolean) => api.decideApproval(approval.id, approve, note || undefined),
    [["approvals"], ["leads"], ["tasks"], ["dashboard"]],
  );
  const draft = typeof approval.details.draft === "string" ? approval.details.draft : null;
  const to = typeof approval.details.to === "string" ? approval.details.to : null;
  return (
    <article className="panel space-y-3 border-amber-400/30 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <Badge value={approval.risk_level} />
        <span className="label">{approval.kind}</span>
        <h2 className="flex-1 font-semibold">{approval.action}</h2>
        <span className="text-xs text-muted">requested by {approval.agent_slug} · {formatDate(approval.created_at)}</span>
      </div>
      {approval.kind === "outreach" && (
        <p className="text-xs text-muted">
          {to ? `Public contact on record: ${to}. ` : "No public email on record. "}
          Approving marks the draft ready; MATT has no email provider connected, so you send it yourself.
        </p>
      )}
      {typeof approval.details.reason === "string" && <p className="text-sm text-warn">{approval.details.reason}</p>}
      {draft && <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950/60 p-4 font-sans text-sm">{draft}</pre>}
      {canDecide ? (
        <div className="flex flex-wrap items-center gap-2">
          <input className="input max-w-sm" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          <button type="button" className="btn" disabled={decide.isPending} onClick={() => decide.mutate(true)}>Approve</button>
          <button type="button" className="btn bg-rose-500/80 text-white hover:bg-rose-500" disabled={decide.isPending} onClick={() => decide.mutate(false)}>
            Reject
          </button>
        </div>
      ) : (
        <p className="text-xs text-muted">Only the {approval.risk_level === "high" ? "owner" : "owner or an admin"} can decide this.</p>
      )}
      <ActionError error={decide.error} />
    </article>
  );
}
