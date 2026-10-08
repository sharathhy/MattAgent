import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { CodeAiStatus } from "../api/types";
import { DiffView } from "../pages/ApprovalsPage";
import { ActionError, Badge, Field, useAction } from "./kit";
import { formatDate } from "../lib/format";
import { ErrorState, Panel } from "./ui";

const STATUS: Record<string, string> = {
  drafting: "running",
  awaiting_approval: "pending",
  approved: "approved",
  pr_opened: "won",
  rejected: "rejected",
  failed: "failed",
};

/** Owner-only: ask MATT to change its own code. Drafted, approved by you, then opened as a PR. */
export function ChangeRequests() {
  const config = useQuery({ queryKey: ["change-config"], queryFn: api.changeConfig });
  const list = useQuery({ queryKey: ["changes"], queryFn: api.changes, refetchInterval: 5000 });
  const [text, setText] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const create = useAction(() => api.requestChange(text), [["changes"], ["tasks"]]);
  const c = config.data;
  return (
    <Panel title="Change MATT">
      <p className="text-xs text-muted">
        Describe a change to MATT itself (or say "Hey Matt, change your code to …"). MATT drafts a plan and the exact code with
        {c?.code_ai.provider === "claude" ? " Claude" : " the free AI model"}, and nothing changes until you approve it in{" "}
        <Link className="text-accent" to="/approvals">Approvals</Link>. Then it opens a pull request on {c?.repo ?? "GitHub"} for you
        to review and merge; MATT never merges or deploys by itself.
      </p>
      {c && <CodeAi status={c.code_ai} />}
      {c && !c.github_connected && (
        <p className="mt-2 text-sm text-amber-300">
          Add MATT_GITHUB_TOKEN in Render: a fine-grained GitHub token for {c.repo} only, with Contents and Pull requests
          set to read and write.
        </p>
      )}
      <form
        className="mt-3 space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate(undefined, { onSuccess: () => setText("") });
        }}
      >
        <Field label="What should change?">
          <textarea
            className="input min-h-20 w-full"
            required
            minLength={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Add a button on the Revenue page that exports the ledger as CSV"
          />
        </Field>
        <button type="submit" className="btn" disabled={create.isPending}>Draft the change</button>
      </form>
      <ActionError error={create.error ?? config.error} />
      {list.isError && <ErrorState error={list.error} />}
      {list.data && list.data.length > 0 && (
        <ul className="mt-4 space-y-2 text-sm">
          {list.data.map((ch) => (
            <li key={ch.id} className="rounded-lg border border-line/60 p-3">
              <div className="flex flex-wrap items-center gap-3">
                <Badge value={STATUS[ch.status] ?? ch.status} />
                <span className="min-w-0 flex-1">{ch.request}</span>
                <span className="text-xs text-muted">{formatDate(ch.created_at)}</span>
                {ch.pr_url && <a className="text-xs text-accent" href={ch.pr_url} target="_blank" rel="noreferrer">Open pull request</a>}
                {ch.status === "awaiting_approval" && <Link className="text-xs text-accent" to="/approvals">Review in Approvals</Link>}
                {(ch.plan ?? ch.diff) && (
                  <button type="button" className="text-xs text-accent" onClick={() => setOpen(open === ch.id ? null : ch.id)}>
                    {open === ch.id ? "Hide" : "Show plan and code"}
                  </button>
                )}
              </div>
              {ch.error && <p className="mt-2 text-xs text-rose-300">{ch.error}</p>}
              {open === ch.id && (
                <div className="mt-3 space-y-2">
                  {ch.plan && <pre className="whitespace-pre-wrap rounded-lg bg-slate-950/60 p-3 font-sans text-sm">{ch.plan}</pre>}
                  {ch.diff && <DiffView diff={ch.diff} />}
                  {ch.model && (
                    <p className="text-xs text-muted">
                      Drafted by {ch.model} · AI cost {ch.cost_inr > 0 ? inr(ch.cost_inr) : "free"}.
                    </p>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

const inr = (n: number) => `₹${n.toFixed(2)}`;

/** Which model drafts code changes, and Claude's spend against the owner's cap, kept apart from business AI. */
function CodeAi({ status }: { status: CodeAiStatus }) {
  if (status.provider === "free") {
    return (
      <p className="mt-2 text-xs text-muted">
        Code AI: free model. To draft code changes with Claude only, add MATT_ANTHROPIC_API_KEY and a monthly cap in
        MATT_CODE_AI_MONTHLY_BUDGET_INR in Render. Business work always stays on free models.
      </p>
    );
  }
  const used = status.monthly_cap_inr > 0 ? Math.min(100, (status.spent_30d_inr / status.monthly_cap_inr) * 100) : 0;
  return (
    <div className="mt-2 space-y-1 text-xs text-muted">
      <p>
        Code AI: Claude ({status.model}) · {inr(status.spent_30d_inr)} of your {inr(status.monthly_cap_inr)} cap used in
        the last 30 days. At the cap MATT drafts with the free model. {status.scope}
      </p>
      <div className="h-1.5 w-full max-w-sm rounded bg-slate-800">
        <div className="h-1.5 rounded bg-accent" style={{ width: `${used}%` }} />
      </div>
    </div>
  );
}
