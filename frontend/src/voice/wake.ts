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

const STOP_WORDS =
  "(?:stop(?:\\s+(?:it|that|talking|speaking))?|be quiet|quiet|shut up|cancel(?:\\s+(?:it|that))?|enough|that's enough|never ?mind|hush|silence|hold on)";
/** "stop", "Matt stop", "hey Matt, be quiet", "cancel that please". */
const STOP = new RegExp(
  `(?:^|\\b(?:${GREETING}[\\s,.!]+)?${NAME}[\\s,.!]+|^\\s*(?:ok|okay|no)[\\s,.!]+)(?:please\\s+)?${STOP_WORDS}(?:[\\s,]+(?:now|please|matt))*[\\s.!?]*$`,
  "i",
);
const STOP_ALONE = new RegExp(`^\\s*(?:please\\s+)?${STOP_WORDS}(?:[\\s,]+(?:now|please|matt))*[\\s.!?]*$`, "i");

/**
 * Is this a request to stop? `trailing` also accepts a stop phrase at the end of a longer
 * transcript, which is how barge-in arrives: the recogniser glues it onto MATT's own echo.
 */
export function isStopPhrase(transcript: string, trailing = false): boolean {
  const t = transcript.trim();
  if (STOP_ALONE.test(t) || STOP.test(t)) return true;
  if (!trailing) return false;
  const words = t.split(/\s+/);
  for (let n = 1; n <= Math.min(5, words.length); n++) {
    const tail = words.slice(-n).join(" ");
    if (STOP_ALONE.test(tail) || STOP.test(tail)) return true;
  }
  return false;
}
