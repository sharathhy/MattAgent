import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { ActionError, Badge, Field, inr, useAction, useCan } from "./kit";
import { formatDate } from "../lib/format";
import { ErrorState, Panel } from "./ui";

const STATUS: Record<string, string> = { requested: "pending", received: "won", cancelled: "cancelled" };

/** Receive-only UPI payment requests: customers pay the owner's own UPI ID directly. */
export function PaymentRequests({ categories }: { categories: string[] }) {
  const config = useQuery({ queryKey: ["payment-config"], queryFn: api.paymentConfig });
  const list = useQuery({ queryKey: ["payments"], queryFn: api.paymentRequests });
  const canRequest = useCan("operator");
  const isOwner = useCan("owner");
  const [amount, setAmount] = useState("");
  const [purpose, setPurpose] = useState("");
  const [category, setCategory] = useState("websites");
  const [open, setOpen] = useState<number | null>(null);
  const refresh = [["payments"], ["ledger"], ["dashboard"]];
  const create = useAction(() => api.requestPayment({ amount_inr: Number(amount), purpose, category }), refresh);
  const received = useAction((id: number) => api.paymentReceived(id), refresh);
  const cancel = useAction((id: number) => api.cancelPayment(id), refresh);
  if (config.isError) return <ErrorState error={config.error} />;
  const c = config.data;
  return (
    <Panel title="Get paid by UPI">
      <p className="text-xs text-muted">
        {c?.rule ?? "MATT only receives money."} Customers pay {c?.upi_id ? <span className="font-mono text-slate-200">{c.upi_id}</span> : "you"} directly by scanning the
        QR in PhonePe, GPay or any UPI app{c?.bank ? `, or by bank transfer to ${c.bank.bank_name} ${c.bank.number}` : ""}. {c?.verification}
      </p>
      {c && !c.configured && (
        <p className="mt-2 text-sm text-amber-300">
          {c.problem ?? "Add where you get paid (bank account or UPI ID) in Settings to start requesting payments."}
        </p>
      )}
      {c?.configured && canRequest && (
        <form
          className="mt-3 grid gap-3 sm:grid-cols-[8rem_1fr_10rem_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(undefined, { onSuccess: (r) => { setAmount(""); setPurpose(""); setOpen(r.id); } });
          }}
        >
          <Field label="Amount (₹)">
            <input className="input w-full" type="number" min="1" step="1" required value={amount} onChange={(e) => setAmount(e.target.value)} />
          </Field>
          <Field label="For">
            <input className="input w-full" required minLength={2} value={purpose} onChange={(e) => setPurpose(e.target.value)} placeholder="Website for Mysore Dental" />
          </Field>
          <Field label="Stream">
            <select className="input w-full" value={category} onChange={(e) => setCategory(e.target.value)}>
              {categories.map((x) => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}
            </select>
          </Field>
          <button type="submit" className="btn" disabled={create.isPending}>Create payment request</button>
        </form>
      )}
      <ActionError error={create.error ?? received.error ?? cancel.error} />
      {list.data && list.data.length > 0 && (
        <ul className="mt-4 space-y-2 text-sm">
          {list.data.map((p) => (
            <li key={p.id} className="rounded-lg border border-line/60 p-3">
              <div className="flex flex-wrap items-center gap-3">
                <Badge value={STATUS[p.status] ?? p.status} />
                <span className="font-mono">{inr(p.amount_inr)}</span>
                <span className="min-w-0 flex-1 truncate">{p.purpose}</span>
                <span className="font-mono text-xs text-muted">{p.reference}</span>
                <button type="button" className="text-xs text-accent" onClick={() => setOpen(open === p.id ? null : p.id)}>
                  {open === p.id ? "Hide QR" : "Show QR"}
                </button>
                {p.status === "requested" && isOwner && (
                  <button type="button" className="btn bg-emerald-700 text-white" onClick={() => received.mutate(p.id)} disabled={received.isPending}>
                    Money received
                  </button>
                )}
                {p.status === "requested" && canRequest && (
                  <button type="button" className="text-xs text-muted" onClick={() => cancel.mutate(p.id)} disabled={cancel.isPending}>Cancel</button>
                )}
              </div>
              {open === p.id && (
                <div className="mt-3 flex flex-wrap items-start gap-4">
                  {p.qr_svg && p.upi_link && (
                    <img
                      alt={`UPI QR code for ${p.reference}`}
                      className="h-40 w-40 rounded bg-white p-1"
                      src={`data:image/svg+xml;utf8,${encodeURIComponent(p.qr_svg)}`}
                    />
                  )}
                  <div className="space-y-2 text-xs text-muted">
                    {p.upi_link && (
                      <>
                        <p>UPI: <span className="font-mono text-slate-200">{p.upi_id}</span></p>
                        <a className="text-accent" href={p.upi_link}>Open in a UPI app</a>
                        <button type="button" className="ml-3 text-accent" onClick={() => void navigator.clipboard?.writeText(p.upi_link ?? "")}>Copy link</button>
                      </>
                    )}
                    {p.bank && (
                      <p>
                        Bank transfer: {p.bank.holder_name}, {p.bank.bank_name}, A/c <span className="font-mono text-slate-200">{p.bank.number}</span>,
                        IFSC <span className="font-mono text-slate-200">{p.bank.ifsc}</span>. Reference {p.reference}.
                      </p>
                    )}
                    <p>Created {formatDate(p.created_at)}.</p>
                    {p.received_at && <p>Received {formatDate(p.received_at)} and recorded as revenue.</p>}
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
