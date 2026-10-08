import { Fingerprint } from "lucide-react";
import { useState } from "react";

import { useAuth } from "../lib/auth";
import { useVoice } from "../voice/VoiceProvider";
import { clearVoiceprint, saveVoiceprint, setVoiceLock } from "../voice/voiceprint";
import { Panel } from "./ui";

const SAMPLES = 3;
const SAMPLE_MS = 3000;
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Owner-only enrollment of the optional voice lock. */
export function VoiceLockPanel() {
  const { user } = useAuth();
  const voice = useVoice();
  const [step, setStep] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!user || user.role !== "owner" || !voice.recognitionSupported) return null;
  const vp = voice.voiceprint;

  const enroll = async () => {
    setError(null);
    voice.setEnrolling(true);
    try {
      const mic = await voice.getMic();
      const samples: number[][] = [];
      for (let i = 0; i < SAMPLES; i++) {
        setStep(i + 1);
        await wait(SAMPLE_MS);
        const p = mic.recentProfile(SAMPLE_MS);
        if (p) samples.push(p);
      }
      if (samples.length < 2) {
        setError("I couldn't hear enough speech. Try again a little closer to the mic.");
        return;
      }
      saveVoiceprint(user.email, samples);
      voice.refreshVoiceprint();
    } catch {
      setError("The microphone isn't available.");
    } finally {
      voice.setEnrolling(false);
      setStep(null);
    }
  };

  return (
    <Panel title="Voice lock">
      <div className="flex flex-wrap items-start gap-4">
        <Fingerprint className="h-8 w-8 shrink-0 text-accent" aria-hidden />
        <div className="min-w-0 flex-1 text-sm">
          <p className="text-slate-300">
            {vp
              ? `Your voice is enrolled (${vp.samples} samples). MATT ${vp.enabled ? "ignores voices that don't match it" : "currently accepts any voice"}.`
              : "Enroll your voice so MATT only answers you. Only the owner can enroll."}
          </p>
          <p className="mt-1 text-xs text-muted">
            A convenience filter, not security: your Google sign-in is what protects MATT. The fingerprint stays in this
            browser and a similar voice or a recording can pass it.
          </p>
          {step !== null && (
            <p role="status" className="mt-2 animate-pulse font-mono text-sm text-accent">
              Sample {step} of {SAMPLES}: say “Hey Matt, what's the status?”
            </p>
          )}
          {error && <p className="mt-2 text-sm text-danger">{error}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn" onClick={() => void enroll()} disabled={step !== null}>
            {vp ? "Re-enroll" : "Enroll my voice"}
          </button>
          {vp && (
            <>
              <button
                type="button"
                className="rounded-lg border border-line px-3 py-2 text-sm hover:border-accent"
                onClick={() => {
                  setVoiceLock(user.email, !vp.enabled);
                  voice.refreshVoiceprint();
                }}
              >
                {vp.enabled ? "Turn lock off" : "Turn lock on"}
              </button>
              <button
                type="button"
                className="rounded-lg border border-line px-3 py-2 text-sm text-muted hover:text-danger"
                onClick={() => {
                  clearVoiceprint(user.email);
                  voice.refreshVoiceprint();
                }}
              >
                Delete
              </button>
            </>
          )}
        </div>
      </div>
    </Panel>
  );
}
