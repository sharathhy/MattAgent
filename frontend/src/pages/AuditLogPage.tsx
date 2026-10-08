import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { ErrorState, Loading } from "../components/ui";
import { formatDate } from "../lib/format";

export function AuditLogPage() {
  const logs = useQuery({ queryKey: ["audit-logs"], queryFn: api.auditLogs });
  return (
    <div className="space-y-5">
      <header>
        <div className="label">Traceability</div>
        <h1 className="mt-1 text-2xl font-semibold">Audit Log</h1>
      </header>
      {logs.isPending && <Loading />}
      {logs.isError && <ErrorState error={logs.error} />}
      {logs.data && logs.data.length === 0 && <p className="text-muted">No entries yet.</p>}
      {logs.data && logs.data.length > 0 && (
        <div className="panel overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="label border-b border-line">
              <tr>
                <th className="p-3">Time</th>
                <th className="p-3">Actor</th>
                <th className="p-3">Action</th>
                <th className="p-3">Target</th>
                <th className="p-3">Details</th>
              </tr>
            </thead>
            <tbody>
              {logs.data.map((l) => (
                <tr key={l.id} className="border-b border-line/50 align-top">
                  <td className="whitespace-nowrap p-3 text-muted">{formatDate(l.created_at)}</td>
                  <td className="p-3 font-mono text-xs">{l.actor_type}:{l.actor_id}</td>
                  <td className="p-3 font-mono text-xs text-accent">{l.action}</td>
                  <td className="p-3 font-mono text-xs">{l.target_id ?? "—"}</td>
                  <td className="max-w-md p-3 font-mono text-xs text-muted">{JSON.stringify(l.details)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
