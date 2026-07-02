import { MarketQuote, Position, Trade } from "@/types";
import { isOptionTrade } from "./fifo";
import { parseAsNY } from "./format";

const EPSILON = 1e-9;

export interface SymbolMeta {
  symbol: string;
  target_percent: number | null;
  basket: string | null;
  score: number | null;
}

export interface OptionExposureRow {
  key: string;
  underlyingSymbol: string;
  expiry: string | null;
  putCall: "C" | "P" | null;
  strike: number | null;
  side: "short" | "long";
  contracts: number;
  absContracts: number;
  multiplier: number;
  notional: number;
  mtmValue: number;
  unrealizedPnl: number;
  premiumCredit: number;
  dte: number | null;
  quoteStatus: string;
}

export interface ExpiryRiskRow {
  expiry: string | null;
  dte: number | null;
  contractCount: number;
  contracts: number;
  shortPutContracts: number;
  shortCallContracts: number;
  shortPutNotional: number;
  shortCallNotional: number;
  totalNotional: number;
  mtmValue: number;
  unrealizedPnl: number;
}

export interface AssignmentEvent {
  date: string;
  month: string;
  underlyingSymbol: string;
  eventType: string;
  putCall: "C" | "P" | null;
  expiry: string | null;
  strike: number | null;
  contracts: number;
  stockQuantity: number;
  stockNotional: number;
  optionRealizedPnl: number;
  stockRealizedPnl: number;
}

export interface UnderlyingRiskRow extends Position {
  basket: string | null;
  score: number | null;
  realizedPnl: number;
  fullBookPnl: number;
  driftPercent: number;
  shortPutNotional: number;
  shortCallNotional: number;
  longOptionNotional: number;
  optionNotional: number;
  optionMtm: number;
  optionUnrealizedPnl: number;
  frontExpiryNotional: number;
  openOptionContracts: number;
  riskNotional: number;
  riskFlags: string[];
}

export interface RiskDashboardData {
  asOf: string | null;
  latestQuoteAt: string | null;
  positionRows: UnderlyingRiskRow[];
  optionExposures: OptionExposureRow[];
  expiryRows: ExpiryRiskRow[];
  assignmentEvents: AssignmentEvent[];
  totals: {
    totalMtm: number;
    totalRealizedPnl: number;
    totalUnrealizedPnl: number;
    totalBookPnl: number;
    positionCount: number;
    optionContractCount: number;
    totalOptionNotional: number;
    shortPutNotional: number;
    shortCallNotional: number;
    shortPutContracts: number;
    shortCallContracts: number;
    optionUnrealizedPnl: number;
    frontExpiryNotional: number;
    topFiveMtmPercent: number;
    overTargetCount: number;
    assignmentCountYtd: number;
  };
}

function toNumber(value: number | string | null | undefined, fallback = 0): number {
  if (value === null || value === undefined) return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizePutCall(value: string | null | undefined): "C" | "P" | null {
  const normalized = (value || "").trim().toUpperCase();
  if (normalized === "C" || normalized === "CALL") return "C";
  if (normalized === "P" || normalized === "PUT") return "P";
  return null;
}

function openCloseTokens(value: string | null | undefined): Set<string> {
  return new Set(
    (value || "")
      .toUpperCase()
      .replaceAll(",", ";")
      .split(";")
      .map((token) => token.trim())
      .filter(Boolean)
  );
}

function localDate(dateTime: string): string {
  const d = parseAsNY(dateTime);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function parseExpiry(expiry: string | null | undefined): Date | null {
  if (!expiry) return null;
  const digits = expiry.replace(/\D/g, "");
  if (digits.length !== 8) return null;
  const year = Number(digits.slice(0, 4));
  const month = Number(digits.slice(4, 6));
  const day = Number(digits.slice(6, 8));
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
}

function daysUntil(expiry: string | null | undefined, now: Date): number | null {
  const expiryDate = parseExpiry(expiry);
  if (!expiryDate) return null;
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const end = new Date(expiryDate.getFullYear(), expiryDate.getMonth(), expiryDate.getDate());
  return Math.round((end.getTime() - start.getTime()) / 86_400_000);
}

function contractKey(trade: Trade): string {
  const putCall = normalizePutCall(trade.putCall);
  if (!putCall) return trade.contractKey || `EQ::${trade.symbol}`;
  const underlying = trade.underlyingSymbol || trade.symbol;
  const expiry = trade.expiry || "unknown";
  const strike = trade.strike ?? 0;
  const multiplier = trade.multiplier ?? 100;
  return trade.contractKey || `OPT::${underlying}::${expiry}::${putCall}::${strike}::${multiplier}`;
}

function metaBySymbol(targets: SymbolMeta[]): Record<string, SymbolMeta> {
  return Object.fromEntries(targets.map((target) => [target.symbol, target]));
}

export function calculateOptionExposures(
  trades: Trade[],
  now: Date = new Date()
): OptionExposureRow[] {
  const groups = new Map<string, Trade[]>();

  for (const trade of trades) {
    if (!isOptionTrade(trade)) continue;
    if (Math.abs(trade.remaining_qty ?? 0) < EPSILON) continue;
    const key = contractKey(trade);
    groups.set(key, [...(groups.get(key) || []), trade]);
  }

  const rows: OptionExposureRow[] = [];

  for (const [key, group] of groups) {
    const first = group[0];
    const contracts = group.reduce((sum, trade) => sum + (trade.remaining_qty ?? 0), 0);
    if (Math.abs(contracts) < EPSILON) continue;

    const multiplier = first.multiplier ?? 100;
    const strike = first.strike ?? null;
    const putCall = normalizePutCall(first.putCall);
    const notional = Math.abs(contracts) * (strike ?? 0) * multiplier;
    const quoteStatuses = new Set(group.map((trade) => trade.quote_status).filter(Boolean));

    rows.push({
      key,
      underlyingSymbol: first.underlyingSymbol || first.symbol,
      expiry: first.expiry || null,
      putCall,
      strike,
      side: contracts < 0 ? "short" : "long",
      contracts,
      absContracts: Math.abs(contracts),
      multiplier,
      notional,
      mtmValue: group.reduce((sum, trade) => sum + (trade.mtm_value ?? 0), 0),
      unrealizedPnl: group.reduce((sum, trade) => sum + (trade.unrealized_pnl ?? 0), 0),
      premiumCredit: group.reduce((sum, trade) => sum + (trade.credit ?? 0), 0),
      dte: daysUntil(first.expiry, now),
      quoteStatus: [...quoteStatuses].join(", ") || "unquoted",
    });
  }

  return rows.sort((a, b) => {
    const dteA = a.dte ?? Number.MAX_SAFE_INTEGER;
    const dteB = b.dte ?? Number.MAX_SAFE_INTEGER;
    if (dteA !== dteB) return dteA - dteB;
    return b.notional - a.notional;
  });
}

export function calculateExpiryRows(exposures: OptionExposureRow[]): ExpiryRiskRow[] {
  const groups = new Map<string, OptionExposureRow[]>();

  for (const exposure of exposures) {
    const key = exposure.expiry || "unknown";
    groups.set(key, [...(groups.get(key) || []), exposure]);
  }

  return [...groups.entries()]
    .map(([expiry, rows]) => ({
      expiry: expiry === "unknown" ? null : expiry,
      dte: rows.reduce<number | null>((min, row) => {
        if (row.dte === null) return min;
        return min === null ? row.dte : Math.min(min, row.dte);
      }, null),
      contractCount: rows.length,
      contracts: rows.reduce((sum, row) => sum + row.absContracts, 0),
      shortPutContracts: rows.reduce(
        (sum, row) => sum + (row.side === "short" && row.putCall === "P" ? row.absContracts : 0),
        0
      ),
      shortCallContracts: rows.reduce(
        (sum, row) => sum + (row.side === "short" && row.putCall === "C" ? row.absContracts : 0),
        0
      ),
      shortPutNotional: rows.reduce(
        (sum, row) => sum + (row.side === "short" && row.putCall === "P" ? row.notional : 0),
        0
      ),
      shortCallNotional: rows.reduce(
        (sum, row) => sum + (row.side === "short" && row.putCall === "C" ? row.notional : 0),
        0
      ),
      totalNotional: rows.reduce((sum, row) => sum + row.notional, 0),
      mtmValue: rows.reduce((sum, row) => sum + row.mtmValue, 0),
      unrealizedPnl: rows.reduce((sum, row) => sum + row.unrealizedPnl, 0),
    }))
    .sort((a, b) => (a.dte ?? Number.MAX_SAFE_INTEGER) - (b.dte ?? Number.MAX_SAFE_INTEGER));
}

function assignmentType(putCall: "C" | "P" | null, stockQuantity: number): string {
  if (putCall === "P" && stockQuantity > 0) return "short_put_assignment";
  if (putCall === "C" && stockQuantity < 0) return "short_call_assignment";
  if (putCall === "C" && stockQuantity > 0) return "long_call_exercise";
  if (putCall === "P" && stockQuantity < 0) return "long_put_exercise";
  return "option_exercise_or_assignment";
}

export function inferAssignmentEvents(trades: Trade[]): AssignmentEvent[] {
  const stockGroups = new Map<string, Trade[]>();

  for (const trade of trades) {
    if (isOptionTrade(trade)) continue;
    if (Math.abs(trade.quantity ?? 0) < EPSILON) continue;
    const underlying = trade.underlyingSymbol || trade.symbol;
    const priceKey = toNumber(trade.tradePrice).toFixed(4);
    const key = `${trade.dateTime}|${underlying}|${priceKey}`;
    stockGroups.set(key, [...(stockGroups.get(key) || []), trade]);
  }

  const optionGroups = new Map<string, Trade[]>();
  for (const trade of trades) {
    if (!isOptionTrade(trade)) continue;
    if (!openCloseTokens(trade.openCloseIndicator).has("C")) continue;
    if (Math.abs(trade.tradePrice ?? 0) > EPSILON) continue;
    if (Math.abs(trade.quantity ?? 0) < EPSILON) continue;

    const underlying = trade.underlyingSymbol || trade.symbol;
    const putCall = normalizePutCall(trade.putCall) || "?";
    const strike = toNumber(trade.strike).toFixed(4);
    const key = `${trade.dateTime}|${underlying}|${strike}|${putCall}|${trade.expiry || ""}`;
    optionGroups.set(key, [...(optionGroups.get(key) || []), trade]);
  }

  const events: AssignmentEvent[] = [];

  for (const group of optionGroups.values()) {
    const first = group[0];
    const underlying = first.underlyingSymbol || first.symbol;
    const strike = first.strike ?? null;
    const stockKey = `${first.dateTime}|${underlying}|${toNumber(strike).toFixed(4)}`;
    const stockGroup = stockGroups.get(stockKey);
    if (!stockGroup || stockGroup.length === 0) continue;

    const contracts = Math.abs(group.reduce((sum, trade) => sum + (trade.quantity ?? 0), 0));
    const multiplier = first.multiplier ?? 100;
    const expectedShares = contracts * multiplier;
    const stockQuantity = stockGroup.reduce((sum, trade) => sum + (trade.quantity ?? 0), 0);
    if (expectedShares > 0 && Math.abs(Math.abs(stockQuantity) - expectedShares) > Math.max(1, expectedShares * 0.01)) {
      continue;
    }

    const date = localDate(first.dateTime);
    const stockNotional = stockGroup.reduce(
      (sum, trade) => sum + Math.abs((trade.quantity ?? 0) * (trade.tradePrice ?? 0)),
      0
    );
    const putCall = normalizePutCall(first.putCall);

    events.push({
      date,
      month: date.slice(0, 7),
      underlyingSymbol: underlying,
      eventType: assignmentType(putCall, stockQuantity),
      putCall,
      expiry: first.expiry || null,
      strike,
      contracts,
      stockQuantity,
      stockNotional,
      optionRealizedPnl: group.reduce((sum, trade) => sum + (trade.realized_pnl ?? 0), 0),
      stockRealizedPnl: stockGroup.reduce((sum, trade) => sum + (trade.realized_pnl ?? 0), 0),
    });
  }

  return events.sort((a, b) => b.date.localeCompare(a.date));
}

export function buildRiskDashboardData({
  trades,
  positions,
  targets,
  quotes,
  now = new Date(),
}: {
  trades: Trade[];
  positions: Position[];
  targets: SymbolMeta[];
  quotes: MarketQuote[];
  now?: Date;
}): RiskDashboardData {
  const meta = metaBySymbol(targets);
  const exposures = calculateOptionExposures(trades, now);
  const expiryRows = calculateExpiryRows(exposures);
  const assignments = inferAssignmentEvents(trades);
  const latestTrade = trades.reduce<string | null>((latest, trade) => {
    if (!trade.dateTime) return latest;
    return latest === null || trade.dateTime > latest ? trade.dateTime : latest;
  }, null);
  const latestQuoteAt = quotes.reduce<string | null>((latest, quote) => {
    const updated = quote.quote_time || quote.updated_at;
    if (!updated) return latest;
    return latest === null || updated > latest ? updated : latest;
  }, null);
  const latestYear = latestTrade ? parseAsNY(latestTrade).getFullYear() : now.getFullYear();

  const exposuresByUnderlying = new Map<string, OptionExposureRow[]>();
  for (const exposure of exposures) {
    exposuresByUnderlying.set(exposure.underlyingSymbol, [
      ...(exposuresByUnderlying.get(exposure.underlyingSymbol) || []),
      exposure,
    ]);
  }

  const totalMtm = positions.reduce((sum, position) => sum + position.mtm, 0);
  const positionRows: UnderlyingRiskRow[] = positions.map((position) => {
    const optionRows = exposuresByUnderlying.get(position.symbol) || [];
    const targetPercent = meta[position.symbol]?.target_percent ?? position.targetPercent;
    const realizedPnl = position.stockPnl + position.callPnl + position.putPnl;
    const shortPutNotional = optionRows.reduce(
      (sum, row) => sum + (row.side === "short" && row.putCall === "P" ? row.notional : 0),
      0
    );
    const shortCallNotional = optionRows.reduce(
      (sum, row) => sum + (row.side === "short" && row.putCall === "C" ? row.notional : 0),
      0
    );
    const longOptionNotional = optionRows.reduce(
      (sum, row) => sum + (row.side === "long" ? row.notional : 0),
      0
    );
    const optionNotional = optionRows.reduce((sum, row) => sum + row.notional, 0);
    const frontDte = optionRows.reduce<number | null>((min, row) => {
      if (row.dte === null) return min;
      return min === null ? row.dte : Math.min(min, row.dte);
    }, null);
    const frontExpiryNotional = optionRows.reduce(
      (sum, row) => sum + (row.dte === frontDte ? row.notional : 0),
      0
    );
    const driftPercent = position.mtmPercent - targetPercent;
    const fullBookPnl = realizedPnl + position.unrealizedPnl;
    const riskFlags = [
      Math.abs(driftPercent) >= 3 ? "target drift" : null,
      shortPutNotional > Math.abs(position.mtm) ? "put-heavy" : null,
      position.unrealizedPnl < -5000 ? "large unrealized loss" : null,
      frontDte !== null && frontDte <= 21 && frontExpiryNotional > 0 ? "front expiry" : null,
    ].filter(Boolean) as string[];

    return {
      ...position,
      targetPercent,
      basket: meta[position.symbol]?.basket ?? null,
      score: meta[position.symbol]?.score ?? null,
      realizedPnl,
      fullBookPnl,
      driftPercent,
      shortPutNotional,
      shortCallNotional,
      longOptionNotional,
      optionNotional,
      optionMtm: optionRows.reduce((sum, row) => sum + row.mtmValue, 0),
      optionUnrealizedPnl: optionRows.reduce((sum, row) => sum + row.unrealizedPnl, 0),
      frontExpiryNotional,
      openOptionContracts: optionRows.reduce((sum, row) => sum + row.absContracts, 0),
      riskNotional: Math.abs(position.mtm) + optionNotional,
      riskFlags,
    };
  });

  const totalRealizedPnl = positionRows.reduce((sum, row) => sum + row.realizedPnl, 0);
  const totalUnrealizedPnl = positionRows.reduce((sum, row) => sum + row.unrealizedPnl, 0);
  const shortPutNotional = exposures.reduce(
    (sum, row) => sum + (row.side === "short" && row.putCall === "P" ? row.notional : 0),
    0
  );
  const shortCallNotional = exposures.reduce(
    (sum, row) => sum + (row.side === "short" && row.putCall === "C" ? row.notional : 0),
    0
  );
  const topFiveMtmPercent = [...positionRows]
    .sort((a, b) => Math.abs(b.mtm) - Math.abs(a.mtm))
    .slice(0, 5)
    .reduce((sum, row) => sum + Math.abs(row.mtmPercent), 0);
  const ytdAssignments = assignments.filter((event) => event.date.startsWith(String(latestYear)));

  return {
    asOf: latestTrade,
    latestQuoteAt,
    positionRows,
    optionExposures: exposures,
    expiryRows,
    assignmentEvents: assignments,
    totals: {
      totalMtm,
      totalRealizedPnl,
      totalUnrealizedPnl,
      totalBookPnl: totalRealizedPnl + totalUnrealizedPnl,
      positionCount: positionRows.length,
      optionContractCount: exposures.length,
      totalOptionNotional: exposures.reduce((sum, row) => sum + row.notional, 0),
      shortPutNotional,
      shortCallNotional,
      shortPutContracts: exposures.reduce(
        (sum, row) => sum + (row.side === "short" && row.putCall === "P" ? row.absContracts : 0),
        0
      ),
      shortCallContracts: exposures.reduce(
        (sum, row) => sum + (row.side === "short" && row.putCall === "C" ? row.absContracts : 0),
        0
      ),
      optionUnrealizedPnl: exposures.reduce((sum, row) => sum + row.unrealizedPnl, 0),
      frontExpiryNotional: expiryRows[0]?.totalNotional ?? 0,
      topFiveMtmPercent,
      overTargetCount: positionRows.filter((row) => row.driftPercent > 2).length,
      assignmentCountYtd: ytdAssignments.length,
    },
  };
}
