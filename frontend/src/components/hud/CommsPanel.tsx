import { ExternalLink, Mic, MicOff, Send, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { useVoice } from "../../voice/VoiceProvider";

/** The conversation with MATT, plus a typed command line that works in every browser. */
export function CommsPanel() {
  const voice = useVoice();
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [voice.log.length]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    voice.submit(text);
    setText("");
  };
  const listening = !["off", "unsupported", "error", "blocked"].includes(voice.state);

  return (
    <section aria-label="Conversation" className="panel flex min-h-[340px] flex-col p-4">
      <h2 className="label mb-3 flex items-center gap-1.5">
        <Sparkles className="h-3.5 w-3.5 text-accent" aria-hidden /> Comms
      </h2>
      <div className="flex-1 space-y-2 overflow-y-auto pr-1 lg:max-h-[420px]" aria-label="Conversation log">
        {voice.log.length === 0 && (
          <div className="rounded-md border border-dashed border-line p-3 text-sm text-muted">
            Talk to MATT like Alexa. Say <span className="text-accent">“Hey Matt”</span>, then for example:
            <ul className="mt-2 space-y-1 text-slate-300">
              <li>“Find gyms in Bangalore that need a website”</li>
              <li>“Audit example.com”</li>
              <li>“Brief me” · “How much did we earn today?”</li>
              <li>“Set a timer for 10 minutes” · “Play lo-fi on YouTube”</li>
              <li>“What should we build next?”</li>
            </ul>
          </div>
        )}
        {voice.log.map((entry) => (
          <div
            key={entry.id}
            className={`rise max-w-[92%] rounded-md px-3 py-2 text-[15px] leading-snug ${
              entry.who === "you"
                ? "ml-auto border border-accent/30 bg-accent/10 text-cyan-100"
                : entry.who === "matt"
                  ? "border-l-2 border-accent bg-slate-900/70 text-slate-100"
                  : "mx-auto text-center text-xs text-muted"
            }`}
          >
            {entry.who === "matt" && <span className="hud-title mr-1.5 text-[10px]">MATT</span>}
            <span className="whitespace-pre-line">{entry.text}</span>
            {entry.link && (
              <a
                href={entry.link.url}
                target="_blank"
                rel="noreferrer"
                className="mt-1.5 flex items-center gap-1 text-sm text-accent hover:underline"
              >
                <ExternalLink className="h-3.5 w-3.5" aria-hidden /> {entry.link.label}
              </a>
            )}
          </div>
        ))}
        <div ref={end} />
      </div>
      <form onSubmit={onSubmit} className="mt-3 flex items-center gap-2">
        {voice.recognitionSupported && (
          <button
            type="button"
            className={`btn shrink-0 px-2.5 ${listening ? "" : "border-slate-600 text-slate-400"}`}
            onClick={() => voice.setEnabled(!listening)}
            aria-label={listening ? "Mute microphone" : "Turn microphone on"}
            title={listening ? "Mute microphone" : "Turn microphone on"}
          >
            {listening ? <Mic className="h-4 w-4" aria-hidden /> : <MicOff className="h-4 w-4" aria-hidden />}
          </button>
        )}
        <input
          className="input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Matt, what should we do next?"
          aria-label="Command"
        />
        <button type="submit" className="btn shrink-0 px-3" aria-label="Send command" disabled={!text.trim()}>
          <Send className="h-4 w-4" aria-hidden />
        </button>
      </form>
    </section>
  );
}
