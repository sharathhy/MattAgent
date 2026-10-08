import { useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import { AutopilotPanel } from "../components/AutopilotPanel";
import { Badge, PageHeader, Table, inr, useCan } from "../components/kit";
import { ErrorState, Loading, Panel } from "../components/ui";

export function SettingsPage() {
  const isAdmin = useCan("admin");
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, enabled: isAdmin });
  if (!isAdmin) return <p className="text-muted">Settings are visible to admins and the owner.</p>;
  if (settings.isPending) return <Loading />;
  if (settings.isError) return <ErrorState error={settings.error} />;
  const s = settings.data;
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="System" title="Settings" />
      <AutopilotPanel full />
      <p className="text-sm text-muted">
        Secrets live only in the hosting environment (Render → Environment), never in the app or the repository. This page
        shows whether each one is set, not its value.
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Access">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt>Owner email</dt><dd className="font-mono text-xs">{s.owner_email ?? "not set"}</dd></div>
            <div className="flex justify-between"><dt>Google sign-in</dt><dd><Badge value={s.google_sign_in ? "active" : "not connected"} /></dd></div>
            <div className="flex justify-between"><dt>Environment</dt><dd className="font-mono text-xs">{s.environment}</dd></div>
            <div className="flex justify-between"><dt>Background worker</dt><dd><Badge value={s.worker_enabled ? "active" : "cancelled"} /></dd></div>
            <div className="flex justify-between"><dt>Email sending</dt><dd><Badge value={s.email_sending ? "active" : "not connected"} /></dd></div>
          </dl>
        </Panel>
        <Panel title="AI budget">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between"><dt>Daily limit (paid models)</dt><dd className="font-mono">{inr(s.daily_ai_budget_inr)}</dd></div>
            <div className="flex justify-between"><dt>Monthly limit (paid models)</dt><dd className="font-mono">{inr(s.monthly_ai_budget_inr)}</dd></div>
            <div className="flex justify-between"><dt>Premium models</dt><dd><Badge value={s.allow_premium_models ? "approved" : "rejected"} /></dd></div>
          </dl>
          <p className="mt-3 text-xs text-muted">
            Free and local models are always allowed. At the limit MATT stops and asks you in Approvals. Change limits with
            MATT_DAILY_AI_BUDGET_INR and MATT_MONTHLY_AI_BUDGET_INR.
          </p>
        </Panel>
      </div>
      <Panel title="Model keys">
        <ul className="grid gap-2 text-sm sm:grid-cols-2">
          {Object.entries(s.model_keys).map(([k, set]) => (
            <li key={k} className="flex items-center justify-between gap-2">
              <span className="font-mono text-xs">{k}</span>
              <Badge value={set ? "active" : "not connected"} />
            </li>
          ))}
        </ul>
      </Panel>
      <h2 className="label">Model routing order (cheapest first)</h2>
      {s.models.length === 0 ? (
        <p className="text-sm text-muted">No model is configured. Add MATT_GEMINI_API_KEY (free tier) to give MATT its reasoning.</p>
      ) : (
        <Table head={["Model", "Tier", "Quality", "Paid", "Limits", "Enabled"]}>
          {s.models.map((m) => (
            <tr key={m.model} className="border-b border-line/50">
              <td className="p-3 font-mono text-xs">{m.provider}/{m.model}</td>
              <td className="p-3">{m.tier}</td>
              <td className="p-3">{m.quality}/5</td>
              <td className="p-3">{m.paid ? "yes" : "free"}</td>
              <td className="p-3 text-xs text-muted">{m.rate_limit}</td>
              <td className="p-3"><Badge value={m.enabled ? "active" : "needs opt-in"} /></td>
            </tr>
          ))}
        </Table>
      )}
    </div>
  );
}
