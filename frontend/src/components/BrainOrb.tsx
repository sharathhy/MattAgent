import { useNavigate } from "react-router-dom";

import { STATE_LABEL, useVoice } from "../voice/VoiceProvider";
import { Brain } from "./Brain";

/** A small floating brain on every other page, so MATT stays visibly awake while you browse. */
export function BrainOrb() {
  const voice = useVoice();
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate("/command-center")}
      className="panel fixed right-4 bottom-4 z-40 flex items-center gap-2 rounded-full py-1 pr-4 pl-1 shadow-[0_0_30px_rgb(34_211_238/0.25)]"
      aria-label={`MATT: ${STATE_LABEL[voice.state]}. Open command center`}
    >
      <Brain state={voice.state} signals={voice.signals} size={64} compact />
      <span className="hidden max-w-48 text-left text-xs text-slate-300 sm:block">
        {voice.interim ? `“${voice.interim}”` : STATE_LABEL[voice.state]}
      </span>
    </button>
  );
}
