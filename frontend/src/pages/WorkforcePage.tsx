import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { HierarchyNode } from "../api/types";
import { ErrorState, Loading, StatusBadge } from "../components/ui";
import { titleCase } from "../lib/format";

export function WorkforcePage() {
  const tree = useQuery({ queryKey: ["hierarchy"], queryFn: api.hierarchy });
  return (
    <div className="space-y-5">
      <header>
        <div className="label">Organisation</div>
        <h1 className="mt-1 text-2xl font-semibold">AI Workforce Map</h1>
      </header>
      {tree.isPending && <Loading />}
      {tree.isError && <ErrorState error={tree.error} />}
      {tree.data?.map((root) => (
        <div key={root.slug} className="space-y-6">
          <div className="flex justify-center">
            <NodeCard node={root} highlight />
          </div>
          <div className="grid items-start gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {root.children
              .filter((c) => c.kind === "executive")
              .map((exec) => (
                <ExecutiveColumn key={exec.slug} node={exec} />
              ))}
          </div>
          <DirectReports node={root} />
        </div>
      ))}
    </div>
  );
}

function NodeCard({ node, highlight = false }: { node: HierarchyNode; highlight?: boolean }) {
  return (
    <Link
      to={`/agents/${node.slug}`}
      className={`panel block px-4 py-3 transition hover:border-accent/60 ${highlight ? "border-accent/50 shadow-[0_0_24px_rgb(34_211_238/0.15)]" : ""}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium">{node.name}</span>
        <StatusBadge status={node.status} />
      </div>
      <div className="text-xs text-muted">{node.role}</div>
    </Link>
  );
}

function ExecutiveColumn({ node }: { node: HierarchyNode }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-2">
      <NodeCard node={node} />
      {node.children.length > 0 && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="label flex items-center gap-1 hover:text-accent"
        >
          <ChevronRight className={`h-3 w-3 transition ${open ? "rotate-90" : ""}`} aria-hidden />
          {node.children.length} agents · {titleCase(node.department)}
        </button>
      )}
      {open && (
        <ul className="space-y-1 border-l border-line pl-3">
          {node.children.map((c) => (
            <li key={c.slug}>
              <Link to={`/agents/${c.slug}`} className="text-sm text-slate-300 hover:text-accent">{c.name}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Non-executive agents that report straight to the root (the intelligence unit). */
function DirectReports({ node }: { node: HierarchyNode }) {
  const direct = node.children.filter((c) => c.kind !== "executive");
  if (direct.length === 0) return null;
  return (
    <section>
      <h2 className="label mb-2">Reports directly to {node.name}</h2>
      <ul className="flex flex-wrap gap-2">
        {direct.map((c) => (
          <li key={c.slug}>
            <Link to={`/agents/${c.slug}`} className="panel block px-3 py-1.5 text-sm hover:border-accent/60">
              {c.name}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
