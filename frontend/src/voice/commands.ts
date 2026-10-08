import { api } from "../api/client";
import { titleCase } from "../lib/format";
import { NAV } from "../lib/navigation";
import { isStopPhrase } from "./wake";

/** What a command produced: something to say, and optionally somewhere to go. */
export interface CommandOutcome {
  say: string;
  navigate?: string;
  /** End the conversation and go back to waiting for "Hey Matt". */
  sleep?: boolean;
  logout?: boolean;
  /** A web page to open (search results, YouTube, Gmail…). */
  link?: { label: string; url: string };
  /** A backend task started by this command; MATT announces when it finishes. */
  taskId?: number;
  /** Speak again after `ms`: timers and reminders. */
  timer?: { ms: number; label?: string };
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
  "opportunities, brief you on status, or tell you what we've earned today. Ask me anything else in your own " +
  "words and I'll answer or hand the work to the team. I can also set timers and reminders, do quick maths, search the web, play YouTube, " +
  "open any page, look up any agent, and sign you out.";

// Mirrors backend app/core/money.py. Money only ever comes in, so anything that sounds like moving money out
// skips every local shortcut and goes straight to /api/command, where the money rule refuses it.
const MONEY = "(?:money|funds?|cash|₹|rs\\.?|inr|rupees?|amount|payment|upi|salary|fees?)";
const ALWAYS_OUT = /\b(?:payouts?|pay\s*out|withdraw(?:al|s)?|debit(?:ed|s)?|refund(?:ed|s)?|chargeback)\b/i;
const SEND_MONEY = new RegExp(`\\b(?:send|transfer|wire|remit|pay|move|disburse)\\b(?:\\s+\\S+){0,4}?\\s+${MONEY}\\b`, "i");
const INBOUND = /\b(?:invoice|request|collect|receiv\w*|link|qr|bill)\b/i;
export const isOutboundMoney = (text: string) => ALWAYS_OUT.test(text) || (SEND_MONEY.test(text) && !INBOUND.test(text));

/** Interpret one spoken or typed command against the live MATT API. */
export async function runCommand(raw: string, ctx: CommandContext): Promise<CommandOutcome> {
  const text = raw.trim().replace(/[.!?]+$/, "");
  const t = text.toLowerCase();
  if (!t) return { say: "I didn't catch that." };

  if (isStopPhrase(t) || /^(go to sleep|sleep|that's all|thanks?( you)?|nothing)$/.test(t))
    return { say: "Standing by.", sleep: true };

  if (isOutboundMoney(text)) return askAgents(text);

  // "Stop trading" is the trading kill switch: always send it straight to the backend.
  if (/\b(?:stop|halt|kill|pause|freeze)\b.{0,20}\btrad(?:ing|es)\b|\bkill switch\b/i.test(text)) return askAgents(text);

  if (has(t, "sign out", "log out", "logout")) return { say: `Signing you out, ${ctx.userName}.`, logout: true };

  // Only a bare "help": "help me write an email" is a real request for the brain.
  if (/^(help|what can you do|capabilities|what are your capabilities)$/.test(t)) return { say: CAPABILITIES };

  if (/\b(who are you|your name|introduce yourself)\b/.test(t))
    return { say: "I'm MATT, the operating brain of your autonomous company. " + CAPABILITIES };

  if (/^(hi|hello|hey|good (morning|afternoon|evening))\b/.test(t))
    return { say: `Hello ${ctx.userName}. What needs to be done?` };

  const quick = everydaySkill(text, t);
  if (quick) return quick;

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
    // Only a clear agent lookup is answered here; "what is the capital of France" goes to MATT's brain.
    const named = /\b(agent|skill)\b/i.test(text);
    const key = q.toLowerCase();
    const first = named ? hits[0] : hits.find((h) => h.name.toLowerCase() === key || h.slug === key.replace(/\s+/g, "-"));
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

/** Anything MATT can't answer locally goes to the backend command API: workflows or MATT's brain. */
async function askAgents(text: string): Promise<CommandOutcome> {
  const res = await api.command(text);
  // The brain answers inline; workflows keep running, so MATT reports back when they finish.
  const background = res.task_id !== null && res.intent !== "ceo" && res.intent !== "chat";
  const page = typeof res.data.navigate === "string" ? res.data.navigate : INTENT_PAGE[res.intent];
  return { say: res.reply, navigate: page, taskId: background ? (res.task_id ?? undefined) : undefined };
}

const UNITS: Record<string, number> = { second: 1000, sec: 1000, minute: 60_000, min: 60_000, hour: 3_600_000, hr: 3_600_000 };
const NUMBER_WORDS: Record<string, number> = {
  a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
  fifteen: 15, twenty: 20, thirty: 30, forty: 40, "forty-five": 45, fifty: 50, sixty: 60, ninety: 90,
};
const num = (w: string) => (/^\d+(\.\d+)?$/.test(w) ? Number(w) : NUMBER_WORDS[w.toLowerCase()]);

const SITES: Record<string, string> = {
  youtube: "https://www.youtube.com", google: "https://www.google.com", gmail: "https://mail.google.com",
  whatsapp: "https://web.whatsapp.com", linkedin: "https://www.linkedin.com", instagram: "https://www.instagram.com",
  twitter: "https://x.com", x: "https://x.com", facebook: "https://www.facebook.com", github: "https://github.com",
  maps: "https://www.google.com/maps", "google maps": "https://www.google.com/maps", calendar: "https://calendar.google.com",
  drive: "https://drive.google.com", chatgpt: "https://chatgpt.com", render: "https://dashboard.render.com",
};

const JOKES = [
  "I told the CFO agent a joke about money. It didn't find it very capital.",
  "Why did the startup cross the road? To pivot to the other side.",
  "I'd tell you a UDP joke, but you might not get it.",
  "My cost optimisation agent cut my jokes budget. This is the last one.",
];

/** Everyday Alexa-style requests MATT can do instantly in the browser, with no backend or AI model. */
function everydaySkill(text: string, t: string): CommandOutcome | null {
  // Timers and reminders: "set a timer for 5 minutes", "remind me in 10 minutes to call Ravi".
  const timer = /\b(?:timer|remind me|reminder)\b.*?\b(\d+(?:\.\d+)?|[a-z-]+)\s+(second|sec|minute|min|hour|hr)s?\b(?:\s+(?:to|that|about)\s+(.+))?/i.exec(text);
  if (timer?.[1] && timer[2]) {
    const n = num(timer[1]);
    if (n) {
      const unit = timer[2].toLowerCase();
      const label = timer[3]?.trim() || (/remind/i.test(text) ? /\bto\s+(.+?)\s+in\b/i.exec(text)?.[1] : undefined);
      const span = `${n} ${unit.startsWith("h") ? "hour" : unit.startsWith("m") ? "minute" : "second"}${n === 1 ? "" : "s"}`;
      return {
        say: label ? `Okay, I'll remind you to ${label} in ${span}.` : `Timer set for ${span}.`,
        timer: { ms: n * (UNITS[unit] ?? 60_000), label },
      };
    }
  }

  // Arithmetic: "what is 25 times 4", "15 percent of 2400".
  const math = /^(?:what(?:'s| is)|calculate|how much is)?\s*(-?\d[\d,.]*)\s*(plus|\+|minus|-|times|x|\*|multiplied by|divided by|\/|percent of|% of)\s*(-?\d[\d,.]*)\s*\??$/i.exec(t);
  if (math?.[1] && math[2] && math[3]) {
    const a = Number(math[1].replace(/,/g, ""));
    const b = Number(math[3].replace(/,/g, ""));
    const op = math[2].toLowerCase();
    const r = /plus|\+/.test(op) ? a + b : /minus|-/.test(op) ? a - b : /percent|%/.test(op) ? (a / 100) * b
      : /divided|\//.test(op) ? (b === 0 ? NaN : a / b) : a * b;
    if (Number.isFinite(r)) return { say: `That's ${Number(r.toFixed(4)).toLocaleString("en-IN")}.` };
  }

  if (/\b(tell me a joke|joke|make me laugh)\b/.test(t)) {
    return { say: JOKES[Math.floor(Math.random() * JOKES.length)] ?? "I'm all out of jokes." };
  }

  if (/\b(thank you|thanks)\b/.test(t) && t.split(" ").length <= 4) return { say: "Anytime.", sleep: true };

  // "play lo-fi on youtube", "search youtube for …"
  const yt = /^(?:play|search youtube for|youtube)\s+(.+?)(?:\s+on youtube)?$/i.exec(text);
  if (yt?.[1] && (/youtube/i.test(text) || /^play\b/i.test(text))) {
    const q = yt[1];
    return { say: `Here's ${q} on YouTube.`, link: { label: `YouTube: ${q}`, url: `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}` } };
  }

  // "search for …", "google …"
  const search = /^(?:search (?:the web|google|online) for|google)\s+(.+)$/i.exec(text);
  if (search?.[1]) {
    const q = search[1];
    return { say: `Searching the web for ${q}.`, link: { label: `Google: ${q}`, url: `https://www.google.com/search?q=${encodeURIComponent(q)}` } };
  }

  // "open youtube", "open gmail"
  const open = /^(?:open|launch|go to)\s+(.+?)$/i.exec(t);
  const site = open?.[1] ? SITES[open[1].replace(/^the\s+/, "")] : undefined;
  if (open?.[1] && site) return { say: `Opening ${titleCase(open[1])}.`, link: { label: titleCase(open[1]), url: site } };

  return null;
}
