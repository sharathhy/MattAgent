import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../api/client";
import { isOutboundMoney, runCommand } from "../voice/commands";
import type { Recognition, RecognitionEvent } from "../voice/speech";
import { similarity, voiceAccepted, type Voiceprint } from "../voice/voiceprint";
import { detectWake, isStopPhrase } from "../voice/wake";
import { OWNER, mockApi, renderApp } from "./utils";

const SUMMARY = {
  total: 120,
  by_kind: { ceo: 1, executive: 9, skill: 100, meta: 10 },
  by_department: { sales: 11, marketing: 21 },
  by_status: { designed: 120 },
};
const HEALTH = { status: "ok", database: "ok", env: "test" };

afterEach(() => vi.unstubAllGlobals());

describe("wake phrase", () => {
  it.each([
    ["Hey Matt", ""],
    ["hey mat show me the agents", "show me the agents"],
    ["okay Matt, system status?", "system status?"],
    ["so I said hey Matt what time is it", "what time is it"],
    ["Matt, brief me", "brief me"],
  ])("wakes on %j", (said, rest) => {
    expect(detectWake(said)).toEqual({ rest });
  });

  it.each(["matter of fact", "hey there", "the math test"])("stays asleep on %j", (said) => {
    expect(detectWake(said)).toBeNull();
  });
});

describe("commands", () => {
  const ctx = { userName: "Sharath" };

  it("summarises the workforce from the API", async () => {
    mockApi({ "/agents/summary": SUMMARY });
    const out = await runCommand("how many agents do we have", ctx);
    expect(out.say).toContain("120 registered agents");
    expect(out.say).toContain("Marketing with 21");
  });

  it("reports system health", async () => {
    mockApi({ "/health": HEALTH });
    expect((await runCommand("system status", ctx)).say).toContain("All systems nominal");
  });

  it("opens pages", async () => {
    expect(await runCommand("open the workforce map", ctx)).toMatchObject({ navigate: "/workforce" });
    const tasks = await runCommand("show me tasks", ctx);
    expect(tasks.navigate).toBe("/tasks");
    expect(tasks.say).toBe("Opening Tasks.");
  });

  it("hands real work to the backend agents", async () => {
    const fetch = mockApi({
      "/command": { reply: "On it. I'm finding gyms in Bangalore.", intent: "website_opportunities", task_id: 7, data: {} },
    });
    const out = await runCommand("find gyms in Bangalore that need a website", ctx);
    expect(out).toEqual({ say: "On it. I'm finding gyms in Bangalore.", navigate: "/leads", taskId: 7 });
    expect(JSON.parse(fetch.mock.calls[0]?.[1]?.body as string)).toEqual({ text: "find gyms in Bangalore that need a website" });
  });

  it("asks the CEO when a lookup matches no agent", async () => {
    mockApi({ "/agents": [], "/command": { reply: "Our best bet is local SEO.", intent: "ceo", task_id: 8, data: {} } });
    expect((await runCommand("what is our best opportunity", ctx)).say).toBe("Our best bet is local SEO.");
  });

  it("goes back to sleep on stop", async () => {
    expect(await runCommand("never mind", ctx)).toMatchObject({ sleep: true });
  });
});

describe("everyday skills", () => {
  const ctx = { userName: "Sharath" };

  it("sets timers and reminders", async () => {
    expect(await runCommand("set a timer for 5 minutes", ctx)).toMatchObject({ timer: { ms: 300_000 } });
    const r = await runCommand("remind me in 10 minutes to call Ravi", ctx);
    expect(r).toMatchObject({ say: "Okay, I'll remind you to call Ravi in 10 minutes.", timer: { ms: 600_000, label: "call Ravi" } });
  });

  it("does quick maths", async () => {
    expect((await runCommand("what is 25 times 4", ctx)).say).toBe("That's 100.");
    expect((await runCommand("15 percent of 2400", ctx)).say).toBe("That's 360.");
  });

  it("opens the web for searches and YouTube", async () => {
    expect((await runCommand("play lofi beats on youtube", ctx)).link?.url).toContain("youtube.com/results?search_query=lofi%20beats");
    expect((await runCommand("google best CRM for agencies", ctx)).link?.url).toContain("google.com/search?q=best%20CRM");
    expect((await runCommand("open gmail", ctx)).link?.url).toBe("https://mail.google.com");
  });

  it("lets the backend answer money questions and opens the page it names", async () => {
    mockApi({ "/command": { reply: "Today you've earned ₹1,500.", intent: "earnings", task_id: null, data: { navigate: "/revenue" } } });
    expect(await runCommand("how much did we earn today", ctx)).toEqual({ say: "Today you've earned ₹1,500.", navigate: "/revenue", taskId: undefined });
  });

  it("sends anything that moves money out to the backend money rule, never a local shortcut", async () => {
    const refusal = "Main rule: MATT only receives money, into your own UPI account.";
    const fetchMock = mockApi({ "/command": { reply: refusal, intent: "money_rule", task_id: null, data: {} } });
    for (const cmd of ["remind me in 5 minutes to send money to Ravi", "google how to withdraw cash", "what is a refund", "open payout"]) {
      expect(isOutboundMoney(cmd)).toBe(true);
      expect((await runCommand(cmd, ctx)).say).toBe(refusal);
    }
    expect(fetchMock.mock.calls.every(([url]) => String(url).includes("/command"))).toBe(true);
    expect(isOutboundMoney("send a payment request to FitZone for 5000 rupees")).toBe(false);
    expect(isOutboundMoney("set a timer for 5 minutes")).toBe(false);
  });
});

describe("voice lock", () => {
  const vp = (enabled: boolean): Voiceprint => ({ profile: [1, -1, 2, -2], samples: 3, enrolled_at: "", enabled });

  it("accepts any voice when the lock is off", () => {
    expect(voiceAccepted(null, null)).toBe(true);
    expect(voiceAccepted(vp(false), [-1, 1, -2, 2])).toBe(true);
  });

  it("accepts a matching voice and rejects a different one", () => {
    expect(similarity([1, 2, 3], [1, 2, 3])).toBeCloseTo(1);
    expect(voiceAccepted(vp(true), [1.1, -0.9, 2.1, -1.8])).toBe(true);
    expect(voiceAccepted(vp(true), [-1, 1, -2, 2])).toBe(false);
    expect(voiceAccepted(vp(true), null)).toBe(false);
  });
});

describe("stop phrases", () => {
  it("recognises stop, Matt stop, be quiet and cancel", () => {
    for (const t of ["stop", "Stop.", "Matt stop", "hey Matt, be quiet", "cancel", "cancel that please", "shut up", "okay stop talking", "never mind"])
      expect(isStopPhrase(t)).toBe(true);
    for (const t of ["stop the autopilot campaign for gyms", "find bus stops in Pune", "cancel my subscription to the newsletter"])
      expect(isStopPhrase(t)).toBe(false);
  });

  it("hears a stop glued onto MATT's own echo during barge-in", () => {
    expect(isStopPhrase("I found twelve gyms in Mysore and matt stop", true)).toBe(true);
    expect(isStopPhrase("I found twelve gyms in Mysore", true)).toBe(false);
  });
});

/** A speech engine that talks until cancelled, so tests can interrupt it mid-sentence. */
function fakeSynthesis() {
  let current: { onend?: () => void; text: string } | null = null;
  const synth = {
    speaking: () => current !== null,
    spoken: [] as string[],
    speak(u: { onend?: () => void; text: string }) {
      current = u;
      if (u.text) synth.spoken.push(u.text);
    },
    cancel: vi.fn(() => {
      const u = current;
      current = null;
      u?.onend?.();
    }),
    getVoices: () => [],
  };
  vi.stubGlobal("speechSynthesis", synth);
  vi.stubGlobal(
    "SpeechSynthesisUtterance",
    class {
      text: string;
      constructor(text: string) {
        this.text = text;
      }
    },
  );
  return synth;
}

describe("always-on voice assistant", () => {
  it("listens on load, wakes on 'Hey Matt' and answers the command", async () => {
    const instances: Recognition[] = [];
    class FakeRecognition {
      continuous = false;
      interimResults = false;
      lang = "";
      maxAlternatives = 1;
      onresult: Recognition["onresult"] = null;
      onerror: Recognition["onerror"] = null;
      onend: Recognition["onend"] = null;
      onstart: Recognition["onstart"] = null;
      constructor() {
        instances.push(this as unknown as Recognition);
      }
      start() {}
      stop() {}
      abort() {
        this.onend?.();
      }
    }
    vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
    tokenStore.set("tok");
    mockApi({ "/auth/me": OWNER, "/agents/summary": SUMMARY, "/health": HEALTH });

    renderApp("/command-center");
    expect(await screen.findByText("Listening for “Hey Matt”")).toBeInTheDocument();

    const say = (transcript: string) => {
      const rec = instances[instances.length - 1];
      const event = { resultIndex: 0, results: { length: 1, 0: { isFinal: true, length: 1, 0: { transcript, confidence: 1 } } } };
      act(() => rec?.onresult?.(event as RecognitionEvent));
    };

    say("what's the weather");
    expect(screen.queryByText("what's the weather")).not.toBeInTheDocument();

    say("hey Matt how many agents do we have");
    expect(await screen.findByText(/You have 120 registered agents/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Listening…")).toBeInTheDocument());

    // Still awake: a follow-up needs no wake phrase.
    say("system status");
    expect(await screen.findByText(/All systems nominal/)).toBeInTheDocument();
  });

  it("stops talking the moment the owner says stop, then listens again", async () => {
    const instances: Recognition[] = [];
    class FakeRecognition {
      continuous = false;
      interimResults = false;
      lang = "";
      maxAlternatives = 1;
      onresult: Recognition["onresult"] = null;
      onerror: Recognition["onerror"] = null;
      onend: Recognition["onend"] = null;
      onstart: Recognition["onstart"] = null;
      constructor() {
        instances.push(this as unknown as Recognition);
      }
      start() {}
      stop() {}
      abort() {
        this.onend?.();
      }
    }
    vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
    const synth = fakeSynthesis();
    let release: (v: Response) => void = () => {};
    tokenStore.set("tok");
    const fetchMock = mockApi({ "/auth/me": OWNER, "/agents/summary": SUMMARY, "/health": HEALTH });
    const realFetch = fetchMock.getMockImplementation();
    fetchMock.mockImplementation(async (input, init) =>
      String(input).includes("/command") ? new Promise<Response>((r) => (release = r)) : (realFetch?.(input, init) as Promise<Response>),
    );

    renderApp("/command-center");
    expect(await screen.findByText("Listening for “Hey Matt”")).toBeInTheDocument();
    const hear = (transcript: string, isFinal = true) => {
      const rec = instances[instances.length - 1];
      const event = { resultIndex: 0, results: { length: 1, 0: { isFinal, length: 1, 0: { transcript, confidence: 1 } } } };
      act(() => rec?.onresult?.(event as RecognitionEvent));
    };

    // Mid-sentence: the mic is still open, and an interim "Matt stop" is enough.
    hear("hey Matt how many agents do we have");
    expect(await screen.findByText("Speaking")).toBeInTheDocument();
    hear("you have 120 registered agents matt stop", false);
    expect(synth.cancel).toHaveBeenCalled();
    expect(synth.speaking()).toBe(false);
    expect(await screen.findByText("Listening…")).toBeInTheDocument();
    expect(screen.getByText("Stopped.")).toBeInTheDocument();

    // While a command is still running: "cancel" drops its answer entirely.
    hear("find gyms in Mysore");
    expect(await screen.findByText("Thinking…")).toBeInTheDocument();
    hear("cancel");
    expect(await screen.findByText("Listening…")).toBeInTheDocument();
    const reply = { reply: "On it, finding gyms.", intent: "website_opportunities", task_id: 4, data: {} };
    await act(async () => release(new Response(JSON.stringify(reply), { status: 200, headers: { "Content-Type": "application/json" } })));
    expect(screen.queryByText("On it, finding gyms.")).not.toBeInTheDocument();
    expect(synth.spoken).not.toContain("On it, finding gyms.");

    // And it still takes the next command.
    hear("system status");
    expect(await screen.findByText(/All systems nominal/)).toBeInTheDocument();
  });

  it("answers typed commands when the browser has no speech recognition", async () => {
    tokenStore.set("tok");
    mockApi({ "/auth/me": OWNER, "/agents/summary": SUMMARY, "/health": HEALTH });
    renderApp("/command-center");
    await userEvent.type(await screen.findByLabelText("Command"), "what can you do{Enter}");
    expect(await screen.findByText(/audit any website/)).toBeInTheDocument();
  });
});
