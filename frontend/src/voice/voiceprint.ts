/**
 * Optional "voice lock": a convenience filter on top of Google sign-in, never authentication.
 * The enrolled profile is an averaged spectral fingerprint stored only in this browser, and the
 * match is deliberately loose. A recording of the owner, or a similar voice, can pass it.
 */
import { averageProfiles } from "./mic";

const KEY = (email: string) => `matt.voiceprint.${email.toLowerCase()}`;
export const MATCH_THRESHOLD = 0.82;

export interface Voiceprint {
  profile: number[];
  samples: number;
  enrolled_at: string;
  enabled: boolean;
}

export function loadVoiceprint(email: string): Voiceprint | null {
  try {
    const raw = localStorage.getItem(KEY(email));
    return raw ? (JSON.parse(raw) as Voiceprint) : null;
  } catch {
    return null;
  }
}

export function saveVoiceprint(email: string, samples: number[][]): Voiceprint | null {
  const profile = averageProfiles(samples);
  if (!profile) return null;
  const vp: Voiceprint = { profile, samples: samples.length, enrolled_at: new Date().toISOString(), enabled: true };
  localStorage.setItem(KEY(email), JSON.stringify(vp));
  return vp;
}

export function setVoiceLock(email: string, enabled: boolean): Voiceprint | null {
  const vp = loadVoiceprint(email);
  if (!vp) return null;
  const next = { ...vp, enabled };
  localStorage.setItem(KEY(email), JSON.stringify(next));
  return next;
}

export function clearVoiceprint(email: string) {
  localStorage.removeItem(KEY(email));
}

export function similarity(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    const x = a[i] ?? 0;
    const y = b[i] ?? 0;
    dot += x * y;
    na += x * x;
    nb += y * y;
  }
  return na && nb ? dot / Math.sqrt(na * nb) : 0;
}

/** True when there is no active lock, or when the sample is close enough to the enrolled voice. */
export function voiceAccepted(vp: Voiceprint | null, sample: number[] | null): boolean {
  if (!vp?.enabled) return true;
  if (!sample) return false;
  return similarity(vp.profile, sample) >= MATCH_THRESHOLD;
}
