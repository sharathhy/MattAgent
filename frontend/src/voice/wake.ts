/**
 * Wake-phrase detection on recogniser transcripts. Recognisers often mishear "Matt"
 * ("mat", "mad", "math", "max"), so a small set of near-misses is accepted.
 */
const GREETING = "(?:hey|hay|hi|hello|ok|okay|a|yo)";
const NAME = "(?:matt|mat|matte|mad|math|mass|max|met|maat|mutt|mac|mart)";
/** "Hey Matt" anywhere, or just "Matt, …" at the start, the way people talk to Alexa. */
const WAKE = new RegExp(`(?:\\b${GREETING}[\\s,.!]+${NAME}\\b|^\\s*(?:matt|mat)\\b)[\\s,.!?]*`, "i");

export interface WakeMatch {
  /** Whatever was said after the wake phrase, e.g. "show me the agents". */
  rest: string;
}

export function detectWake(transcript: string): WakeMatch | null {
  const m = WAKE.exec(transcript);
  if (!m) return null;
  return { rest: transcript.slice(m.index + m[0].length).trim() };
}
