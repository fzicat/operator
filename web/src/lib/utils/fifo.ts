import { MarketQuote, Position, Trade } from "@/types";

interface InventoryItem {
  idx: number;
  qty: number;
  price: number;
}

function normalizeSymbol(symbol: string | null | undefined): string {
  return (symbol || "").trim().toUpperCase();
}

function normalizePutCall(putCall: string | null | undefined): "C" | "P" | null {
  const value = (putCall || "").trim().toUpperCase();
  if (value === "C" || value === "P") return value;
  if (value === "CALL") return "C";
  if (value === "PUT") return "P";
  return null;
}

function normalizeExpiry(expiry: string | null | undefined): string | null {
  if (!expiry) return null;
  const digits = expiry.replace(/\D/g, "");
  return digits.length === 8 ? digits : null;
}

function normalizeStrike(strike: number | null | undefined): string | null {
  if (strike === null || strike === undefined || Number.isNaN(strike)) return null;
  return strike.toFixed(4);
}

export function isOptionTrade(trade: Pick<Trade, "putCall">): boolean {
  return normalizePutCall(trade.putCall) !== null;
}

export function buildContractKey(trade: Trade): string | null {
  if (isOptionTrade(trade)) {
    const underlying = normalizeSymbol(trade.underlyingSymbol || trade.symbol);
    const expiry = normalizeExpiry(trade.expiry);
    const putCall = normalizePutCall(trade.putCall);
    const strike = normalizeStrike(trade.strike);
    const multiplier = trade.multiplier ?? 100;

    if (!underlying || !expiry || !putCall || !strike || !multiplier) {
      return null;
    }

    return `OPT::${underlying}::${expiry}::${putCall}::${strike}::${multiplier}`;
  }

  const symbol = normalizeSymbol(trade.symbol);
  if (!symbol) return null;
  return `EQ::${symbol}`;
}

export function calculatePnL(trades: Trade[]): Trade[] {
  if (trades.length === 0) return [];

  const result = trades.map((trade) => ({
    ...trade,
    contractKey: buildContractKey(trade),
    realized_pnl: 0,
    remaining_qty: 0,
  }));

  const inventory: Record<string, InventoryItem[]> = {};

  for (let idx = 0; idx < result.length; idx++) {
    const row = result[idx];
    const symbol = row.symbol;
    let qty = row.quantity ?? 0;
    const price = row.tradePrice ?? 0;
    const multiplier = row.multiplier ?? 1;

    if (!inventory[symbol]) {
      inventory[symbol] = [];
    }

    if (inventory[symbol].length === 0) {
      result[idx].remaining_qty = qty;
      inventory[symbol].push({ idx, qty, price });
      continue;
    }

    const head = inventory[symbol][0];

    if ((qty > 0 && head.qty > 0) || (qty < 0 && head.qty < 0)) {
      result[idx].remaining_qty = qty;
      inventory[symbol].push({ idx, qty, price });
    } else {
      let qtyToProcess = qty;
      let totalPnl = 0;

      while (qtyToProcess !== 0 && inventory[symbol].length > 0) {
        const item = inventory[symbol][0];
        const openQty = item.qty;
        const openPrice = item.price;
        const openIdx = item.idx;

        if (Math.abs(qtyToProcess) >= Math.abs(openQty)) {
          const matchQty = -openQty;
          const termPnl = -(price - openPrice) * matchQty * multiplier;
          totalPnl += termPnl;
          qtyToProcess -= matchQty;

          result[openIdx].remaining_qty = 0;
          inventory[symbol].shift();
        } else {
          const termPnl = -(price - openPrice) * qtyToProcess * multiplier;
          totalPnl += termPnl;

          item.qty += qtyToProcess;
          result[openIdx].remaining_qty = item.qty;

          qtyToProcess = 0;
        }
      }

      result[idx].realized_pnl = totalPnl;

      if (qtyToProcess !== 0) {
        result[idx].remaining_qty = qtyToProcess;
        inventory[symbol].push({ idx, qty: qtyToProcess, price });
      }
    }
  }

  return result;
}

/**
 * For each closing trade, compute the original opening premium of the lots it
 * closes, attributed to that closing trade (field `closed_open_premium`).
 *
 * Uses FIFO matching by symbol (same matching as calculatePnL). The opening
 * premium per contract follows the same sign convention as `credit`/premium:
 * sell-to-open yields a positive premium-per-contract, buy-to-open negative.
 * Trades must be passed in chronological order.
 */
export function calculateClosedOpenPremium(trades: Trade[]): Trade[] {
  const result = trades.map((trade) => ({ ...trade, closed_open_premium: 0 }));

  // Per-symbol inventory of open lots: signed qty + premium per (absolute) contract
  const inventory: Record<string, { qty: number; premiumPerContract: number }[]> = {};

  for (let idx = 0; idx < result.length; idx++) {
    const row = result[idx];
    const symbol = row.symbol;
    const qty = row.quantity ?? 0;
    const price = row.tradePrice ?? 0;
    const multiplier = row.multiplier ?? 1;

    if (qty === 0) continue;

    // -sign(qty) * price * multiplier — premium received per contract on opening
    const premiumPerContract = (-qty * price * multiplier) / Math.abs(qty);

    if (!inventory[symbol]) inventory[symbol] = [];

    const head = inventory[symbol][0];

    if (!head || (qty > 0 && head.qty > 0) || (qty < 0 && head.qty < 0)) {
      // Opening (or adding to position in the same direction)
      inventory[symbol].push({ qty, premiumPerContract });
      continue;
    }

    // Opposite direction — closing existing lots FIFO
    let qtyToProcess = qty;
    let closedPremium = 0;

    while (qtyToProcess !== 0 && inventory[symbol].length > 0) {
      const item = inventory[symbol][0];

      if (Math.abs(qtyToProcess) >= Math.abs(item.qty)) {
        closedPremium += Math.abs(item.qty) * item.premiumPerContract;
        qtyToProcess += item.qty; // opposite signs move toward zero
        inventory[symbol].shift();
      } else {
        closedPremium += Math.abs(qtyToProcess) * item.premiumPerContract;
        item.qty += qtyToProcess;
        qtyToProcess = 0;
      }
    }

    result[idx].closed_open_premium = closedPremium;

    // Leftover quantity opens a new lot in the opposite direction
    if (qtyToProcess !== 0) {
      inventory[symbol].push({ qty: qtyToProcess, premiumPerContract });
    }
  }

  return result;
}

export function calculateCredit(trades: Trade[]): Trade[] {
  return trades.map((trade) => {
    const multiplier = trade.multiplier ?? 1;
    const credit = (trade.remaining_qty ?? 0) * trade.tradePrice * multiplier * -1;
    return { ...trade, contractKey: trade.contractKey ?? buildContractKey(trade), credit };
  });
}

function deriveLegacyContractQuote(
  trade: Trade,
  prices: Record<string, number>
): MarketQuote | null {
  if (isOptionTrade(trade)) return null;

  const price = prices[trade.symbol];
  if (price === undefined) return null;

  return {
    contract_key: buildContractKey(trade) || `EQ::${trade.symbol}`,
    instrument_type: "equity",
    source: "yahoo_fallback",
    symbol: trade.symbol,
    underlying_symbol: trade.underlyingSymbol || trade.symbol,
    expiry: null,
    put_call: null,
    strike: null,
    multiplier: 1,
    conid: null,
    bid: null,
    ask: null,
    last: price,
    close: null,
    mark: price,
    status: "live",
    quote_time: null,
    updated_at: new Date().toISOString(),
  };
}

export function applyMarketQuotes(
  trades: Trade[],
  quotesByKey: Record<string, MarketQuote>
): Trade[] {
  return trades.map((trade) => {
    const contractKey = trade.contractKey ?? buildContractKey(trade);
    const quote = contractKey ? quotesByKey[contractKey] : undefined;
    const multiplier = trade.multiplier ?? (isOptionTrade(trade) ? 100 : 1);

    if (!contractKey) {
      return {
        ...trade,
        contractKey: null,
        quote_status: "contract_unresolved",
        quote_source: null,
        mtm_price: null,
        mtm_value: null,
        unrealized_pnl: null,
      };
    }

    if (!quote || quote.mark === null || quote.mark === undefined) {
      return {
        ...trade,
        contractKey,
        quote_status: quote?.status ?? "unavailable",
        quote_source: quote?.source ?? null,
        mtm_price: null,
        mtm_value: null,
        unrealized_pnl: null,
      };
    }

    const mtmPrice = quote.mark;
    const mtmValue =
      mtmPrice * (trade.remaining_qty ?? 0) * (isOptionTrade(trade) ? multiplier : 1);
    const unrealizedPnl = mtmValue + (trade.credit ?? 0);

    return {
      ...trade,
      contractKey,
      quote_status: quote.status,
      quote_source: quote.source,
      mtm_price: mtmPrice,
      mtm_value: mtmValue,
      unrealized_pnl: unrealizedPnl,
    };
  });
}

export function applyMtmPrices(
  trades: Trade[],
  marketData: Record<string, number> | Record<string, MarketQuote>
): Trade[] {
  const values = Object.values(marketData);
  const looksLikeQuoteMap = values.length > 0 && typeof values[0] === "object";

  if (looksLikeQuoteMap) {
    return applyMarketQuotes(trades, marketData as Record<string, MarketQuote>);
  }

  const priceMap = marketData as Record<string, number>;
  const quoteMap: Record<string, MarketQuote> = {};
  for (const trade of trades) {
    const legacyQuote = deriveLegacyContractQuote(trade, priceMap);
    if (legacyQuote) {
      quoteMap[legacyQuote.contract_key] = legacyQuote;
    }
  }

  return applyMarketQuotes(trades, quoteMap);
}

export function groupByUnderlying(trades: Trade[]): Record<string, Trade[]> {
  const groups: Record<string, Trade[]> = {};
  for (const trade of trades) {
    const symbol = trade.underlyingSymbol || trade.symbol;
    if (!groups[symbol]) {
      groups[symbol] = [];
    }
    groups[symbol].push(trade);
  }
  return groups;
}

export function calculatePositions(
  trades: Trade[],
  totalMtm: number,
  targetPercents: Record<string, number> = {}
): Position[] {
  const groups = groupByUnderlying(trades);
  const positions: Position[] = [];

  for (const [symbol, groupTrades] of Object.entries(groups)) {
    const stockTrades = groupTrades.filter((t) => !isOptionTrade(t));
    const callTrades = groupTrades.filter((t) => normalizePutCall(t.putCall) === "C");
    const putTrades = groupTrades.filter((t) => normalizePutCall(t.putCall) === "P");

    const stockValue = stockTrades.reduce((sum, t) => sum + (t.credit ?? 0), 0) * -1;
    const stockMtm = stockTrades.reduce((sum, t) => sum + (t.mtm_value ?? 0), 0);
    const callMtm = callTrades.reduce((sum, t) => sum + (t.mtm_value ?? 0), 0);
    const putMtm = putTrades.reduce((sum, t) => sum + (t.mtm_value ?? 0), 0);
    const mtm = stockMtm + callMtm + putMtm;

    const stockUnrealizedPnl = stockTrades.reduce(
      (sum, t) => sum + (t.unrealized_pnl ?? 0),
      0
    );
    const callUnrealizedPnl = callTrades.reduce(
      (sum, t) => sum + (t.unrealized_pnl ?? 0),
      0
    );
    const putUnrealizedPnl = putTrades.reduce(
      (sum, t) => sum + (t.unrealized_pnl ?? 0),
      0
    );
    const unrealizedPnl = stockUnrealizedPnl + callUnrealizedPnl + putUnrealizedPnl;

    const stockQty = stockTrades.reduce((sum, t) => sum + (t.remaining_qty ?? 0), 0);
    const callQty = callTrades.reduce((sum, t) => sum + (t.remaining_qty ?? 0), 0);
    const putQty = putTrades.reduce((sum, t) => sum + (t.remaining_qty ?? 0), 0);

    const stockPnl = stockTrades.reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0);
    const callPnl = callTrades.reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0);
    const putPnl = putTrades.reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0);

    const creditSum = stockTrades.reduce((sum, t) => sum + (t.credit ?? 0), 0);
    const bookPrice = stockQty !== 0 ? creditSum / stockQty : 0;

    if (
      stockValue === 0 &&
      mtm === 0 &&
      stockQty === 0 &&
      callQty === 0 &&
      putQty === 0 &&
      stockPnl === 0 &&
      callPnl === 0 &&
      putPnl === 0
    ) {
      continue;
    }

    positions.push({
      symbol,
      underlyingSymbol: symbol,
      value: stockValue,
      mtm,
      mtmPercent: totalMtm !== 0 ? (mtm / totalMtm) * 100 : 0,
      targetPercent: targetPercents[symbol] ?? 0,
      unrealizedPnl,
      stockValue,
      stockMtm,
      callMtm,
      putMtm,
      stockUnrealizedPnl,
      callUnrealizedPnl,
      putUnrealizedPnl,
      stockQty,
      callQty,
      putQty,
      stockPnl,
      callPnl,
      putPnl,
      bookPrice,
    });
  }

  return positions;
}

export function calculateTotals(positions: Position[]) {
  return {
    totalValue: positions.reduce((sum, p) => sum + p.value, 0),
    totalMtm: positions.reduce((sum, p) => sum + p.mtm, 0),
    totalUnrealizedPnl: positions.reduce((sum, p) => sum + p.unrealizedPnl, 0),
    totalStockUnrealizedPnl: positions.reduce((sum, p) => sum + p.stockUnrealizedPnl, 0),
    totalCallUnrealizedPnl: positions.reduce((sum, p) => sum + p.callUnrealizedPnl, 0),
    totalPutUnrealizedPnl: positions.reduce((sum, p) => sum + p.putUnrealizedPnl, 0),
    totalStockQty: positions.reduce((sum, p) => sum + p.stockQty, 0),
    totalCallQty: positions.reduce((sum, p) => sum + p.callQty, 0),
    totalPutQty: positions.reduce((sum, p) => sum + p.putQty, 0),
    totalStockPnl: positions.reduce((sum, p) => sum + p.stockPnl, 0),
    totalCallPnl: positions.reduce((sum, p) => sum + p.callPnl, 0),
    totalPutPnl: positions.reduce((sum, p) => sum + p.putPnl, 0),
    totalTargetPct: positions.reduce((sum, p) => sum + p.targetPercent, 0),
  };
}
