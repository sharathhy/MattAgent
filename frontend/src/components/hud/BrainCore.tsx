import { AlertTriangle, Mic } from "lucide-react";
import { useEffect, useState } from "react";

import { STATE_LABEL, useVoice, type VoiceState } from "../../voice/VoiceProvider";
import { Brain } from "../Brain";

const STATE_TONE: Record<VoiceState, string> = {
  unsupported: "text-muted",
  idle: "text-accent",
  blocked: "text-danger",
  error: "text-danger",
  off: "text-muted",
  sleeping: "text-accent",
  awake: "text-white",
  thinking: "text-accent-2",
  speaking: "text-teal-300",
};

const brainSize = () => {
  if (typeof window === "undefined") return 460;
  const w = window.innerWidth;
  return w < 420 ? Math.min(360, w - 32) : w < 1024 ? 440 : w < 1440 ? 470 : 540;
};

/** Centre of the HUD: the brain inside its reactor rings, what it hears, and why voice is off when it is. */
export function BrainCore() {
  const voice = useVoice();
  const [size, setSize] = useState(brainSize);

  useEffect(() => {
    const onResize = () => setSize(brainSize());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return (
    <section aria-label="MATT brain" className="flex flex-col items-center">
      <button
        type="button"
        onClick={voice.wake}
        className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-accent"
        aria-label="Talk to MATT"
        title="Tap to talk without the wake phrase"
      >
        <Brain state={voice.state} signals={voice.signals} size={size} />
      </button>
      <div role="status" aria-live="polite" className={`hud-title -mt-3 text-center text-xs md:text-sm ${STATE_TONE[voice.state]}`}>
        <span className={voice.state === "sleeping" ? "flicker" : voice.state === "awake" ? "animate-pulse" : ""}>
          {STATE_LABEL[voice.state]}
        </span>
      </div>
      <div className="mt-2 min-h-7 max-w-lg text-center text-lg text-cyan-100">
        {voice.interim && <span className="caret opacity-90">{voice.interim}</span>}
      </div>
      {voice.problem && (
        <p role="alert" className="mt-1 flex max-w-md items-start gap-2 rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {voice.problem}
        </p>
      )}
      {(voice.state === "idle" || voice.state === "blocked" || voice.state === "error") && (
        <button type="button" className="btn mt-3" onClick={voice.start}>
          <Mic className="h-4 w-4" aria-hidden /> {voice.state === "idle" ? "Activate voice" : "Try voice again"}
        </button>
      )}
      {voice.state === "blocked" && (
        <p className="mt-2 max-w-md text-center text-xs text-muted">
          Click the lock or mic icon in the address bar, allow the microphone for this site, then press “Try voice again”.
        </p>
      )}
    </section>
  );
}
