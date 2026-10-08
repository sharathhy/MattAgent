import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { Badge, PageHeader, Table } from "../components/kit";
import { ErrorState, Loading } from "../components/ui";

export function ToolsPage() {
  const tools = useQuery({ queryKey: ["tools"], queryFn: api.tools });
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Capabilities" title="Tools" />
      <p className="text-sm text-muted">
        Connected tools do real work today. Tools marked not connected are listed so you can see what agents will need;
        nothing can call them until they are built and configured.
      </p>
      {tools.isPending && <Loading />}
      {tools.isError && <ErrorState error={tools.error} />}
      {tools.data && (
        <Table head={["Tool", "Status", "Provider", "Permission", "Risk", "Cost"]}>
          {tools.data.map((t) => (
            <tr key={t.slug} className="border-b border-line/50 align-top">
              <td className="p-3">
                <div className="font-medium">{t.name}</div>
                <div className="text-xs text-muted">{t.description}</div>
              </td>
              <td className="p-3">
                <Badge value={t.available ? "active" : "not connected"} />
              </td>
              <td className="p-3 font-mono text-xs">{t.provider}</td>
              <td className="p-3 font-mono text-xs">{t.permission}</td>
              <td className="p-3"><Badge value={t.risk_level} /></td>
              <td className="p-3 font-mono text-xs">{t.cost_tier}</td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
