import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { ActionError, Badge, Field, useAction } from "./kit";
import { ErrorState, Panel } from "./ui";

/** Owner-only: where customers pay. Stored encrypted, shown masked, every change audit-logged. */
export function ReceivingAccounts() {
  const list = useQuery({ queryKey: ["receiving-accounts"], queryFn: api.receivingAccounts });
  const [kind, setKind] = useState<"bank" | "upi">("bank");
  const [form, setForm] = useState({ label: "", holder_name: "", number: "", bank_name: "", ifsc: "" });
  const refresh = [["receiving-accounts"], ["payment-config"], ["payments"]];
  const add = useAction(
    () => api.addReceivingAccount({ kind, ...form, bank_name: form.bank_name || null, ifsc: form.ifsc || null }),
    refresh,
  );
  const primary = useAction((id: number) => api.makePrimaryAccount(id), refresh);
  const remove = useAction((id: number) => api.removeReceivingAccount(id), refresh);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <Panel title="Where you get paid">
      <p className="text-xs text-muted">
        Customers pay these directly; they are printed on payment requests. MATT only receives money: it never sends, withdraws
        or debits from these accounts. Details are encrypted, shown masked here, and every change is logged. Only you can see this.
      </p>
      {list.isError ? (
        <ErrorState error={list.error} />
      ) : (
        <ul className="mt-3 space-y-2 text-sm">
          {list.data?.length === 0 && <li className="text-muted">No accounts yet. Add your bank account or UPI ID below.</li>}
          {list.data?.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-line/60 p-3">
              <Badge value={a.kind} />
              <span>{a.label}</span>
              <span className="font-mono text-xs">{a.masked}</span>
              <span className="text-xs text-muted">{a.holder_name}{a.bank_name ? ` · ${a.bank_name}` : ""}{a.ifsc ? ` · ${a.ifsc}` : ""}</span>
              <span className="flex-1" />
              {a.is_primary ? (
                <Badge value="primary" />
              ) : (
                <button type="button" className="text-xs text-accent" onClick={() => primary.mutate(a.id)}>Make primary</button>
              )}
              <button type="button" className="text-xs text-muted" onClick={() => remove.mutate(a.id)}>Remove</button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="mt-4 grid gap-3 sm:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(undefined, { onSuccess: () => setForm({ label: "", holder_name: "", number: "", bank_name: "", ifsc: "" }) });
        }}
      >
        <Field label="Type">
          <select className="input w-full" value={kind} onChange={(e) => setKind(e.target.value as "bank" | "upi")}>
            <option value="bank">Bank account</option>
            <option value="upi">UPI ID</option>
          </select>
        </Field>
        <Field label="Label">
          <input className="input w-full" required value={form.label} onChange={set("label")} placeholder={kind === "bank" ? "Main account" : "PhonePe"} />
        </Field>
        <Field label="Account holder name">
          <input className="input w-full" required minLength={2} value={form.holder_name} onChange={set("holder_name")} />
        </Field>
        <Field label={kind === "bank" ? "Account number" : "UPI ID"}>
          <input className="input w-full font-mono" required autoComplete="off" value={form.number} onChange={set("number")} placeholder={kind === "bank" ? "" : "name@ybl"} />
        </Field>
        {kind === "bank" && (
          <>
            <Field label="Bank name">
              <input className="input w-full" required value={form.bank_name} onChange={set("bank_name")} />
            </Field>
            <Field label="IFSC">
              <input className="input w-full font-mono uppercase" required value={form.ifsc} onChange={set("ifsc")} placeholder="ABCD0123456" />
            </Field>
          </>
        )}
        <div className="sm:col-span-3">
          <button type="submit" className="btn" disabled={add.isPending}>Save account</button>
        </div>
      </form>
      <ActionError error={add.error ?? primary.error ?? remove.error} />
    </Panel>
  );
}
