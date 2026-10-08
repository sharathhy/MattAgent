/**
 * Microphone analyser: a live loudness level for the brain animation, and a short rolling
 * buffer of voiced spectra for the optional voice lock. Runs alongside speech recognition.
 */

export const BANDS = 24;
const MIN_HZ = 85;
const MAX_HZ = 4000;
/** Frames below this RMS are treated as silence and kept out of voice profiles. */
const VOICED_RMS = 0.025;

export interface MicMonitor {
  /** Smoothed loudness, 0..1. */
  level(): number;
  /** Mean voiced spectrum over the last `ms` milliseconds, or null if too little speech. */
  recentProfile(ms: number): number[] | null;
  /** Browsers start audio suspended until a tap. */
  resume(): void;
  stop(): void;
}

/** Log-spaced band edges between MIN_HZ and MAX_HZ, as FFT bin indices. */
function bandEdges(sampleRate: number, binCount: number): number[] {
  const hzPerBin = sampleRate / 2 / binCount;
  const edges: number[] = [];
  for (let i = 0; i <= BANDS; i++) {
    const hz = MIN_HZ * Math.pow(MAX_HZ / MIN_HZ, i / BANDS);
    edges.push(Math.max(1, Math.min(binCount - 1, Math.round(hz / hzPerBin))));
  }
  return edges;
}

/** Collapse a dB spectrum into BANDS mean-removed band energies (a crude timbre fingerprint). */
export function bandProfile(db: Float32Array, edges: number[]): number[] {
  const out: number[] = [];
  for (let b = 0; b < BANDS; b++) {
    const lo = edges[b] ?? 0;
    const hi = Math.max(lo + 1, edges[b + 1] ?? lo + 1);
    let sum = 0;
    for (let i = lo; i < hi; i++) sum += db[i] ?? -100;
    out.push(sum / (hi - lo));
  }
  const mean = out.reduce((a, v) => a + v, 0) / out.length;
  return out.map((v) => v - mean);
}

export function averageProfiles(profiles: number[][]): number[] | null {
  if (!profiles.length) return null;
  const acc = new Array<number>(BANDS).fill(0);
  for (const p of profiles) p.forEach((v, i) => (acc[i] = (acc[i] ?? 0) + v));
  return acc.map((v) => v / profiles.length);
}

export async function startMic(): Promise<MicMonitor> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });
  const ctx = new AudioContext();
  const src = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  analyser.smoothingTimeConstant = 0.6;
  src.connect(analyser);

  const time = new Float32Array(analyser.fftSize);
  const freq = new Float32Array(analyser.frequencyBinCount);
  const edges = bandEdges(ctx.sampleRate, analyser.frequencyBinCount);
  const history: { t: number; p: number[] }[] = [];
  let level = 0;
  let stopped = false;

  const tick = () => {
    if (stopped) return;
    analyser.getFloatTimeDomainData(time);
    let sq = 0;
    for (const v of time) sq += v * v;
    const rms = Math.sqrt(sq / time.length);
    level = level * 0.7 + Math.min(1, rms * 8) * 0.3;
    if (rms > VOICED_RMS) {
      analyser.getFloatFrequencyData(freq);
      const now = performance.now();
      history.push({ t: now, p: bandProfile(freq, edges) });
      while (history.length && (history[0]?.t ?? now) < now - 10_000) history.shift();
    }
  };
  const timer = setInterval(tick, 30);
  if (ctx.state === "suspended") void ctx.resume().catch(() => {});

  return {
    level: () => level,
    recentProfile(ms) {
      const since = performance.now() - ms;
      const frames = history.filter((h) => h.t >= since).map((h) => h.p);
      return frames.length >= 8 ? averageProfiles(frames) : null;
    },
    resume() {
      if (ctx.state === "suspended") void ctx.resume().catch(() => {});
    },
    stop() {
      stopped = true;
      clearInterval(timer);
      stream.getTracks().forEach((tr) => tr.stop());
      void ctx.close().catch(() => {});
    },
  };
}
