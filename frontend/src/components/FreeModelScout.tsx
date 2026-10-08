import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { ActionError, Badge, Table, useAction, useCan } from "./kit";
import { formatDate } from "../lib/format";
import { ErrorState, Loading, Panel } from "./ui";

const STATUS: Record<string, string> = {
  ok: "active",
  not_connected: "not connected",
  error: "failed",
  no_free_model: "rejected",
  not_checked: "queued",
};

/** The Free Model Scout: which free-tier AI services MATT uses, their health, and what to connect. */
export function FreeModelScout() {
  const sources = useQuery({ queryKey: ["free-sources"], queryFn: api.freeSources, refetchInterval: 30000 });
  const canScan = useCan("admin");
  const scan = useAction(() => api.runScout(), [["free-sources"], ["settings"], ["approvals"]]);
  return (
    <Panel title="Free Model Scout">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <p className="min-w-0 flex-1 text-xs text-muted">
          Every 6 hours the Cost Optimization skill checks each free AI service, switches to its best free model and spreads
          work across them when one hits its daily limit. MATT can't create accounts or keys, so it marks the most useful
          missing one as suggested. Paid models are never used. Limits are the providers' own estimates.
        </p>
        {canScan && (
          <button type="button" className="btn bg-slate-700 text-slate-100" onClick={() => scan.mutate(undefined)} disabled={scan.isPending}>
            {scan.isPending ? "Scanning…" : "Scan now"}
          </button>
        )}
      </div>
      <ActionError error={scan.error} />
      {sources.isPending ? (
        <Loading />
      ) : sources.isError ? (
        <ErrorState error={sources.error} />
      ) : (
        <Table head={["Service", "Status", "Model in use", "Calls 24h", "Free limits", "Key"]}>
          {sources.data.map((s) => (
            <tr key={s.slug} className="border-b border-line/50 align-top">
              <td className="p-3">
                {s.name}
                {s.suggested && <span className="ml-2"><Badge value="suggested" /></span>}
                {s.note && <p className="mt-1 text-xs text-muted">{s.note}</p>}
              </td>
              <td className="p-3">
                <Badge value={STATUS[s.status] ?? s.status} />
                {s.error && <p className="mt-1 max-w-xs truncate text-xs text-rose-300" title={s.error}>{s.error}</p>}
                {s.checked_at && <p className="mt-1 text-xs text-muted">{formatDate(s.checked_at)}</p>}
              </td>
              <td className="p-3 font-mono text-xs">
                {s.model ?? "—"}
                {s.free_models > 0 && <span className="text-muted"> ({s.free_models} free)</span>}
              </td>
              <td className="p-3 font-mono text-xs">
                {s.calls_24h}
                {s.failures_24h > 0 && <span className="text-rose-300"> ({s.failures_24h} failed)</span>}
              </td>
              <td className="p-3 text-xs text-muted">{s.free_limits}</td>
              <td className="p-3 text-xs">
                <span className="font-mono">{s.env_var}</span>
                {!s.connected && (
                  <a className="mt-1 block text-accent" href={s.signup_url} target="_blank" rel="noreferrer">
                    Get a free key
                  </a>
                )}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Panel>
  );
}
