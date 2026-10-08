import type { Customer, Experiment, Knowledge, LedgerEntry, Product } from "../api/types";
import { Badge, Truth, inr } from "../components/kit";
import { RecordsPage } from "../components/RecordsPage";
import { Stat } from "../components/ui";
import { formatDate, titleCase } from "../lib/format";

const REVENUE_CATEGORIES = [
  "websites", "saas", "automation", "ai_consulting", "content", "digital_products", "affiliate",
  "subscriptions", "lead_generation", "other",
];

const today = () => new Date().toISOString().slice(0, 10);

export function CustomersPage() {
  return (
    <RecordsPage<Customer>
      collection="customers" eyebrow="Revenue engines" title="Customers"
      empty="No customers yet. Add real customers here when you win them."
      fields={[
        { name: "name", label: "Name", required: true },
        { name: "company", label: "Company" },
        { name: "email", label: "Email" },
        { name: "status", label: "Status", type: "select", options: ["active", "prospect", "churned"] },
        { name: "notes", label: "Notes", type: "textarea" },
      ]}
      columns={[
        { label: "Name", render: (c) => <div><div>{c.name}</div><div className="text-xs text-muted">{c.company}</div></div> },
        { label: "Email", render: (c) => c.email ?? "—" },
        { label: "Status", render: (c) => <Badge value={c.status} /> },
        { label: "Since", render: (c) => formatDate(c.created_at) },
      ]}
    />
  );
}

export function ProductsPage() {
  return (
    <RecordsPage<Product>
      collection="products" eyebrow="AI SaaS factory" title="Products"
      empty="No products yet. Track the services and SaaS products you build here."
      fields={[
        { name: "name", label: "Name", required: true },
        { name: "kind", label: "Type", type: "select", options: ["service", "saas", "digital_product", "subscription", "other"] },
        { name: "status", label: "Stage", type: "select", options: ["idea", "building", "live", "retired"] },
        { name: "price_inr", label: "Price (₹)", type: "number" },
        { name: "billing", label: "Billing", type: "select", options: ["one_time", "monthly", "yearly"] },
        { name: "url", label: "URL" },
        { name: "description", label: "Description", type: "textarea" },
      ]}
      columns={[
        { label: "Product", render: (p) => <div><div>{p.name}</div><div className="text-xs text-muted">{p.description}</div></div> },
        { label: "Type", render: (p) => titleCase(p.kind) },
        { label: "Stage", render: (p) => <Badge value={p.status} /> },
        { label: "Price", render: (p) => (p.price_inr ? `${inr(p.price_inr)} ${p.billing?.replace("_", " ") ?? ""}` : "—") },
      ]}
    />
  );
}

export function RevenuePage() {
  return (
    <RecordsPage<LedgerEntry>
      collection="ledger" eyebrow="Revenue portfolio" title="Revenue"
      intro={<>Every amount here is a <Truth value="fact" /> you recorded. MATT never generates revenue figures.</>}
      empty="No revenue or expenses recorded yet."
      summary={(rows) => {
        const sum = (kind: string) => rows.filter((r) => r.kind === kind).reduce((s, r) => s + Number(r.amount_inr), 0);
        const byCat = new Map<string, number>();
        rows.filter((r) => r.kind === "revenue").forEach((r) => byCat.set(r.category, (byCat.get(r.category) ?? 0) + Number(r.amount_inr)));
        return (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Revenue" value={inr(sum("revenue"))} hint="All recorded" />
            <Stat label="Expenses" value={inr(sum("expense"))} hint="All recorded" />
            <Stat label="Profit" value={inr(sum("revenue") - sum("expense"))} />
            <Stat label="Top stream" value={[...byCat].sort((a, b) => b[1] - a[1])[0]?.[0]?.replace(/_/g, " ") ?? "—"} />
          </div>
        );
      }}
      fields={[
        { name: "kind", label: "Type", type: "select", options: ["revenue", "expense"] },
        { name: "amount_inr", label: "Amount (₹)", type: "number", required: true },
        { name: "category", label: "Stream", type: "select", options: REVENUE_CATEGORIES },
        { name: "description", label: "Description", required: true },
        { name: "occurred_on", label: "Date", type: "date", required: true },
        { name: "recurring", label: "Recurring", type: "checkbox" },
      ]}
      toBody={(v) => ({ ...v, occurred_on: v.occurred_on || today() })}
      columns={[
        { label: "Date", render: (r) => r.occurred_on },
        { label: "Type", render: (r) => <Badge value={r.kind === "revenue" ? "won" : "lost"} /> },
        { label: "Description", render: (r) => r.description },
        { label: "Stream", render: (r) => titleCase(r.category) },
        { label: "Amount", render: (r) => <span className="font-mono">{inr(r.amount_inr)}{r.recurring ? " ↻" : ""}</span> },
      ]}
    />
  );
}

export function ExperimentsPage() {
  return (
    <RecordsPage<Experiment>
      collection="experiments" eyebrow="Validation" title="Experiments"
      empty="No experiments yet. Write down a hypothesis before spending time or money on it."
      fields={[
        { name: "name", label: "Name", required: true },
        { name: "target", label: "Target audience" },
        { name: "budget_inr", label: "Budget (₹)", type: "number" },
        { name: "status", label: "Status", type: "select", options: ["planned", "running", "completed", "stopped"] },
        { name: "hypothesis", label: "Hypothesis", type: "textarea", required: true },
        { name: "expected", label: "Expected result", type: "textarea" },
      ]}
      toBody={(v) => ({ ...v, budget_inr: v.budget_inr || "0", expected: v.expected || null, target: v.target || null })}
      columns={[
        { label: "Experiment", render: (x) => <div><div>{x.name}</div><div className="text-xs text-muted">{x.hypothesis}</div></div> },
        { label: "Status", render: (x) => <Badge value={x.status} /> },
        { label: "Budget", render: (x) => inr(x.budget_inr) },
        { label: "Result", render: (x) => x.result ?? <span className="text-muted">Pending</span> },
      ]}
    />
  );
}

export function MemoryPage() {
  return (
    <RecordsPage<Knowledge>
      collection="knowledge" eyebrow="Knowledge" title="Memory"
      intro="What MATT should remember: pricing, decisions, customer context, procedures. Short-term entries expire after their retention period."
      empty="Nothing remembered yet."
      fields={[
        { name: "title", label: "Title", required: true },
        { name: "kind", label: "Type", type: "select", options: ["long_term", "business", "customer", "procedure", "agent", "short_term"] },
        { name: "retention_days", label: "Keep for (days, blank = forever)", type: "number" },
        { name: "content", label: "Content", type: "textarea", required: true },
      ]}
      toBody={(v) => ({ ...v, retention_days: v.retention_days ? Number(v.retention_days) : null, tags: [] })}
      columns={[
        { label: "Memory", render: (k) => <div><div>{k.title}</div><div className="line-clamp-2 text-xs text-muted">{k.content}</div></div> },
        { label: "Type", render: (k) => titleCase(k.kind) },
        { label: "Expires", render: (k) => (k.expires_at ? formatDate(k.expires_at) : "Never") },
      ]}
    />
  );
}
