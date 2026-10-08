import { Mic, MicOff, Send, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { STATE_LABEL, useVoice, type VoiceState } from "../voice/VoiceProvider";
import { Brain } from "./Brain";

const STATE_TONE: Record<VoiceState, string> = {
  unsupported: "text-muted",
  idle: "text-accent",
  blocked: "text-danger",
  off: "text-muted",
  sleeping: "text-accent",
  awake: "text-cyan-200",
  thinking: "text-accent-2",
  speaking: "text-teal-300",
};

/** The command center hero: MATT's brain, what it is hearing, the conversation, and a typed fallback. */
export function BrainConsole() {
  const voice = useVoice();
  const [text, setText] = useState("");
  const logEnd = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState(() => (typeof window !== "undefined" && window.innerWidth < 640 ? 300 : 440));

  useEffect(() => {
    const onResize = () => setSize(window.innerWidth < 640 ? 300 : 440);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    logEnd.current?.scrollIntoView?.({ block: "nearest" });
  }, [voice.log.length]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    voice.submit(text);
    setText("");
  };

  const listening = voice.state !== "off" && voice.state !== "unsupported";

  return (
    <section aria-label="MATT brain" className="panel scanline relative overflow-hidden">
      <div className="grid gap-6 p-4 md:p-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <div className="flex flex-col items-center">
          <button
            type="button"
            onClick={voice.wake}
            className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-accent"
            aria-label="Talk to MATT"
            title="Tap to talk without the wake phrase"
          >
            <Brain state={voice.state} signals={voice.signals} size={size} />
          </button>
          <div role="status" aria-live="polite" className={`label -mt-2 text-center ${STATE_TONE[voice.state]}`}>
            <span className={voice.state === "sleeping" || voice.state === "awake" ? "animate-pulse" : ""}>
              {STATE_LABEL[voice.state]}
            </span>
          </div>
          <div className="mt-2 min-h-6 max-w-md text-center font-mono text-sm text-slate-300">
            {voice.interim && <span className="opacity-80">“{voice.interim}”</span>}
          </div>
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {voice.recognitionSupported && (
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1 text-xs text-slate-300 hover:border-accent hover:text-accent"
                onClick={() => (listening ? voice.setEnabled(false) : voice.setEnabled(true))}
              >
                {listening ? <MicOff className="h-3.5 w-3.5" aria-hidden /> : <Mic className="h-3.5 w-3.5" aria-hidden />}
                {listening ? "Mute mic" : "Unmute mic"}
              </button>
            )}
            {(voice.state === "idle" || voice.state === "blocked") && (
              <button type="button" className="btn px-3 py-1 text-xs" onClick={voice.start}>
                <Mic className="h-3.5 w-3.5" aria-hidden /> Enable microphone
              </button>
            )}
          </div>
        </div>

        <div className="flex min-h-[320px] flex-col">
          <div className="label mb-3 flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5 text-accent" aria-hidden /> Conversation
          </div>
          <div className="flex-1 space-y-2 overflow-y-auto pr-1 lg:max-h-[380px]" aria-label="Conversation log">
            {voice.log.length === 0 && (
              <div className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">
                Say <span className="text-accent">“Hey Matt”</span>, then ask: <em>“find gyms in Bangalore”</em>,{" "}
                <em>“audit example.com”</em>, <em>“brief me”</em>, <em>“what should we build next?”</em> or{" "}
                <em>“what can you do?”</em>. You can also type below.
              </div>
            )}
            {voice.log.map((entry) => (
              <div
                key={entry.id}
                className={`max-w-[90%] rounded-xl px-3 py-2 text-sm ${
                  entry.who === "you"
                    ? "ml-auto bg-accent/15 text-cyan-100"
                    : entry.who === "matt"
                      ? "border border-line bg-slate-900/70 text-slate-100"
                      : "mx-auto text-center text-xs text-muted"
                }`}
              >
                {entry.who === "matt" && <span className="mr-1 font-mono text-[10px] text-accent">MATT</span>}
                {entry.text}
              </div>
            ))}
            <div ref={logEnd} />
          </div>
          <form onSubmit={onSubmit} className="mt-3 flex items-center gap-2">
            <input
              className="input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Matt, what should we do next?"
              aria-label="Command"
            />
            <button type="submit" className="btn" aria-label="Send command" disabled={!text.trim()}>
              <Send className="h-4 w-4" aria-hidden />
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}
