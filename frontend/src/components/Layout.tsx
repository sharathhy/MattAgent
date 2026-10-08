import { Activity, LogOut } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../lib/auth";
import { NAV } from "../lib/navigation";
import { VoiceProvider } from "../voice/VoiceProvider";
import { BrainOrb } from "./BrainOrb";

export function Layout() {
  return (
    <VoiceProvider>
      <Shell />
    </VoiceProvider>
  );
}

function Shell() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-[#030b14]/80 p-4 backdrop-blur md:flex">
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <span className="relative flex h-7 w-7 items-center justify-center">
            <span className="absolute inset-0 animate-spin rounded-full border border-accent/30 border-t-accent [animation-duration:3s]" />
            <Activity className="h-3.5 w-3.5 text-accent" aria-hidden />
          </span>
          <span className="hud-title text-lg font-bold">MATT</span>
        </div>
        <nav aria-label="Main" className="flex-1 space-y-0.5 overflow-y-auto">
          {NAV.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center justify-between border-l-2 px-3 py-1.5 text-[15px] font-medium tracking-wide transition ${
                  isActive
                    ? "border-accent bg-gradient-to-r from-accent/15 to-transparent text-accent"
                    : "border-transparent text-slate-300 hover:border-accent/40 hover:bg-white/5 hover:text-cyan-100"
                }`
              }
            >
              <span>{item.label}</span>
              {item.phase && <span className="font-mono text-[10px] text-muted">P{item.phase}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="mt-4 border-t border-line pt-3 text-xs text-muted">
          <div className="truncate">{user?.email}</div>
          <div className="mt-1 flex items-center justify-between">
            <span className="font-mono uppercase tracking-wider">{user?.role}</span>
            <button type="button" onClick={logout} className="flex items-center gap-1 hover:text-slate-200">
              <LogOut className="h-3.5 w-3.5" aria-hidden /> Sign out
            </button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-8">
        <nav aria-label="Main mobile" className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 pb-2 md:hidden">
          {NAV.filter((i) => !i.phase).map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `shrink-0 rounded-full border border-line px-3 py-1 text-xs ${isActive ? "text-accent" : "text-slate-300"}`
              }
            >
              {item.label}
            </NavLink>
          ))}
          <button type="button" onClick={logout} className="shrink-0 px-3 py-1 text-xs text-muted">
            Sign out
          </button>
        </nav>
        <Outlet />
      </main>
      {pathname !== "/command-center" && <BrainOrb />}
    </div>
  );
}
