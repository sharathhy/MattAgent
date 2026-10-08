import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { SalesOffer, SalesService } from "../api/types";
import { ActionError, Badge, Empty, PageHeader, useAction, useCan } from "../components/kit";
import { ErrorState, Loading } from "../components/ui";

/** The one path from a found business to a real payment: MATT prepares, you send, the customer pays you. */
export function SalesDeskPage() {
  const desk = useQuery({ queryKey: ["sales"], queryFn: api.salesDesk, refetchInterval: 15000 });
  const services = useQuery({ queryKey: ["sales-services"], queryFn: api.salesServices });
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Earn" title="Sales Desk" />
      <ol className="list-decimal space-y-1 pl-5 text-sm text-muted">
        <li>
          MATT finds local businesses, builds each one a free sample of a service (a demo website, a month of social posts,
          a Google profile makeover, local SEO and more) and writes a personal offer with its link.
        </li>
        <li>You set a price. MATT adds your UPI payment details to the offer.</li>
        <li>You press WhatsApp or Email. It opens on your own phone or email with the message ready; MATT sends nothing itself.</li>
        <li>When the customer pays you, press Paid. It is recorded as revenue. Then you deliver the work.</li>
      </ol>
      {desk.isPending && <Loading />}
      {desk.isError && <ErrorState error={desk.error} />}
      {desk.data && !desk.data.upi_ready && (
        <p className="text-sm text-amber-300">
          Add your UPI ID in <Link className="text-accent" to="/settings">Settings, Where you get paid</Link> so offers can include it.
        </p>
      )}
      {desk.data && desk.data.offers.length === 0 && (
        <Empty>
          No offers yet. Say "find gyms in Mysuru" (or any business type and city), or let Autopilot find leads.
          {desk.data.without_contact > 0 && ` ${desk.data.without_contact} found businesses have no public phone or email.`}
        </Empty>
      )}
      {desk.data?.offers.map((o) => <Offer key={o.lead_id} offer={o} services={services.data ?? []} />)}
    </div>
  );
}

function Offer({ offer, services }: { offer: SalesOffer; services: SalesService[] }) {
  const [service, setService] = useState(services.find((s) => s.name === offer.service)?.slug ?? "website");
  const isOwner = useCan("owner");
  const [price, setPrice] = useState(offer.price_inr);
  const [copied, setCopied] = useState(false);
  const keys = [["sales"], ["revenue"], ["dashboard"]];
  const setPriceAction = useAction(() => api.priceOffer(offer.lead_id, price), keys);
  const sent = useAction(() => api.offerSent(offer.lead_id), keys);
  const demo = useAction(() => api.buildDemo(offer.lead_id, service), keys);
  const paid = useAction(() => api.offerPaid(offer.lead_id), keys);
  const pay = offer.payment;
  return (
    <article className="panel space-y-3 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="flex-1 font-semibold">
          {offer.business} <span className="text-sm font-normal text-muted">· {offer.category}{offer.city ? `, ${offer.city}` : ""}</span>
        </h2>
        <Badge value={offer.status} />
        {offer.website_score !== null && <span className="text-xs text-muted">website score {offer.website_score}/100 (estimate)</span>}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {offer.samples.map((x) => (
          <a key={x.service} className="text-accent underline" href={x.url} target="_blank" rel="noreferrer">
            Open free sample: {x.name}
          </a>
        ))}
        {offer.samples.length === 0 && <span className="text-muted">No free sample yet.</span>}
        {services.length > 0 && (
          <select className="input w-auto py-1 text-xs" aria-label="Service" value={service} onChange={(e) => setService(e.target.value)}>
            {services.map((x) => (
              <option key={x.slug} value={x.slug}>
                {x.name} (from ₹{x.price_inr})
              </option>
            ))}
          </select>
        )}
        <button type="button" className="btn bg-slate-700 px-2.5 py-1 text-xs text-slate-100" disabled={demo.isPending} onClick={() => demo.mutate(undefined)}>
          {demo.isPending ? "Building…" : "Build free sample"}
        </button>
      </div>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-950/60 p-3 font-sans text-sm">{offer.message}</pre>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-sm">
          Price ₹
          <input className="input w-28" type="number" min={1} value={price} onChange={(e) => setPrice(Number(e.target.value))} />
        </label>
        <button type="button" className="btn bg-slate-700 text-slate-100" disabled={setPriceAction.isPending || price < 1} onClick={() => setPriceAction.mutate(undefined)}>
          {pay ? "Update price" : "Add UPI payment"}
        </button>
        {offer.whatsapp_url && (
          <a className="btn" href={offer.whatsapp_url} target="_blank" rel="noreferrer">WhatsApp {offer.public_phone}</a>
        )}
        {offer.email_url && <a className="btn" href={offer.email_url}>Email {offer.public_email}</a>}
        <button
          type="button"
          className="btn bg-slate-700 text-slate-100"
          onClick={() => {
            void navigator.clipboard?.writeText(offer.message).then(() => setCopied(true));
          }}
        >
          {copied ? "Copied" : "Copy message"}
        </button>
        {offer.status !== "contacted" && (
          <button type="button" className="btn bg-slate-700 text-slate-100" disabled={sent.isPending} onClick={() => sent.mutate(undefined)}>
            I sent it
          </button>
        )}
        {isOwner && pay && pay.status !== "received" && (
          <button type="button" className="btn bg-emerald-600 text-white" disabled={paid.isPending} onClick={() => paid.mutate(undefined)}>
            Paid ₹{pay.amount_inr}
          </button>
        )}
      </div>
      {pay && <p className="text-xs text-muted">Payment request {pay.reference}: ₹{pay.amount_inr} to {pay.upi_id ?? "your bank account"} · {pay.status}</p>}
      <p className="text-xs text-muted">Send one message per business, and stop if they reply STOP.</p>
      <ActionError error={setPriceAction.error ?? sent.error ?? paid.error ?? demo.error} />
    </article>
  );
}
