import { api } from "../api/client";
import { titleCase } from "../lib/format";
import { NAV } from "../lib/navigation";

/** What a command produced: something to say, and optionally somewhere to go. */
export interface CommandOutcome {
  say: string;
  navigate?: string;
  /** End the conversation and go back to waiting for "Hey Matt". */
  sleep?: boolean;
  logout?: boolean;
}

export interface CommandContext {
  userName: string;
  now?: Date;
}

const has = (text: string, ...words: string[]) => words.some((w) => new RegExp(`\\b${w}\\b`, "i").test(text));

const list = (items: string[]) =>
  items.length <= 1 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;

/** Page aliases a person might say, mapped onto the real navigation. */
const PAGE_ALIASES: Record<string, string[]> = {
  "/command-center": ["command center", "home", "dashboard", "main screen"],
  "/workforce": ["workforce", "org chart", "organisation", "organization", "team map"],
  "/agents": ["agents", "agent list", "registry"],
  "/audit-log": ["audit log", "audit", "activity log", "history"],
};

function findPage(text: string) {
  const t = text.toLowerCase();
  for (const item of NAV) {
    const aliases = [item.label.toLowerCase(), ...(PAGE_ALIASES[item.path] ?? [])];
    if (aliases.some((a) => t.includes(a))) return item;
  }
  return null;
}

export const CAPABILITIES =
  "Ask me to find businesses in a city that need a better website, audit any website, research new " +
  "opportunities, or brief you on status. Anything else goes to your CEO agent and its team. " +
  "I can also open any page, check system health, look up any agent, and sign you out.";

/** Interpret one spoken or typed command against the live MATT API. */
export async function runCommand(raw: string, ctx: CommandContext): Promise<CommandOutcome> {
  const text = raw.trim().replace(/[.!?]+$/, "");
  const t = text.toLowerCase();
  if (!t) return { say: "I didn't catch that." };

  if (/^(stop|cancel|never ?mind|go to sleep|sleep|that's all|thanks?( you)?|nothing)$/.test(t))
    return { say: "Standing by.", sleep: true };

  if (has(t, "sign out", "log out", "logout")) return { say: `Signing you out, ${ctx.userName}.`, logout: true };

  if (has(t, "help", "what can you do", "capabilities")) return { say: CAPABILITIES };

  if (/\b(who are you|your name|introduce yourself)\b/.test(t))
    return { say: "I'm MATT, the operating brain of your autonomous company. " + CAPABILITIES };

  if (/^(hi|hello|hey|good (morning|afternoon|evening))\b/.test(t))
    return { say: `Hello ${ctx.userName}. What needs to be done?` };

  if (/\b(what time|the time|what's the date|the date|what day)\b/.test(t)) {
    const now = ctx.now ?? new Date();
    const time = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    const date = now.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
    return { say: `It's ${time} on ${date}.` };
  }

  if (/\b(health|system status|systems|online)\b/.test(t)) {
    try {
      const h = await api.health();
      return h.status === "ok"
        ? { say: `All systems nominal. Database ${h.database}, running in ${h.env}.` }
        : { say: `Systems are degraded. Database reports ${h.database}.` };
    } catch {
      return { say: "I can't reach the backend right now." };
    }
  }

  const agentQuery = /\b(?:tell me about|who is|what is|what does|look ?up|open agent)\s+(?:the\s+)?(.+?)(?:\s+(?:agent|skill|do))?$/i.exec(text);
  if (agentQuery?.[1] && !findPage(agentQuery[1])) {
    const q = agentQuery[1];
    const hits = await api.agents({ q });
    const first = hits[0];
    // No such agent: it was probably a real request ("what is our best opportunity"), so ask the CEO.
    if (!first) return askAgents(text);
    const detail = await api.agent(first.slug);
    const more = hits.length > 1 ? ` I found ${hits.length - 1} other match${hits.length > 2 ? "es" : ""} too.` : "";
    return {
      say: `${detail.name}, ${titleCase(detail.kind)} in ${titleCase(detail.department)}. ${detail.description}${more}`,
      navigate: `/agents/${detail.slug}`,
    };
  }

  const page = findPage(t);
  if (page && (has(t, "open", "show", "go to", "take me", "navigate", "display", "bring up") || t === page.label.toLowerCase())) {
    return { say: `Opening ${page.label}.`, navigate: page.path };
  }

  if (has(t, "executives", "executive team", "leadership", "c-suite")) {
    const execs = await api.agents({ kind: "executive" });
    return { say: `Your executive team is ${list(execs.map((e) => e.name))}.`, navigate: "/workforce" };
  }

  if (/\bhow many (agents|skills|executives)\b|\bworkforce\b|\b(agent|registry) summary\b/.test(t)) {
    const s = await api.registrySummary();
    const depts = Object.entries(s.by_department).sort((a, b) => b[1] - a[1]).slice(0, 3);
    return {
      say:
        `You have ${s.total} registered agents: ${s.by_kind.executive ?? 0} executives, ` +
        `${s.by_kind.skill ?? 0} skills and ${s.by_kind.meta ?? 0} self-upgrade skills. ` +
        `The largest departments are ${list(depts.map(([d, n]) => `${titleCase(d)} with ${n}`))}.`,
    };
  }

  if (/\b(audit log|recent activity|latest activity|audit trail)\b/.test(t)) {
    const logs = await api.auditLogs();
    if (!logs.length) return { say: "The audit log is empty.", navigate: "/audit-log" };
    const recent = logs.slice(0, 3).map((l) => l.action.replace(/[._]/g, " "));
    return { say: `The latest activity: ${list(recent)}.`, navigate: "/audit-log" };
  }

  return askAgents(text);
}

/** Pages to show after the backend starts work, so the owner can watch results arrive. */
const INTENT_PAGE: Record<string, string> = {
  website_opportunities: "/leads",
  opportunity_research: "/opportunities",
};

/** Anything MATT can't answer locally goes to the backend command API: workflows or the CEO agent. */
async function askAgents(text: string): Promise<CommandOutcome> {
  const res = await api.command(text);
  return { say: res.reply, navigate: INTENT_PAGE[res.intent] };
}
