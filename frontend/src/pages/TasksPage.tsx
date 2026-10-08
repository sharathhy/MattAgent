import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { Task } from "../api/types";
import { ActionError, Badge, Empty, Field, PageHeader, useAction, useCan } from "../components/kit";
import { ErrorState, Loading, Panel } from "../components/ui";
import { formatDate } from "../lib/format";

const STATUSES = ["", "queued", "running", "waiting_approval", "succeeded", "failed", "cancelled"];

export function TasksPage() {
  const [status, setStatus] = useState("");
  const tasks = useQuery({ queryKey: ["tasks", status], queryFn: () => api.tasks({ status }), refetchInterval: 3000 });
  const canRun = useCan("operator");
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Orchestration" title="Tasks">
        <select className="input w-48" aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s ? s.replace(/_/g, " ") : "All statuses"}
            </option>
          ))}
        </select>
      </PageHeader>
      {canRun && <NewTask />}
      {tasks.isPending && <Loading />}
      {tasks.isError && <ErrorState error={tasks.error} />}
      {tasks.data?.length === 0 && <Empty>No tasks yet. Give MATT an objective above or from the Command Center.</Empty>}
      <div className="space-y-2">
        {tasks.data?.map((t) => <TaskRow key={t.id} task={t} canRun={canRun} />)}
      </div>
    </div>
  );
}

function NewTask() {
  const agents = useQuery({ queryKey: ["agents", {}], queryFn: () => api.agents() });
  const [objective, setObjective] = useState("");
  const [agent, setAgent] = useState("ceo");
  const create = useAction(api.createTask, [["tasks"]]);
  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate({ objective, agent_slug: agent }, { onSuccess: () => setObjective("") });
  }
  return (
    <Panel title="Assign work">
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-[1fr_16rem_auto] md:items-end">
        <Field label="Objective">
          <input className="input" required minLength={3} value={objective} onChange={(e) => setObjective(e.target.value)}
            placeholder="e.g. Draft a pricing page for website care plans" />
        </Field>
        <Field label="Agent">
          <select className="input" value={agent} onChange={(e) => setAgent(e.target.value)}>
            {(agents.data ?? [{ slug: "ceo", name: "MATT CEO" }]).map((a) => (
              <option key={a.slug} value={a.slug}>
                {a.name}
              </option>
            ))}
          </select>
        </Field>
        <button type="submit" className="btn" disabled={create.isPending}>Assign</button>
      </form>
      <ActionError error={create.error} />
    </Panel>
  );
}

function TaskRow({ task, canRun }: { task: Task; canRun: boolean }) {
  const [open, setOpen] = useState(false);
  const cancel = useAction(api.cancelTask, [["tasks"]]);
  const retry = useAction(api.retryTask, [["tasks"]]);
  return (
    <article className="panel p-4">
      <button type="button" className="flex w-full flex-wrap items-center gap-3 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="font-mono text-xs text-muted">#{task.id}</span>
        <Badge value={task.status} />
        <span className="min-w-0 flex-1 truncate">{task.objective}</span>
        <span className="font-mono text-xs text-muted">{task.agent_slug ?? task.kind}</span>
        <span className="text-xs text-muted">{formatDate(task.created_at)}</span>
      </button>
      {open && (
        <div className="mt-3 space-y-3 border-t border-line pt-3 text-sm">
          {task.output && <pre className="whitespace-pre-wrap font-sans text-slate-200">{task.output}</pre>}
          {task.error && <p className="text-danger">{task.error}</p>}
          <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-muted">
            <span>attempts {task.attempts}/{task.max_attempts}</span>
            {task.model && <span>model {task.model}</span>}
            {task.tokens > 0 && <span>{task.tokens} tokens</span>}
            <span>cost ₹{Number(task.cost_inr).toFixed(2)}</span>
            {task.parent_id && <span>delegated from #{task.parent_id}</span>}
            {task.agent_slug && <Link className="text-accent hover:underline" to={`/agents/${task.agent_slug}`}>agent profile</Link>}
          </div>
          {canRun && (
            <div className="flex gap-2">
              {(task.status === "queued" || task.status === "waiting_approval") && (
                <button type="button" className="btn bg-slate-700 text-slate-100" onClick={() => cancel.mutate(task.id)}>Cancel</button>
              )}
              {(task.status === "failed" || task.status === "cancelled") && (
                <button type="button" className="btn" onClick={() => retry.mutate(task.id)}>Retry</button>
              )}
            </div>
          )}
          <ActionError error={cancel.error ?? retry.error} />
        </div>
      )}
    </article>
  );
}
