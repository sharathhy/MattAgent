import { useEffect, useState } from "react";

export function HudClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const hh = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const ss = String(now.getSeconds()).padStart(2, "0");
  return (
    <div className="text-right">
      <div className="hud-num glow text-3xl text-cyan-100 md:text-4xl">
        {hh}
        <span className="text-lg text-accent/70">:{ss}</span>
      </div>
      <div className="label mt-0.5">
        {now.toLocaleDateString([], { weekday: "long", day: "numeric", month: "short", year: "numeric" })}
      </div>
    </div>
  );
}
