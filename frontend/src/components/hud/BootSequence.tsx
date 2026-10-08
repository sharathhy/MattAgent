import { useEffect, useState } from "react";

const LINES = [
  "MATT CORE v2 // AUTONOMOUS COMPANY OS",
  "Linking neural mesh ............ OK",
  "Loading agent workforce ........ OK",
  "Connecting revenue ledger ...... OK",
  "Calibrating voice interface .... OK",
  "All systems online. Say “Hey Matt”.",
];
const KEY = "matt.booted";

const alreadyBooted = () => {
  try {
    return sessionStorage.getItem(KEY) === "1" || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return true;
  }
};

/** The JARVIS-style boot sequence, once per browser session. Tap to skip. */
export function BootSequence() {
  const [shown, setShown] = useState(() => (alreadyBooted() ? -1 : 0));

  useEffect(() => {
    if (shown < 0) return;
    const t = setTimeout(
      () => {
        if (shown >= LINES.length) {
          try {
            sessionStorage.setItem(KEY, "1");
          } catch {
            /* nothing to remember in private mode */
          }
          setShown(-1);
        } else setShown(shown + 1);
      },
      shown >= LINES.length ? 700 : 330,
    );
    return () => clearTimeout(t);
  }, [shown]);

  if (shown < 0) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#02060c]/95 backdrop-blur"
      onClick={() => setShown(LINES.length)}
      role="presentation"
    >
      <div className="w-[min(560px,90vw)]">
        <div className="relative mx-auto mb-8 h-28 w-28">
          <div className="absolute inset-0 animate-spin rounded-full border-2 border-accent/20 border-t-accent [animation-duration:1.2s]" />
          <div className="absolute inset-3 animate-spin rounded-full border-2 border-hot/20 border-b-hot [animation-direction:reverse] [animation-duration:1.8s]" />
          <div className="absolute inset-8 rounded-full bg-accent/30 shadow-[0_0_40px_rgb(34_211_238/0.8)]" />
        </div>
        <ol className="space-y-1 font-mono text-sm text-cyan-200">
          {LINES.slice(0, shown).map((l, i) => (
            <li key={l} className={`rise ${i === shown - 1 ? "caret" : ""}`}>
              <span className="text-accent/60">&gt; </span>
              {l}
            </li>
          ))}
        </ol>
        <div className="mt-6 h-1 overflow-hidden rounded bg-slate-800">
          <div
            className="h-full bg-gradient-to-r from-accent to-hot transition-[width] duration-300"
            style={{ width: `${(Math.min(shown, LINES.length) / LINES.length) * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}
