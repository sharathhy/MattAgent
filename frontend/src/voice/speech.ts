/**
 * Thin, typed wrappers over the browser's free, built-in speech APIs.
 * Recognition is Chrome/Edge/Safari only (`webkitSpeechRecognition`); synthesis works everywhere.
 */

export interface RecognitionAlternative {
  transcript: string;
  confidence: number;
}
export interface RecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  [index: number]: RecognitionAlternative;
}
export interface RecognitionEvent {
  readonly resultIndex: number;
  readonly results: { readonly length: number; [index: number]: RecognitionResult };
}
export interface RecognitionErrorEvent {
  readonly error: string;
}
export interface Recognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onresult: ((e: RecognitionEvent) => void) | null;
  onerror: ((e: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

export function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export const synthesisSupported = () => typeof window !== "undefined" && "speechSynthesis" in window;

function pickVoice(): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis.getVoices();
  const en = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  const preferred = ["Google UK English Male", "Daniel", "Microsoft Ryan", "Microsoft Guy", "Google US English", "Alex"];
  for (const name of preferred) {
    const v = en.find((x) => x.name.includes(name));
    if (v) return v;
  }
  return en[0];
}

/**
 * Speak `text`. `onWord` fires on each word boundary so the brain can pulse in time.
 * Resolves when speech ends, or immediately if the browser blocks or lacks synthesis.
 */
let cutOff: (() => void) | null = null;

export function speak(text: string, onWord?: () => void): Promise<"spoken" | "blocked"> {
  if (!synthesisSupported()) return Promise.resolve("blocked");
  return new Promise((resolve) => {
    const synth = window.speechSynthesis;
    synth.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const voice = pickVoice();
    if (voice) u.voice = voice;
    u.rate = 1.03;
    u.pitch = 0.9;
    let done = false;
    const finish = (r: "spoken" | "blocked") => {
      if (done) return;
      done = true;
      cutOff = null;
      clearTimeout(guard);
      resolve(r);
    };
    // Some engines never fire `end`; never let the assistant hang on that.
    const guard = setTimeout(() => finish("spoken"), 1500 + text.length * 90);
    cutOff = () => finish("spoken");
    u.onboundary = () => onWord?.();
    u.onend = () => finish("spoken");
    u.onerror = (e) => finish(e.error === "not-allowed" ? "blocked" : "spoken");
    synth.speak(u);
  });
}

/** Cut MATT off mid-sentence. Some engines never fire `end` after cancel, so settle `speak` here too. */
export function stopSpeaking() {
  if (synthesisSupported()) window.speechSynthesis.cancel();
  cutOff?.();
}
