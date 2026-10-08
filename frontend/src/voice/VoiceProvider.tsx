import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

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
export type VoiceState = "unsupported" | "idle" | "blocked" | "off" | "sleeping" | "awake" | "thinking" | "speaking";

export interface LogEntry {
  id: number;
  who: "you" | "matt" | "system";
  text: string;
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
  const vpRef = useRef(voiceprint);
  const handleFinalRef = useRef<(text: string) => void>(() => {});

  const setState = useCallback((s: VoiceState) => {
    stateRef.current = s;
    setStateRaw(s);
  }, []);

  const push = useCallback((who: LogEntry["who"], text: string) => {
    const id = nextId.current++;
    setLog((l) => [...l.slice(-30), { id, who, text }]);
  }, []);

  const signals = useMemo<BrainSignals>(
    () => ({
      mic: () => micRef.current?.level() ?? 0,
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
        let partial = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          const text = r?.[0]?.transcript ?? "";
          if (r?.isFinal) handleFinalRef.current(text);
          else partial += text;
        }
        setInterim(partial.trim());
      };
      rec.onerror = (e) => {
        if (e.error === "not-allowed" || e.error === "service-not-allowed") {
          wantListening.current = false;
          setState("blocked");
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
    try {
      await getMic();
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
    if (stateRef.current === "idle" || stateRef.current === "blocked" || stateRef.current === "off") setState("sleeping");
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
      push("matt", outcome.say);
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
      if (!voiceAccepted(vpRef.current, micRef.current?.recentProfile(LOCK_WINDOW_MS) ?? null)) {
        push("system", `Ignored "${text}": voice didn't match the enrolled owner.`);
        return;
      }
      const command = wake ? wake.rest : text;
      if (command.length > 1) void execute(command);
      else void greet();
    };
  }, [execute, greet, push]);

  // Always-on: open the mic as soon as the owner is signed in.
  useEffect(() => {
    if (!Ctor || !readEnabled()) return;
    const t = setTimeout(() => void begin(), 0);
    return () => clearTimeout(t);
  }, [Ctor, begin]);

  // If the browser needs a gesture first (or speech was blocked), the first tap anywhere starts it.
  useEffect(() => {
    const onGesture = () => {
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
    [state, interim, log, Ctor, signals, voiceprint, begin, setEnabled, greet, execute, refreshVoiceprint, getMic],
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
  off: "Microphone muted",
  sleeping: "Listening for “Hey Matt”",
  awake: "Listening…",
  thinking: "Thinking…",
  speaking: "Speaking",
};
