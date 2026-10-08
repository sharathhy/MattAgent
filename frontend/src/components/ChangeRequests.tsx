import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
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
        {c?.free_models_only === false ? " the AI model" : " the free AI model"}, and nothing changes until you approve it in{" "}
        <Link className="text-accent" to="/approvals">Approvals</Link>. Then it opens a pull request on {c?.repo ?? "GitHub"} for you
        to review and merge; MATT never merges or deploys by itself.
      </p>
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
                  {ch.model && <p className="text-xs text-muted">Drafted by {ch.model}.</p>}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
