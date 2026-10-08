import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../api/client";
import { runCommand } from "../voice/commands";
import type { Recognition, RecognitionEvent } from "../voice/speech";
import { similarity, voiceAccepted, type Voiceprint } from "../voice/voiceprint";
import { detectWake } from "../voice/wake";
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

  it("opens pages and flags unbuilt ones", async () => {
    expect(await runCommand("open the workforce map", ctx)).toMatchObject({ navigate: "/workforce" });
    const tasks = await runCommand("show me tasks", ctx);
    expect(tasks.navigate).toBe("/tasks");
    expect(tasks.say).toContain("isn't built yet");
  });

  it("says plainly when it can't do something", async () => {
    expect((await runCommand("launch a marketing campaign", ctx)).say).toContain("can't do that yet");
  });

  it("goes back to sleep on stop", async () => {
    expect(await runCommand("never mind", ctx)).toMatchObject({ sleep: true });
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

  it("answers typed commands when the browser has no speech recognition", async () => {
    tokenStore.set("tok");
    mockApi({ "/auth/me": OWNER, "/agents/summary": SUMMARY, "/health": HEALTH });
    renderApp("/command-center");
    await userEvent.type(await screen.findByLabelText("Command"), "what can you do{Enter}");
    expect(await screen.findByText(/I can open any page/)).toBeInTheDocument();
  });
});
