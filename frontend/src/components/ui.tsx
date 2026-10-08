import type { ReactNode } from "react";

import type { AgentStatus } from "../api/types";

export function Panel({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`panel p-5 ${className}`}>
      {title && <h2 className="label mb-4">{title}</h2>}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="panel relative overflow-hidden p-4">
      <div className="label">{label}</div>
      <div className="mt-2 font-mono text-2xl font-semibold text-slate-100">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

const STATUS_STYLE: Record<AgentStatus, string> = {
  discovered: "text-slate-300 border-slate-500/40",
  designed: "text-sky-300 border-sky-400/40",
  built: "text-indigo-300 border-indigo-400/40",
  testing: "text-amber-300 border-amber-400/40",
  evaluated: "text-violet-300 border-violet-400/40",
  deployed: "text-emerald-300 border-emerald-400/40",
  upgrading: "text-cyan-300 border-cyan-400/40",
  retired: "text-slate-500 border-slate-600/40",
};

export function StatusBadge({ status }: { status: AgentStatus }) {
  return (
    <span className={`rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${STATUS_STYLE[status]}`}>
      {status}
    </span>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="label animate-pulse p-6">
      {label}…
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong";
  return (
    <div role="alert" className="panel border-danger/40 p-4 text-sm text-danger">
      {message}
    </div>
  );
}
