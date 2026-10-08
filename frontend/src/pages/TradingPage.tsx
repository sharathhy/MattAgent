import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { tradingApi, type TradeView, type TradingAccountView, type TradingOverview } from "../api/trading";
import { ActionError, Badge, Empty, Field, PageHeader, Table, useAction, useCan } from "../components/kit";
import { ErrorState, Loading, Panel, Stat } from "../components/ui";

const KEY = ["trading"];
const rupees = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined ? "—" : `₹${v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
const signed = (v: number) => `${v >= 0 ? "+" : "−"}${rupees(Math.abs(v))}`;
const tone = (v: number | null | undefined) => (v === null || v === undefined || v === 0 ? "" : v > 0 ? "text-emerald-300" : "text-rose-300");
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
const ago = (iso: string | null) => {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  return s < 90 ? `${Math.round(s)}s ago` : s < 5400 ? `${Math.round(s / 60)}m ago` : `${Math.round(s / 3600)}h ago`;
};

export function TradingPage() {
  const data = useQuery({ queryKey: KEY, queryFn: tradingApi.overview, refetchInterval: 15_000 });
  const owner = useCan("owner");
  if (data.isPending) return <Loading label="Loading the trading desk" />;
  if (data.isError) return <ErrorState error={data.error} />;
  const d = data.data;
  const a = d.account;
  return (
    <div className="space-y-5">
      <PageHeader eyebrow="300-bot swarm" title="Trading desk">
        <Controls account={a} owner={owner} />
      </PageHeader>
      <Banner account={a} />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Stat label={a.mode === "live" ? "Real balance (capped)" : "Paper balance"} value={rupees(a.equity)} hint={`Started with ${rupees(a.starting_capital)}`} />
        <Stat label="Today" value={<span className={tone(a.day_pnl)}>{signed(a.day_pnl)}</span>} hint={`Fees paid ${rupees(a.fees_paid)}`} />
        <Stat label="Total return" value={<span className={tone(a.total_return_pct)}>{a.total_return_pct.toFixed(2)}%</span>} />
        <Stat label="Win rate" value={pct(d.stats[a.mode].win_rate)} hint={`${d.stats[a.mode].trades} closed trades`} />
        <Stat label="Open positions" value={`${d.positions.length}/${a.max_open_positions}`} hint={a.nse_open ? "NSE is open" : "NSE is closed; crypto only"} />
      </div>
      <Goal account={a} />
      <div className="grid gap-5 lg:grid-cols-3">
        <Panel title="Balance over time" className="lg:col-span-2">
          <Curve points={d.curve} />
        </Panel>
        <Swarm data={d} />
      </div>
      <Positions title="Open positions" trades={d.positions} open />
      <Positions title="Recent closed trades" trades={d.trades} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Market data={d} />
        <Strategists data={d} />
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Feed title="Lessons from losses" items={d.lessons} empty="No losing trades yet, so nothing to retrain on." />
        <Feed title="News bots" items={d.news} empty="News bots haven't found headlines yet." />
        <Feed title="Research bots" items={d.research} empty="Research bots haven't reported yet." />
      </div>
      {owner && <Limits account={a} />}
      {owner && <Demat data={d} />}
    </div>
  );
}

function Controls({ account: a, owner }: { account: TradingAccountView; owner: boolean }) {
  const stop = useAction(tradingApi.stop, [KEY]);
  const resume = useAction(tradingApi.resume, [KEY]);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge value={a.mode === "live" ? "live" : "paper"} />
      {a.kill_switch || !a.enabled ? (
        owner && (
          <button type="button" className="btn" onClick={() => resume.mutate(undefined)} disabled={resume.isPending}>
            Resume trading
          </button>
        )
      ) : (
        <button
          type="button"
          className="btn border-rose-400/60 bg-rose-500/15 text-rose-300 hover:bg-rose-500/30"
          onClick={() => stop.mutate(undefined)}
          disabled={stop.isPending}
        >
          Stop trading
        </button>
      )}
      <ActionError error={stop.error ?? resume.error} />
    </div>
  );
}

function Banner({ account: a }: { account: TradingAccountView }) {
  return (
    <div className="space-y-2">
      {a.blocked && (
        <p className="panel border-amber-400/40 p-3 text-sm text-amber-200">Trading is blocked: {a.blocked}.</p>
      )}
      <p className="text-sm text-muted">
        {a.mode === "paper"
          ? "Paper mode: the bots trade pretend money against live prices, with real Indian trading costs deducted. "
          : "Live mode: bots place real intraday orders in your Zerodha account, never above your capital cap. "}
        Intraday only (no futures or options). Each trade risks at most {a.max_trade_risk_pct}% of the balance, trading stops for the day
        after a {a.max_day_loss_pct}% loss, and everything is squared off before the close. Heartbeat {ago(a.last_tick_at)}.
      </p>
    </div>
  );
}

function Goal({ account: a }: { account: TradingAccountView }) {
  return (
    <p className="text-xs text-muted">
      Your goal is ₹100 crore. From {rupees(a.equity)} that means doubling the money about {a.doublings_to_goal ?? "—"} more times. No
      strategy can promise that, or a 90% win rate; the numbers above are what the bots have actually done.
    </p>
  );
}

function Curve({ points }: { points: { t: number; equity: number }[] }) {
  if (points.length < 2) return <p className="text-sm text-muted">The chart fills in as the swarm runs.</p>;
  const w = 600;
  const h = 160;
  const values = points.map((p) => p.equity);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const first = values[0] ?? 0;
  const last = values[values.length - 1] ?? 0;
  const t0 = points[0]?.t ?? 0;
  const tspan = (points[points.length - 1]?.t ?? t0) - t0 || 1;
  const path = points
    .map((p, i) => `${i ? "L" : "M"}${(((p.t - t0) / tspan) * w).toFixed(1)},${(h - ((p.equity - lo) / span) * (h - 10) - 5).toFixed(1)}`)
    .join(" ");
  const up = last >= first;
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-40 w-full" preserveAspectRatio="none" role="img" aria-label="Balance over time">
        <path d={path} fill="none" stroke={up ? "#34d399" : "#f87171"} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="mt-1 flex justify-between font-mono text-xs text-muted">
        <span>low {rupees(lo)}</span>
        <span>high {rupees(hi)}</span>
      </div>
    </div>
  );
}

const ROLE_ABOUT: Record<string, string> = {
  research: "study intraday methods",
  news: "score headlines per symbol",
  analyst: "read candles and indicators",
  strategist: "backtest and evolve strategies",
  trader: "combine signals and trade",
};

function Swarm({ data }: { data: TradingOverview }) {
  const total = data.roles.reduce((s, r) => s + r.bots, 0);
  return (
    <Panel title={`Bot swarm · ${total} bots`}>
      <ul className="space-y-2 text-sm">
        {data.roles.map((r) => (
          <li key={r.role} className="flex items-center justify-between gap-2">
            <span>
              <span className="font-semibold capitalize">{r.bots} {r.role}</span>{" "}
              <span className="text-xs text-muted">{ROLE_ABOUT[r.role]}</span>
            </span>
            <span className="font-mono text-xs text-muted">{r.active_15m} ran in 15m</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-muted">
        These are scheduled workers inside MATT's one free server, a few at a time, so each gets a turn every few minutes.
      </p>
    </Panel>
  );
}

function Positions({ title, trades, open = false }: { title: string; trades: TradeView[]; open?: boolean }) {
  if (!trades.length) return <Panel title={title}><p className="text-sm text-muted">{open ? "No open positions." : "No closed trades yet."}</p></Panel>;
  return (
    <div className="space-y-2">
      <h2 className="label">{title}</h2>
      <Table head={["Symbol", "Side", "Qty", "Entry", open ? "Now" : "Exit", "Stop / target", open ? "Unrealised" : "P&L after fees", open ? "Strategy" : "Why closed"]}>
        {trades.map((t) => (
          <tr key={t.id} className="border-b border-line/50">
            <td className="p-3 font-medium">{t.symbol} <span className="text-xs text-muted">{t.market}{t.mode === "live" ? " · real" : ""}</span></td>
            <td className="p-3"><Badge value={t.side} /></td>
            <td className="p-3 font-mono text-xs">{t.qty}</td>
            <td className="p-3 font-mono text-xs">{rupees(t.entry_price)}</td>
            <td className="p-3 font-mono text-xs">{rupees(open ? t.last_price : t.exit_price)}</td>
            <td className="p-3 font-mono text-xs">{rupees(t.stop_price)} / {rupees(t.target_price)}</td>
            <td className={`p-3 font-mono text-xs ${tone(open ? t.unrealized : t.pnl)}`}>{signed((open ? t.unrealized : t.pnl) ?? 0)}</td>
            <td className="p-3 text-xs">{open ? t.strategy?.replace(/_/g, " ") : t.exit_reason?.replace(/_/g, " ")}</td>
          </tr>
        ))}
      </Table>
    </div>
  );
}

function Market({ data }: { data: TradingOverview }) {
  return (
    <Panel title="Live market (5-minute candles)">
      {data.market.length === 0 ? (
        <p className="text-sm text-muted">Analyst bots are collecting the first candles.</p>
      ) : (
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-left text-sm">
            <tbody>
              {data.market.map((m) => (
                <tr key={m.symbol} className="border-b border-line/40">
                  <td className="py-2 font-medium">{m.symbol}</td>
                  <td className="py-2 font-mono text-xs">{rupees(m.price)}</td>
                  <td className={`py-2 font-mono text-xs ${tone(m.change_pct)}`}>{m.change_pct.toFixed(2)}%</td>
                  <td className="py-2 text-xs">{m.trend === "up" ? "uptrend" : "downtrend"}</td>
                  <td className="py-2 font-mono text-xs">RSI {m.rsi?.toFixed(0) ?? "—"}</td>
                  <td className="py-2 text-xs text-muted">{m.patterns.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function Strategists({ data }: { data: TradingOverview }) {
  return (
    <Panel title="Best strategists (backtested after costs)">
      {data.top_strategists.every((b) => !b.runs) ? (
        <p className="text-sm text-muted">Strategists start backtesting once candles arrive.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {data.top_strategists.map((b) => (
            <li key={b.slug} className="rounded-lg border border-line/50 p-2">
              <div className="flex justify-between gap-2">
                <span className="font-medium">{b.name}</span>
                <span className="font-mono text-xs text-muted">gen {b.generation}</span>
              </div>
              <div className="text-xs text-muted">{b.last_note}</div>
              {b.avoid.length > 0 && <div className="text-xs text-amber-300">Learned to avoid: {b.avoid.join("; ")}</div>}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Feed({ title, items, empty }: { title: string; items: TradingOverview["news"]; empty: string }) {
  return (
    <Panel title={title}>
      {items.length === 0 ? (
        <p className="text-sm text-muted">{empty}</p>
      ) : (
        <ul className="max-h-80 space-y-2 overflow-y-auto text-sm">
          {items.map((n) => (
            <li key={n.id}>
              {n.url ? (
                <a href={n.url} target="_blank" rel="noreferrer noopener" className="hover:text-accent">{n.title}</a>
              ) : (
                <span className="font-medium">{n.title}</span>
              )}
              <div className="text-xs text-muted">
                {n.symbol && `${n.symbol} · `}
                {n.sentiment !== null && <span className={tone(n.sentiment)}>mood {n.sentiment.toFixed(2)} · </span>}
                {ago(n.created_at)}
              </div>
              {n.content && <p className="mt-1 whitespace-pre-line text-xs text-slate-300">{n.content}</p>}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Limits({ account: a }: { account: TradingAccountView }) {
  const [form, setForm] = useState({ risk: a.max_trade_risk_pct, day: a.max_day_loss_pct, slots: a.max_open_positions });
  const save = useAction(
    () => tradingApi.updateSettings({ max_trade_risk_pct: form.risk, max_day_loss_pct: form.day, max_open_positions: form.slots }),
    [KEY],
  );
  const reset = useAction(tradingApi.resetPaper, [KEY]);
  return (
    <Panel title="Risk limits">
      <form
        className="grid gap-3 sm:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        <Field label="Max risk per trade (%)">
          <input className="input" type="number" min={0.1} max={20} step={0.1} value={form.risk} onChange={(e) => setForm({ ...form, risk: Number(e.target.value) })} />
        </Field>
        <Field label="Max loss per day (%)">
          <input className="input" type="number" min={0.1} max={20} step={0.1} value={form.day} onChange={(e) => setForm({ ...form, day: Number(e.target.value) })} />
        </Field>
        <Field label="Max open positions">
          <input className="input" type="number" min={1} max={10} value={form.slots} onChange={(e) => setForm({ ...form, slots: Number(e.target.value) })} />
        </Field>
        <div className="flex items-end gap-2">
          <button type="submit" className="btn" disabled={save.isPending}>Save</button>
          {a.mode === "paper" && (
            <button type="button" className="text-xs text-muted" onClick={() => reset.mutate(undefined)}>Reset paper to ₹100</button>
          )}
        </div>
      </form>
      <p className="mt-2 text-xs text-muted">Neither limit can go above 20%, whatever is typed here.</p>
      <ActionError error={save.error ?? reset.error} />
    </Panel>
  );
}

function Demat({ data }: { data: TradingOverview }) {
  const brokers = useQuery({ queryKey: ["brokers"], queryFn: tradingApi.brokers });
  const refresh = [KEY, ["brokers"]];
  const [form, setForm] = useState({ label: "Zerodha", client_id: "", api_key: "", api_secret: "" });
  const [live, setLive] = useState({ cap: "", phrase: "" });
  const add = useAction(() => tradingApi.addBroker(form), refresh);
  const remove = useAction((id: number) => tradingApi.removeBroker(id), refresh);
  const login = useAction(({ id, token }: { id: number; token: string }) => tradingApi.completeLogin(id, token), refresh);
  const goLive = useAction(() => tradingApi.goLive(live.phrase, Number(live.cap)), refresh);
  const goPaper = useAction(tradingApi.goPaper, refresh);
  const [params, setParams] = useSearchParams();
  const handled = useRef(false);
  const broker = brokers.data?.brokers[0];

  // Zerodha sends you back here with ?request_token=... after the daily login.
  useEffect(() => {
    const token = params.get("request_token");
    if (!token || !broker || handled.current) return;
    handled.current = true;
    login.mutate({ id: broker.id, token });
    setParams({}, { replace: true });
  }, [params, broker, login, setParams]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const a = data.account;
  return (
    <Panel title="Demat account">
      <p className="text-xs text-muted">
        Connect your own Zerodha account so the bots can trade it for real. Keys are encrypted, never shown again, and only you can
        see this section. MATT can only place and cancel intraday orders: it has no way to withdraw or transfer your money. Add funds to
        Zerodha yourself through their app.
      </p>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted">
        {data.broker_needs.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
      {brokers.isError && <ErrorState error={brokers.error} />}
      {broker ? (
        <div className="mt-4 space-y-3">
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-line/60 p-3 text-sm">
            <Badge value={broker.status === "connected" ? "active" : "pending"} />
            <span>{broker.label}</span>
            <span className="font-mono text-xs">{broker.client_id}</span>
            {broker.funds_inr !== null && <span className="text-xs text-muted">Available {rupees(broker.funds_inr)}</span>}
            <span className="flex-1" />
            {broker.status !== "connected" && (
              <button
                type="button"
                className="btn"
                onClick={() => tradingApi.loginUrl(broker.id).then((r) => window.location.assign(r.url))}
              >
                Log in to Zerodha for today
              </button>
            )}
            <button type="button" className="text-xs text-muted" onClick={() => remove.mutate(broker.id)}>Remove</button>
          </div>
          {broker.last_error && <p className="text-xs text-danger">{broker.last_error}</p>}
          {a.mode === "paper" ? (
            <form
              className="grid gap-3 rounded-lg border border-rose-400/30 p-3 sm:grid-cols-3"
              onSubmit={(e) => {
                e.preventDefault();
                goLive.mutate(undefined);
              }}
            >
              <p className="text-xs text-rose-200 sm:col-span-3">
                Switching to live trading means the bots trade your real money and can lose it. Paper results don't guarantee real ones.
              </p>
              <Field label="Most real money MATT may use (₹)">
                <input className="input" type="number" min={1} step={1} required value={live.cap} onChange={(e) => setLive({ ...live, cap: e.target.value })} />
              </Field>
              <Field label={`Type: ${data.live_phrase}`}>
                <input className="input" required value={live.phrase} onChange={(e) => setLive({ ...live, phrase: e.target.value })} />
              </Field>
              <div className="flex items-end">
                <button type="submit" className="btn border-rose-400/60 bg-rose-500/15 text-rose-300" disabled={goLive.isPending || broker.status !== "connected"}>
                  Switch to live trading
                </button>
              </div>
            </form>
          ) : (
            <div className="flex items-center gap-3 text-sm">
              <span>Live since {a.live_confirmed_at ? new Date(a.live_confirmed_at).toLocaleString() : "—"}, capped at {rupees(a.live_capital_cap_inr, 0)}.</span>
              <button type="button" className="btn" onClick={() => goPaper.mutate(undefined)}>Back to paper</button>
            </div>
          )}
        </div>
      ) : (
        <form
          className="mt-4 grid gap-3 sm:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate(undefined);
          }}
        >
          <Field label="Label">
            <input className="input" required value={form.label} onChange={set("label")} />
          </Field>
          <Field label="Zerodha client ID">
            <input className="input font-mono uppercase" required value={form.client_id} onChange={set("client_id")} placeholder="AB1234" />
          </Field>
          <Field label="Kite Connect API key">
            <input className="input font-mono" required autoComplete="off" value={form.api_key} onChange={set("api_key")} />
          </Field>
          <Field label="Kite Connect API secret">
            <input className="input font-mono" required type="password" autoComplete="off" value={form.api_secret} onChange={set("api_secret")} />
          </Field>
          <div className="sm:col-span-4">
            <button type="submit" className="btn" disabled={add.isPending}>Save broker</button>
          </div>
        </form>
      )}
      {!brokers.data && !brokers.isError && <Empty>Loading broker details…</Empty>}
      <ActionError error={add.error ?? remove.error ?? login.error ?? goLive.error ?? goPaper.error} />
    </Panel>
  );
}
