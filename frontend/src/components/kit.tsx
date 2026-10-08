import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useAuth } from "../lib/auth";

const ROLE_RANK = { viewer: 0, operator: 1, admin: 2, owner: 3 } as const;

/** True when the signed-in user has at least this role. The API enforces the same rule. */
export function useCan(minimum: keyof typeof ROLE_RANK) {
  const { user } = useAuth();
  return user ? ROLE_RANK[user.role] >= ROLE_RANK[minimum] : false;
}

export function PageHeader({ eyebrow, title, children }: { eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <div className="label">{eyebrow}</div>
        <h1 className="mt-1 text-2xl font-semibold">{title}</h1>
      </div>
      {children}
    </header>
  );
}

const TONE: Record<string, string> = {
  queued: "text-sky-300 border-sky-400/40",
  running: "text-cyan-300 border-cyan-400/50 animate-pulse",
  waiting_approval: "text-amber-300 border-amber-400/40",
  pending: "text-amber-300 border-amber-400/40",
  succeeded: "text-emerald-300 border-emerald-400/40",
  approved: "text-emerald-300 border-emerald-400/40",
  won: "text-emerald-300 border-emerald-400/40",
  live: "text-emerald-300 border-emerald-400/40",
  active: "text-emerald-300 border-emerald-400/40",
  failed: "text-rose-300 border-rose-400/40",
  rejected: "text-rose-300 border-rose-400/40",
  lost: "text-rose-300 border-rose-400/40",
  high: "text-rose-300 border-rose-400/40",
  medium: "text-amber-300 border-amber-400/40",
  cancelled: "text-slate-400 border-slate-500/40",
};

export function Badge({ value }: { value: string }) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
        TONE[value] ?? "border-line text-slate-300"
      }`}
    >
      {value.replace(/_/g, " ")}
    </span>
  );
}

/** Business-truth label: every number says whether it is a fact, estimate, assumption... */
export function Truth({ value }: { value: string }) {
  const tone = value === "fact" ? "text-emerald-300" : "text-amber-300";
  return <span className={`font-mono text-[10px] uppercase tracking-wider ${tone}`}>{value}</span>;
}

export const inr = (v: number | string | null | undefined) =>
  v === null || v === undefined || v === ""
    ? "—"
    : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

export function Empty({ children }: { children: ReactNode }) {
  return <div className="panel p-6 text-center text-sm text-muted">{children}</div>;
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="label border-b border-line">
          <tr>
            {head.map((h) => (
              <th key={h} className="p-3 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1 text-sm">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

export function ScoreBar({ value, max = 100 }: { value: number | null; max?: number }) {
  if (value === null) return <span className="text-muted">—</span>;
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const tone = pct >= 70 ? "bg-emerald-400" : pct >= 45 ? "bg-amber-400" : "bg-rose-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-slate-800">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs">{Math.round(value)}</span>
    </div>
  );
}

/** A mutation that refreshes the given queries when it succeeds. */
export function useAction<A, R>(fn: (arg: A) => Promise<R>, invalidate: QueryKey[]) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => Promise.all(invalidate.map((key) => qc.invalidateQueries({ queryKey: key }))),
  });
}

export function ActionError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-xs text-danger">
      {error instanceof Error ? error.message : "Something went wrong"}
    </p>
  );
}
