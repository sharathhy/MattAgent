import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { useAuth } from "../lib/auth";
import { runCommand } from "./commands";
import { startMic, type MicMonitor } from "./mic";
import { recognitionCtor, speak, stopSpeaking, type Recognition } from "./speech";
import { loadVoiceprint, voiceAccepted, type Voiceprint } from "./voiceprint";
import { detectWake } from "./wake";

/**
 * MATT's voice loop:
 *   sleeping  — mic open, waiting for "Hey Matt"
 *   awake     — asked "what needs to be done?", listening for the command
 *   thinking  — running the command against the API
 *   speaking  — answering out loud (recognition paused so MATT doesn't hear itself)
 * `idle` means the browser needs a tap before it will open the mic; `blocked` means the
 * mic permission was refused; `off` means the owner muted the always-on mic.
 */
export type VoiceState =
  | "unsupported"
  | "idle"
  | "blocked"
  | "error"
  | "off"
  | "sleeping"
  | "awake"
  | "thinking"
  | "speaking";

export interface LogEntry {
  id: number;
  who: "you" | "matt" | "system";
  text: string;
  link?: { label: string; url: string };
}

/** Live signals the brain animation samples every frame (no React re-render). */
export interface BrainSignals {
  mic(): number;
  voice(): number;
}

interface VoiceApi {
  state: VoiceState;
  interim: string;
  log: LogEntry[];
  /** Why voice isn't working, in plain words, when it isn't. */
  problem: string | null;
  recognitionSupported: boolean;
  signals: BrainSignals;
  voiceprint: Voiceprint | null;
  /** Open the mic (needs a tap in some browsers). */
  start(): void;
  /** Mute or unmute the always-on mic. */
  setEnabled(on: boolean): void;
  /** Skip the wake phrase, e.g. from a tap on the brain. */
  wake(): void;
  submit(text: string): void;
  refreshVoiceprint(): void;
  /** Pause command handling while enrolling, so "Hey Matt" samples don't trigger it. */
  setEnrolling(on: boolean): void;
  getMic(): Promise<MicMonitor>;
}

const VoiceContext = createContext<VoiceApi | null>(null);
const ENABLED_KEY = "matt.voice.enabled";
const AWAKE_TIMEOUT_MS = 12_000;
const LOCK_WINDOW_MS = 3_500;
/**
 * Phones give the microphone to one user at a time: a level meter would starve speech
 * recognition there, so on mobile only recognition opens the mic.
 */
const MOBILE = typeof navigator !== "undefined" && /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);

const ERROR_TEXT: Record<string, string> = {
  network:
    "This browser can't reach its speech service. Brave and some Chromium browsers block it; use Chrome, Edge or Safari, or type below.",
  "audio-capture": "No microphone was found. Plug one in or check your system sound settings.",
  "service-not-allowed": "This browser doesn't allow speech recognition here. Use Chrome, Edge or Safari, or type below.",
};

const readEnabled = () => {
  try {
    return localStorage.getItem(ENABLED_KEY) !== "off";
  } catch {
    return true;
  }
};

export function VoiceProvider({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const Ctor = recognitionCtor();
  const email = user?.email ?? "";
  const userName = user?.full_name?.split(" ")[0] || "boss";

  const [state, setStateRaw] = useState<VoiceState>(() => (Ctor ? (readEnabled() ? "idle" : "off") : "unsupported"));
  const [interim, setInterim] = useState("");
  const [log, setLog] = useState<LogEntry[]>([]);
  const [problem, setProblem] = useState<string | null>(null);
  const [voiceprint, setVoiceprint] = useState<Voiceprint | null>(() => (email ? loadVoiceprint(email) : null));

  const stateRef = useRef(state);
  const recRef = useRef<Recognition | null>(null);
  const micRef = useRef<MicMonitor | null>(null);
  const wantListening = useRef(false);
  const pausedForSpeech = useRef(false);
  const enrolling = useRef(false);
  const restartDelay = useRef(250);
  const awakeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const lastWord = useRef(0);
  const nextId = useRef(1);
  const warnedBlocked = useRef(false);
  const failures = useRef(0);
  const heardAt = useRef(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  /** Background tasks started by voice, announced when they finish. */
  const pendingTasks = useRef(new Set<number>());
  const lastEventId = useRef(0);
  const vpRef = useRef(voiceprint);
  const handleFinalRef = useRef<(text: string) => void>(() => {});

  const setState = useCallback((s: VoiceState) => {
    stateRef.current = s;
    setStateRaw(s);
  }, []);

  const push = useCallback((who: LogEntry["who"], text: string, link?: LogEntry["link"]) => {
    const id = nextId.current++;
    setLog((l) => [...l.slice(-30), { id, who, text, link }]);
  }, []);

  const signals = useMemo<BrainSignals>(
    () => ({
      // Without a level meter (phones), pulse whenever the recogniser hears words.
      mic: () => micRef.current?.level() ?? 0.55 * Math.exp(-(performance.now() - heardAt.current) / 350),
      voice: () => {
        if (stateRef.current !== "speaking") return 0;
        const since = performance.now() - lastWord.current;
        return 0.35 + 0.65 * Math.exp(-since / 160);
      },
    }),
    [],
  );

  const getMic = useCallback(async () => {
    if (!micRef.current) micRef.current = await startMic();
    return micRef.current;
  }, []);

  const startRecognition = useCallback(() => {
    const open = () => {
      if (!Ctor || recRef.current) return;
      const rec = new Ctor();
      rec.continuous = true;
      rec.interimResults = true;
      rec.maxAlternatives = 1;
      rec.lang = navigator.language || "en-US";
      rec.onstart = () => {
        restartDelay.current = 250;
      };
      rec.onresult = (e) => {
        failures.current = 0;
        heardAt.current = performance.now();
        setProblem(null);
        let partial = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          const text = r?.[0]?.transcript ?? "";
          if (r?.isFinal) handleFinalRef.current(text);
          else partial += text;
        }
        setInterim(partial.trim());
        // Light up as soon as the wake phrase is heard, before the recogniser finalises it.
        if (stateRef.current === "sleeping" && detectWake(partial)) setState("awake");
      };
      rec.onerror = (e) => {
        if (e.error === "no-speech" || e.error === "aborted") return;
        if (e.error === "not-allowed") {
          wantListening.current = false;
          // Without a prior tap some browsers refuse silently; a tap fixes that, a real denial doesn't.
          const tapped = (navigator as { userActivation?: { hasBeenActive: boolean } }).userActivation?.hasBeenActive;
          setState(tapped === false ? "idle" : "blocked");
          return;
        }
        if (e.error === "audio-capture" && micRef.current) {
          // The level meter is holding the mic; give it to recognition instead.
          micRef.current.stop();
          micRef.current = null;
          return;
        }
        if (e.error === "language-not-supported") {
          rec.lang = "en-US";
          return;
        }
        failures.current += 1;
        if (failures.current >= 3 || e.error === "service-not-allowed") {
          wantListening.current = false;
          setProblem(ERROR_TEXT[e.error] ?? `Speech recognition failed (${e.error}). Type below instead.`);
          setState("error");
        }
      };
      rec.onend = () => {
        // A newer session may already be running (we abort and reopen around speech).
        if (recRef.current !== rec) return;
        recRef.current = null;
        setInterim("");
        if (!wantListening.current || pausedForSpeech.current) return;
        // Chrome ends continuous sessions every minute or so; reopen quietly, backing off on failures.
        const delay = restartDelay.current;
        restartDelay.current = Math.min(delay * 2, 5000);
        setTimeout(() => {
          if (wantListening.current && !pausedForSpeech.current) open();
        }, delay);
      };
      recRef.current = rec;
      try {
        rec.start();
      } catch {
        recRef.current = null;
      }
    };
    open();
  }, [Ctor, setState]);

  const begin = useCallback(async () => {
    if (!Ctor) return;
    setProblem(null);
    failures.current = 0;
    try {
      if (!MOBILE) await getMic();
    } catch (err) {
      const denied = err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "SecurityError");
      if (denied) {
        setState("blocked");
        return;
      }
      // No analyser (e.g. no AudioContext): recognition still works, the brain just won't react to volume.
    }
    wantListening.current = true;
    pausedForSpeech.current = false;
    if (["idle", "blocked", "off", "error"].includes(stateRef.current)) setState("sleeping");
    startRecognition();
  }, [Ctor, getMic, setState, startRecognition]);

  const goToSleep = useCallback(() => {
    clearTimeout(awakeTimer.current);
    if (wantListening.current) setState("sleeping");
    else setState(Ctor ? (readEnabled() ? "idle" : "off") : "unsupported");
  }, [Ctor, setState]);

  const listenForCommand = useCallback(() => {
    clearTimeout(awakeTimer.current);
    if (!wantListening.current) {
      goToSleep();
      return;
    }
    setState("awake");
    awakeTimer.current = setTimeout(() => {
      if (stateRef.current === "awake") setState("sleeping");
    }, AWAKE_TIMEOUT_MS);
  }, [goToSleep, setState]);

  const say = useCallback(
    async (text: string) => {
      setState("speaking");
      pausedForSpeech.current = true;
      recRef.current?.abort();
      recRef.current = null;
      setInterim("");
      lastWord.current = performance.now();
      const result = await speak(text, () => {
        lastWord.current = performance.now();
      });
      if (result === "blocked" && !warnedBlocked.current) {
        warnedBlocked.current = true;
        push("system", "Your browser blocked spoken replies. Tap anywhere on the page to allow them.");
      }
      pausedForSpeech.current = false;
      if (wantListening.current) startRecognition();
    },
    [push, setState, startRecognition],
  );

  const execute = useCallback(
    async (command: string) => {
      clearTimeout(awakeTimer.current);
      push("you", command);
      setState("thinking");
      // The CEO agent can take a while; say so instead of looking frozen.
      const slow = setTimeout(() => push("system", "Working on it with the team…"), 2500);
      let outcome;
      try {
        outcome = await runCommand(command, { userName });
      } catch (err) {
        outcome = { say: `That failed: ${err instanceof Error ? err.message : "unknown error"}.` };
      } finally {
        clearTimeout(slow);
      }
      if (outcome.navigate) navigate(outcome.navigate);
      // Commands like "start autopilot" change what the HUD shows; refresh it right away.
      void qc.invalidateQueries({ queryKey: ["autopilot"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      push("matt", outcome.say, outcome.link);
      if (outcome.link) {
        // Works when the command was typed or tapped; voice-only commands get the link in the log.
        window.open(outcome.link.url, "_blank", "noopener");
      }
      if (outcome.taskId !== undefined) pendingTasks.current.add(outcome.taskId);
      if (outcome.timer) {
        const { ms, label } = outcome.timer;
        timers.current.push(
          setTimeout(() => {
            const text = label ? `Reminder: ${label}.` : "Your timer is done.";
            push("matt", text);
            void say(text).then(() => {
              if (stateRef.current === "speaking") setState(wantListening.current ? "sleeping" : "idle");
            });
          }, ms),
        );
      }
      await say(outcome.say);
      if (outcome.logout) {
        wantListening.current = false;
        recRef.current?.abort();
        recRef.current = null;
        qc.clear();
        logout();
        return;
      }
      if (outcome.sleep) goToSleep();
      else listenForCommand();
    },
    [goToSleep, listenForCommand, logout, navigate, push, qc, say, setState, userName],
  );

  const greet = useCallback(async () => {
    await say(`Yes ${userName}? What needs to be done?`);
    listenForCommand();
  }, [listenForCommand, say, userName]);

  useEffect(() => {
    handleFinalRef.current = (raw: string) => {
      const text = raw.trim();
      const s = stateRef.current;
      if (!text || enrolling.current || s === "thinking" || s === "speaking") return;
      const wake = detectWake(text);
      if (s === "sleeping" && !wake) return;
      // The lock needs the level meter's spectrum; where there is none (phones) it can't judge, so it steps aside.
      const sample = micRef.current ? micRef.current.recentProfile(LOCK_WINDOW_MS) : null;
      if (micRef.current && !voiceAccepted(vpRef.current, sample)) {
        push("system", `Ignored "${text}": voice didn't match the enrolled owner.`);
        return;
      }
      const command = wake ? wake.rest : text;
      if (command.length > 1) void execute(command);
      else void greet();
    };
  }, [execute, greet, push]);

  // Like Alexa telling you the oven timer is done: report back when work started by voice finishes.
  useEffect(() => {
    const tick = setInterval(async () => {
      if (pendingTasks.current.size === 0) return;
      try {
        const batch = await api.events(lastEventId.current);
        for (const e of batch) {
          lastEventId.current = Math.max(lastEventId.current, e.id);
          const id = e.payload.task_id as number | undefined;
          if (id === undefined || !pendingTasks.current.has(id)) continue;
          if (e.type !== "task.succeeded" && e.type !== "task.failed") continue;
          pendingTasks.current.delete(id);
          const detail = String(e.payload.summary ?? e.payload.error ?? "").split("\n")[0]?.slice(0, 220) ?? "";
          const text = e.type === "task.succeeded" ? `Task done. ${detail}` : `That task failed: ${detail}`;
          push("matt", text);
          if (stateRef.current === "sleeping" || stateRef.current === "idle" || stateRef.current === "off") {
            const before = stateRef.current;
            void say(text).then(() => {
              if (stateRef.current === "speaking") setState(wantListening.current ? "sleeping" : before);
            });
          }
        }
      } catch {
        /* offline for a moment; try again next tick */
      }
    }, 4000);
    return () => clearInterval(tick);
  }, [push, say, setState]);

  // Always-on: open the mic as soon as the owner is signed in.
  useEffect(() => {
    if (!Ctor || !readEnabled()) return;
    const t = setTimeout(() => void begin(), 0);
    return () => clearTimeout(t);
  }, [Ctor, begin]);

  // If the browser needs a gesture first (or speech was blocked), the first tap anywhere starts it.
  useEffect(() => {
    const onGesture = () => {
      micRef.current?.resume();
      if (!warnedBlocked.current && "speechSynthesis" in window) {
        // Unlock spoken replies: browsers only allow speech after the first tap.
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(""));
      }
      if (stateRef.current === "idle") void begin();
    };
    window.addEventListener("pointerdown", onGesture);
    window.addEventListener("keydown", onGesture);
    return () => {
      window.removeEventListener("pointerdown", onGesture);
      window.removeEventListener("keydown", onGesture);
    };
  }, [begin]);

  // Chrome may drop recognition while the tab is hidden; reopen when it comes back.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible" && wantListening.current && !pausedForSpeech.current) startRecognition();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [startRecognition]);

  useEffect(
    () => () => {
      wantListening.current = false;
      clearTimeout(awakeTimer.current);
      timers.current.forEach(clearTimeout);
      recRef.current?.abort();
      micRef.current?.stop();
      micRef.current = null;
      stopSpeaking();
    },
    [],
  );

  const setEnabled = useCallback(
    (on: boolean) => {
      try {
        localStorage.setItem(ENABLED_KEY, on ? "on" : "off");
      } catch {
        /* private mode: preference just won't persist */
      }
      if (on) {
        void begin();
        return;
      }
      wantListening.current = false;
      clearTimeout(awakeTimer.current);
      recRef.current?.abort();
      recRef.current = null;
      micRef.current?.stop();
      micRef.current = null;
      stopSpeaking();
      setState("off");
    },
    [begin, setState],
  );

  const refreshVoiceprint = useCallback(() => {
    const vp = email ? loadVoiceprint(email) : null;
    vpRef.current = vp;
    setVoiceprint(vp);
  }, [email]);

  const value = useMemo<VoiceApi>(
    () => ({
      state,
      interim,
      log,
      problem,
      recognitionSupported: Ctor !== null,
      signals,
      voiceprint,
      start: () => void begin(),
      setEnabled,
      wake: () => {
        if (stateRef.current === "thinking" || stateRef.current === "speaking") return;
        void greet();
      },
      submit: (text: string) => {
        if (text.trim()) void execute(text.trim());
      },
      refreshVoiceprint,
      setEnrolling: (on: boolean) => {
        enrolling.current = on;
      },
      getMic,
    }),
    [state, interim, log, problem, Ctor, signals, voiceprint, begin, setEnabled, greet, execute, refreshVoiceprint, getMic],
  );

  return <VoiceContext.Provider value={value}>{children}</VoiceContext.Provider>;
}

export function useVoice(): VoiceApi {
  const ctx = useContext(VoiceContext);
  if (!ctx) throw new Error("useVoice must be used inside VoiceProvider");
  return ctx;
}

export const STATE_LABEL: Record<VoiceState, string> = {
  unsupported: "Voice needs Chrome, Edge or Safari · type below",
  idle: "Tap anywhere to open the microphone",
  blocked: "Microphone blocked · allow it in the address bar",
  error: "Voice unavailable in this browser · type below",
  off: "Microphone muted",
  sleeping: "Listening for “Hey Matt”",
  awake: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking",
};
