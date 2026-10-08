import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../../api/client";
import type { MattEvent } from "../../api/types";

const TONE: Record<string, string> = {
  succeeded: "text-ok",
  failed: "text-danger",
  requested: "text-warn",
  started: "text-accent",
  received: "text-accent-2",
  cycle: "text-hot",
  ready: "text-ok",
};

function describe(e: MattEvent): string {
  const p = e.payload;
  const text = (p.objective ?? p.summary ?? p.text ?? p.action ?? p.title ?? p.error ?? "") as string;
  return `${e.type.replace(".", " ")}${text ? ` · ${String(text).slice(0, 90)}` : ""}`;
}

/** Live system log: every event MATT's agents emit, streaming in like a terminal. */
export function EventFeed() {
  const [events, setEvents] = useState<MattEvent[]>([]);
  const last = useRef(0);
  const q = useQuery({
    queryKey: ["events-feed"],
    queryFn: async () => {
      const batch = await api.events(last.current);
      const newest = batch[batch.length - 1];
      if (newest) last.current = newest.id;
      return batch;
    },
    refetchInterval: 3000,
  });

  useEffect(() => {
    const batch = q.data;
    if (!batch?.length) return;
    const t = setTimeout(() => setEvents((ev) => [...ev, ...batch].slice(-40)), 0);
    return () => clearTimeout(t);
  }, [q.data]);

  return (
    <section aria-label="Live activity" className="panel flex min-h-0 flex-col p-4">
      <h2 className="label mb-2 flex items-center gap-1.5">
        <Activity className="h-3.5 w-3.5 text-accent" aria-hidden /> Live activity
        <span className="ml-auto h-1.5 w-1.5 animate-pulse rounded-full bg-ok" aria-hidden />
      </h2>
      <ol className="max-h-56 flex-1 space-y-1 overflow-y-auto font-mono text-[11px] leading-snug">
        {events.length === 0 && <li className="text-muted">Waiting for agent activity…</li>}
        {[...events].reverse().map((e) => {
          const kind = e.type.split(".")[1] ?? "";
          return (
            <li key={e.id} className="rise flex gap-2">
              <span className="shrink-0 text-slate-500">
                {new Date(e.created_at).toLocaleTimeString([], { hour12: false })}
              </span>
              <span className={`min-w-0 break-words ${TONE[kind] ?? "text-slate-300"}`}>{describe(e)}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
