// IBKR Types
export interface Trade {
  tradeID: string;
  accountId: string;
  underlyingSymbol: string;
  symbol: string;
  description: string;
  expiry: string | null;
  putCall: string | null;
  strike: number | null;
  dateTime: string;
  quantity: number;
  tradePrice: number;
  multiplier: number;
  ibCommission: number;
  currency: string;
  notes: string | null;
  openCloseIndicator: string | null;
  delta: number | null;
  und_price: number | null;
  // Calculated fields
  contractKey?: string | null;
  realized_pnl?: number;
  remaining_qty?: number;
  credit?: number;
  quote_source?: string | null;
  quote_status?: string | null;
  mtm_price?: number | null;
  mtm_value?: number | null;
  unrealized_pnl?: number | null;
  // Opening premium of the lots closed by this (closing) trade
  closed_open_premium?: number;
}

export interface Position {
  symbol: string;
  underlyingSymbol: string;
  value: number;
  mtm: number;
  mtmPercent: number;
  targetPercent: number;
  unrealizedPnl: number;
  stockValue: number;
  stockMtm: number;
  callMtm: number;
  putMtm: number;
  stockUnrealizedPnl: number;
  callUnrealizedPnl: number;
  putUnrealizedPnl: number;
  stockQty: number;
  callQty: number;
  putQty: number;
  stockPnl: number;
  callPnl: number;
  putPnl: number;
  bookPrice: number;
}

export interface PositionDetail {
  tradeID: string;
  dateTime: string;
  description: string;
  putCall: string | null;
  quantity: number;
  price: number;
  commission: number;
  openClose: string | null;
  realizedPnl: number;
  remainingQty: number;
  credit: number;
  delta: number | null;
  undPrice: number | null;
}

export interface MarketPrice {
  symbol: string;
  price: number;
  date_time: string;
}

export interface MarketQuote {
  contract_key: string;
  instrument_type: "equity" | "option";
  source: "ibkr" | "yahoo_fallback";
  symbol: string;
  underlying_symbol: string | null;
  expiry: string | null;
  put_call: string | null;
  strike: number | null;
  multiplier: number | null;
  conid: string | null;
  bid: number | null;
  ask: number | null;
  last: number | null;
  close: number | null;
  mark: number | null;
  status: string;
  quote_time: string | null;
  raw_payload?: unknown;
  updated_at: string;
}

export interface SymbolTarget {
  id: number;
  symbol: string;
  target_percent: number;
  basket: string | null;
}

export interface DailyStat {
  date: string;
  dayName: string;
  realizedPnl: number;
}

export interface WeeklyStat {
  weekEnding: string;
  realizedPnl: number;
}

// FBN Types
export interface FBNEntry {
  id?: number;
  date: string;
  account: string;
  portfolio: string;
  currency: string;
  investment: number;
  deposit: number;
  interest: number;
  dividend: number;
  distribution: number;
  tax: number;
  fee: number;
  other: number;
  cash: number;
  asset: number;
  rate: number;
}

export interface FBNMonthlyStat {
  date: string;
  deposit: number;
  asset: number;
  fee: number;
  pnl: number;
  pct: number;
}

export interface FBNYearlyStat {
  year: number;
  deposit: number;
  asset: number;
  fee: number;
  pnl: number;
  pct: number;
}

export interface FBNAccount {
  name: string;
  portfolio: string;
  currency: string;
}

// Equity Types
export interface EquityEntry {
  id?: number;
  date: string;
  description: string;
  account: string;
  category: string;
  currency: string;
  rate: number;
  balance: number;
  tax: number;
  // Calculated
  balance_cad?: number;
  balance_net?: number;
}

export interface EquitySummary {
  name: string;
  balanceCad: number;
  balanceNet: number;
}

// Bitcoin Types
export interface BitcoinBuy {
  id?: number;
  exchange: string;
  date: string;
  date_on_chain: string | null;
  quantity: number;
  cost_cad: number;
  account: string;
  fees_cad: number | null;
  fees_sats: number | null;
  notes: string | null;
  // Calculated
  sats?: number;
  buy_price?: number;
}

export interface BitcoinSummary {
  name: string;
  buys: number;
  quantity: number;
  cost: number;
  avgCost: number;
}

// Auth Types
export interface User {
  id: string;
  email: string;
}

// App State Types
export interface AppError {
  message: string;
  timestamp: number;
}

// FBN fixed accounts
export const FBN_ACCOUNTS: FBNAccount[] = [
  { name: "MARGE", portfolio: "Personnel", currency: "CAD" },
  { name: "REER", portfolio: "Personnel", currency: "CAD" },
  { name: "CRI", portfolio: "Personnel", currency: "CAD" },
  { name: "REEE", portfolio: "Personnel", currency: "CAD" },
  { name: "CELI", portfolio: "Personnel", currency: "CAD" },
  { name: "MM MARGE", portfolio: "Personnel", currency: "CAD" },
  { name: "MM CELI", portfolio: "Personnel", currency: "CAD" },
  { name: "GFZ CAD", portfolio: "Gestion FZ", currency: "CAD" },
  { name: "GFZ USD", portfolio: "Gestion FZ", currency: "USD" },
];

// Equity categories
export const EQUITY_CATEGORIES = [
  "Bitcoin",
  "Cash",
  "Immobilier",
  "FBN",
  "IBKR",
  "BZ",
] as const;

export const EQUITY_ACCOUNTS = ["Personnel", "Gestion FZ"] as const;

export const CURRENCIES = ["CAD", "USD", "SAT"] as const;

// Bitcoin
export const BITCOIN_ACCOUNTS = ["FZ", "MPM", "GFZ"] as const;

export const BITCOIN_EXCHANGES = [
  "Coinbase",
  "Bitcoin Well",
  "Bull Bitcoin",
  "Crypto.com",
] as const;
