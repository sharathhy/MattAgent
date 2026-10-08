import { request } from "./client";

export interface TradingAccountView {
  mode: "paper" | "live";
  enabled: boolean;
  kill_switch: boolean;
  halted_reason: string | null;
  blocked: string | null;
  starting_capital: number;
  cash: number;
  equity: number;
  realized_pnl: number;
  fees_paid: number;
  day_pnl: number;
  total_return_pct: number;
  peak_equity: number;
  goal_inr: number;
  doublings_to_goal: number | null;
  max_trade_risk_pct: number;
  max_day_loss_pct: number;
  max_open_positions: number;
  live_capital_cap_inr: number;
  live_confirmed_at: string | null;
  last_tick_at: string | null;
  nse_open: boolean;
}

export interface TradeView {
  id: number;
  mode: string;
  symbol: string;
  market: string;
  side: "long" | "short";
  qty: number;
  entry_price: number;
  stop_price: number;
  target_price: number;
  last_price: number;
  exit_price: number | null;
  status: string;
  exit_reason: string | null;
  pnl: number;
  fees: number;
  unrealized: number | null;
  strategy: string | null;
  opened_at: string;
  closed_at: string | null;
}

export interface TradeStats {
  trades: number;
  wins: number;
  losses: number;
  win_rate: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  expectancy: number | null;
}

export interface TradingBotView {
  slug: string;
  name: string;
  role: string;
  symbol: string | null;
  strategy: string | null;
  generation: number;
  runs: number;
  trades: number;
  wins: number;
  losses: number;
  pnl: number;
  fitness: number;
  last_run_at: string | null;
  last_note: string | null;
  avoid: string[];
  backtest: { trades: number; win_rate: number; return_pct: number } | null;
}

export interface Insight {
  id: number;
  symbol: string | null;
  title: string;
  url: string | null;
  sentiment: number | null;
  content: string | null;
  created_at: string;
}

export interface MarketRow {
  symbol: string;
  market: string;
  price: number;
  change_pct: number;
  trend: string | null;
  rsi: number | null;
  above_vwap: boolean;
  patterns: string[];
  updated_at: string;
}

export interface TradingOverview {
  account: TradingAccountView;
  curve: { t: number; equity: number }[];
  positions: TradeView[];
  trades: TradeView[];
  stats: { paper: TradeStats; live: TradeStats };
  roles: { role: string; bots: number; active_15m: number }[];
  top_strategists: TradingBotView[];
  traders: TradingBotView[];
  market: MarketRow[];
  news: Insight[];
  research: Insight[];
  lessons: Insight[];
  strategies: { name: string; about: string; params: string[] }[];
  live_phrase: string;
  broker_needs: string[];
}

export interface BrokerView {
  id: number;
  broker: string;
  label: string;
  client_id: string;
  status: "connected" | "needs_login";
  funds_inr: number | null;
  last_error: string | null;
}

const post = <T>(path: string, body: unknown = {}) => request<T>(path, { method: "POST", body: JSON.stringify(body) });

export const tradingApi = {
  overview: () => request<TradingOverview>("/trading"),
  bots: (role?: string) => request<TradingBotView[]>(`/trading/bots${role ? `?role=${role}` : ""}`),
  updateSettings: (body: Partial<TradingAccountView>) =>
    request<TradingAccountView>("/trading/settings", { method: "PATCH", body: JSON.stringify(body) }),
  stop: () => post<TradingAccountView>("/trading/stop"),
  resume: () => post<TradingAccountView>("/trading/resume"),
  resetPaper: () => post<TradingAccountView>("/trading/paper/reset"),
  goLive: (confirm: string, capital_cap_inr: number) => post<TradingAccountView>("/trading/live", { confirm, capital_cap_inr }),
  goPaper: () => post<TradingAccountView>("/trading/paper"),
  brokers: () => request<{ brokers: BrokerView[]; needs: string[] }>("/trading/brokers"),
  addBroker: (body: { label: string; client_id: string; api_key: string; api_secret: string }) =>
    post<BrokerView>("/trading/brokers", body),
  loginUrl: (id: number) => request<{ url: string }>(`/trading/brokers/${id}/login`),
  completeLogin: (id: number, request_token: string) => post<BrokerView>(`/trading/brokers/${id}/login`, { request_token }),
  removeBroker: (id: number) => request<null>(`/trading/brokers/${id}`, { method: "DELETE" }),
};
