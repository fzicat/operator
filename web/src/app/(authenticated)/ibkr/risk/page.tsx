"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { IBKRMenu } from "@/components/layout/IBKRMenu";
import { Spinner } from "@/components/ui/Spinner";
import { NumericCell, Table } from "@/components/ui/Table";
import { useError } from "@/lib/error-context";
import { supabase, toCamelCaseArray } from "@/lib/supabase";
import {
  applyMtmPrices,
  calculateCredit,
  calculatePnL,
  calculatePositions,
} from "@/lib/utils/fifo";
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatPercent,
} from "@/lib/utils/format";
import {
  buildRiskDashboardData,
  ExpiryRiskRow,
  OptionExposureRow,
  RiskDashboardData,
  SymbolMeta,
  UnderlyingRiskRow,
} from "@/lib/utils/risk";
import { MarketQuote, Trade } from "@/types";

type SortDirection = "asc" | "desc";

type RawSymbolTarget = {
  symbol: string;
  target_percent: number | string | null;
  basket: string | null;
  score: number | string | null;
};

function asNumber(value: number | string | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function sortRows<T>(rows: T[], sortKey: string | null, direction: SortDirection): T[] {
  if (!sortKey) return rows;
  return [...rows].sort((a, b) => {
    const aValue = (a as Record<string, unknown>)[sortKey];
    const bValue = (b as Record<string, unknown>)[sortKey];

    if (typeof aValue === "string" && typeof bValue === "string") {
      return direction === "asc"
        ? aValue.localeCompare(bValue)
        : bValue.localeCompare(aValue);
    }

    const aNumber = typeof aValue === "number" ? aValue : 0;
    const bNumber = typeof bValue === "number" ? bValue : 0;
    return direction === "asc" ? aNumber - bNumber : bNumber - aNumber;
  });
}

function compactCurrency(value: number): string {
  return value.toLocaleString("en-US", {
    maximumFractionDigits: Math.abs(value) >= 100_000 ? 0 : 1,
    notation: Math.abs(value) >= 1_000_000 ? "compact" : "standard",
  });
}

function ratio(value: number, base: number): number {
  return base === 0 ? 0 : (value / base) * 100;
}

function toneClass(tone: "good" | "bad" | "warn" | "neutral") {
  switch (tone) {
    case "good":
      return "text-[var(--gruvbox-blue)]";
    case "bad":
      return "text-[var(--gruvbox-orange)]";
    case "warn":
      return "text-[var(--gruvbox-yellow)]";
    default:
      return "text-[var(--gruvbox-fg)]";
  }
}

function severityClass(severity: "ok" | "watch" | "hot") {
  switch (severity) {
    case "hot":
      return "border-[var(--gruvbox-red)] bg-[rgba(204,36,29,0.08)]";
    case "watch":
      return "border-[var(--gruvbox-yellow)] bg-[rgba(215,153,33,0.08)]";
    default:
      return "border-[var(--gruvbox-green)] bg-[rgba(152,151,26,0.08)]";
  }
}

function RiskCard({
  label,
  value,
  detail,
  tone = "neutral",
}: {
  label: string;
  value: string;
  detail: string;
  tone?: "good" | "bad" | "warn" | "neutral";
}) {
  return (
    <div className="p-3 rounded border border-[var(--gruvbox-bg3)] bg-[var(--gruvbox-bg1)]">
      <div className="text-xs uppercase tracking-wide text-[var(--gruvbox-fg4)]">{label}</div>
      <div className={`mt-1 text-2xl font-semibold font-data ${toneClass(tone)}`}>{value}</div>
      <div className="mt-1 text-xs text-[var(--gruvbox-fg4)]">{detail}</div>
    </div>
  );
}

function RiskAlert({
  title,
  value,
  detail,
  severity,
}: {
  title: string;
  value: string;
  detail: string;
  severity: "ok" | "watch" | "hot";
}) {
  return (
    <div className={`p-3 rounded border ${severityClass(severity)}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-semibold text-[var(--gruvbox-fg)]">{title}</div>
        <div className="text-sm font-data text-[var(--gruvbox-yellow)]">{value}</div>
      </div>
      <div className="mt-1 text-xs text-[var(--gruvbox-fg4)]">{detail}</div>
    </div>
  );
}

function RiskFlags({ flags }: { flags: string[] }) {
  if (flags.length === 0) return <span className="text-[var(--gruvbox-fg4)]">-</span>;
  return (
    <div className="flex flex-wrap justify-end gap-1">
      {flags.map((flag) => (
        <span
          key={flag}
          className="rounded border border-[var(--gruvbox-bg3)] px-1.5 py-0.5 text-[11px] text-[var(--gruvbox-yellow)]"
        >
          {flag}
        </span>
      ))}
    </div>
  );
}

export default function IBKRRiskDashboardPage() {
  const router = useRouter();
  const { setError } = useError();
  const [dashboard, setDashboard] = useState<RiskDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [positionSortKey, setPositionSortKey] = useState<string | null>("riskNotional");
  const [optionSortKey, setOptionSortKey] = useState<string | null>("notional");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      const [tradesResult, quotesResult, targetsResult] = await Promise.all([
        supabase.from("trades").select("*").order("date_time"),
        supabase.from("market_quotes").select("*"),
        supabase.from("symbol_targets").select("symbol, target_percent, basket, score"),
      ]);

      if (tradesResult.error) throw tradesResult.error;
      if (quotesResult.error) throw quotesResult.error;
      if (targetsResult.error) throw targetsResult.error;

      const quotes = (quotesResult.data || []) as MarketQuote[];
      const quotesByKey: Record<string, MarketQuote> = {};
      quotes.forEach((quote) => {
        quotesByKey[quote.contract_key] = quote;
      });

      const targets: SymbolMeta[] = ((targetsResult.data || []) as RawSymbolTarget[]).map((target) => ({
        symbol: target.symbol,
        target_percent: asNumber(target.target_percent),
        basket: target.basket ?? null,
        score: target.score === null || target.score === undefined ? null : asNumber(target.score),
      }));
      const targetPercents = Object.fromEntries(
        targets.map((target) => [target.symbol, target.target_percent ?? 0])
      );

      let trades = toCamelCaseArray<Trade>(tradesResult.data || []);
      trades = trades.filter((trade) => trade.symbol !== "USD.CAD");
      trades = calculatePnL(trades);
      trades = calculateCredit(trades);
      trades = applyMtmPrices(trades, quotesByKey);

      const totalMtm = trades.reduce((sum, trade) => sum + (trade.mtm_value ?? 0), 0);
      const positions = calculatePositions(trades, totalMtm, targetPercents);
      setDashboard(buildRiskDashboardData({ trades, positions, targets, quotes }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load risk dashboard");
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handlePositionSort = useCallback(
    (key: string) => {
      if (positionSortKey === key) {
        setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      } else {
        setPositionSortKey(key);
        setSortDirection("desc");
      }
    },
    [positionSortKey]
  );

  const handleOptionSort = useCallback(
    (key: string) => {
      if (optionSortKey === key) {
        setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      } else {
        setOptionSortKey(key);
        setSortDirection("desc");
      }
    },
    [optionSortKey]
  );

  const sortedPositions = useMemo(
    () => sortRows(dashboard?.positionRows || [], positionSortKey, sortDirection),
    [dashboard, positionSortKey, sortDirection]
  );
  const sortedOptions = useMemo(
    () => sortRows(dashboard?.optionExposures || [], optionSortKey, sortDirection),
    [dashboard, optionSortKey, sortDirection]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!dashboard) {
    return <div className="p-6 text-center text-[var(--gruvbox-fg4)]">No risk data available</div>;
  }

  const { totals } = dashboard;
  const shortPutPct = ratio(totals.shortPutNotional, Math.abs(totals.totalMtm));
  const optionNotionalPct = ratio(totals.totalOptionNotional, Math.abs(totals.totalMtm));
  const frontExpiryPct = ratio(totals.frontExpiryNotional, Math.abs(totals.totalMtm));
  const largestUnrealizedLosers = [...dashboard.positionRows]
    .sort((a, b) => a.unrealizedPnl - b.unrealizedPnl)
    .slice(0, 5);

  const positionColumns = [
    {
      key: "symbol",
      header: "Symbol",
      sortable: true,
      className: "text-[var(--gruvbox-yellow)] font-semibold",
    },
    {
      key: "basket",
      header: "Basket",
      sortable: true,
      render: (row: UnderlyingRiskRow) => (
        <span className="text-[var(--gruvbox-fg3)]">{row.basket || "-"}</span>
      ),
    },
    {
      key: "score",
      header: "Score",
      sortable: true,
      align: "right" as const,
      render: (row: UnderlyingRiskRow) => <NumericCell value={row.score} />,
    },
    {
      key: "riskNotional",
      header: "Risk Notional",
      sortable: true,
      align: "right" as const,
      render: (row: UnderlyingRiskRow) => <NumericCell value={row.riskNotional} format="currency" />,
    },
    {
      key: "mtmPercent",
      header: "MTM %",
      sortable: true,
      align: "right" as const,
      render: (row: UnderlyingRiskRow) => <NumericCell value={row.mtmPercent} format="percent" />,
    },
    {
      key: "targetPercent",
      header: "Tgt %",
      sortable: true,
      align: "right" as const,
      render: (row: UnderlyingRiskRow) => <NumericCell value={row.targetPercent} format="percent" />,
    },
    {
      key: "driftPercent",
      header: "Diff",
      sortable: true,
      align: "right" as const,
      render: (row: UnderlyingRiskRow) => <NumericCell value={row.driftPercent} format="percent" colorCode />,
    },
    {
      key: "fullBookPnl",
      header: "Book PnL",
      sortable: true,
      align: "right" as const,
      render: (row: UnderlyingRiskRow) => <NumericCell value={row.fullBookPnl} format="currency" colorCode />,
    },
    {
      key: "unrealizedPnl",
      header: "Unrlzd",
      sortable: true,
      align: "right" as const,
      render: (row: UnderlyingRiskRow) => <NumericCell value={row.unrealizedPnl} format="currency" colorCode />,
    },
    {
      key: "shortPutNotional",
      header: "Short Put",
      sortable: true,
      align: "right" as const,
      render: (row: UnderlyingRiskRow) => <NumericCell value={row.shortPutNotional} format="currency" />,
    },
    {
      key: "shortCallNotional",
      header: "Short Call",
      sortable: true,
      align: "right" as const,
      render: (row: UnderlyingRiskRow) => <NumericCell value={row.shortCallNotional} format="currency" />,
    },
    {
      key: "riskFlags",
      header: "Flags",
      align: "right" as const,
      render: (row: UnderlyingRiskRow) => <RiskFlags flags={row.riskFlags} />,
    },
  ];

  const expiryColumns = [
    {
      key: "expiry",
      header: "Expiry",
      sortable: true,
      className: "text-[var(--gruvbox-yellow)] font-semibold",
      render: (row: ExpiryRiskRow) => row.expiry || "Unknown",
    },
    { key: "dte", header: "DTE", sortable: true, align: "right" as const },
    {
      key: "contracts",
      header: "Contracts",
      sortable: true,
      align: "right" as const,
      render: (row: ExpiryRiskRow) => <NumericCell value={row.contracts} />,
    },
    {
      key: "shortPutNotional",
      header: "Short Put",
      sortable: true,
      align: "right" as const,
      render: (row: ExpiryRiskRow) => <NumericCell value={row.shortPutNotional} format="currency" />,
    },
    {
      key: "shortCallNotional",
      header: "Short Call",
      sortable: true,
      align: "right" as const,
      render: (row: ExpiryRiskRow) => <NumericCell value={row.shortCallNotional} format="currency" />,
    },
    {
      key: "totalNotional",
      header: "Total Notional",
      sortable: true,
      align: "right" as const,
      render: (row: ExpiryRiskRow) => <NumericCell value={row.totalNotional} format="currency" />,
    },
    {
      key: "unrealizedPnl",
      header: "Unrlzd",
      sortable: true,
      align: "right" as const,
      render: (row: ExpiryRiskRow) => <NumericCell value={row.unrealizedPnl} format="currency" colorCode />,
    },
  ];

  const optionColumns = [
    {
      key: "underlyingSymbol",
      header: "Symbol",
      sortable: true,
      className: "text-[var(--gruvbox-yellow)] font-semibold",
    },
    { key: "expiry", header: "Expiry", sortable: true },
    { key: "dte", header: "DTE", sortable: true, align: "right" as const },
    { key: "putCall", header: "Type", sortable: true },
    {
      key: "strike",
      header: "Strike",
      sortable: true,
      align: "right" as const,
      render: (row: OptionExposureRow) => <NumericCell value={row.strike} decimals={2} />,
    },
    {
      key: "contracts",
      header: "Qty",
      sortable: true,
      align: "right" as const,
      render: (row: OptionExposureRow) => <NumericCell value={row.contracts} />,
    },
    {
      key: "notional",
      header: "Notional",
      sortable: true,
      align: "right" as const,
      render: (row: OptionExposureRow) => <NumericCell value={row.notional} format="currency" />,
    },
    {
      key: "unrealizedPnl",
      header: "Unrlzd",
      sortable: true,
      align: "right" as const,
      render: (row: OptionExposureRow) => <NumericCell value={row.unrealizedPnl} format="currency" colorCode />,
    },
    {
      key: "quoteStatus",
      header: "Quote",
      sortable: true,
      render: (row: OptionExposureRow) => (
        <span className={row.quoteStatus === "live" ? "text-[var(--gruvbox-green)]" : "text-[var(--gruvbox-yellow)]"}>
          {row.quoteStatus}
        </span>
      ),
    },
  ];

  return (
    <div>
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-center gap-2">
          <IBKRMenu />
          <div>
            <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">
              IBKR Risk Dashboard
            </h1>
            <div className="text-xs text-[var(--gruvbox-fg4)]">
              Trades as of {dashboard.asOf ? formatDateTime(dashboard.asOf) : "-"}; quotes as of{" "}
              {dashboard.latestQuoteAt ? formatDateTime(dashboard.latestQuoteAt) : "-"}
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 mb-4">
        <RiskCard
          label="Net Book PnL"
          value={compactCurrency(totals.totalBookPnl)}
          detail="Realized + current unrealized"
          tone={totals.totalBookPnl >= 0 ? "good" : "bad"}
        />
        <RiskCard
          label="Realized PnL"
          value={compactCurrency(totals.totalRealizedPnl)}
          detail={`${totals.positionCount} active symbols`}
          tone={totals.totalRealizedPnl >= 0 ? "good" : "bad"}
        />
        <RiskCard
          label="Unrealized PnL"
          value={compactCurrency(totals.totalUnrealizedPnl)}
          detail="Open-stock + open-option mark"
          tone={totals.totalUnrealizedPnl >= 0 ? "good" : "bad"}
        />
        <RiskCard
          label="Open Option Notional"
          value={compactCurrency(totals.totalOptionNotional)}
          detail={`${formatPercent(optionNotionalPct)} of current MTM`}
          tone={optionNotionalPct > 100 ? "bad" : optionNotionalPct > 60 ? "warn" : "neutral"}
        />
        <RiskCard
          label="Short Puts"
          value={compactCurrency(totals.shortPutNotional)}
          detail={`${formatNumber(totals.shortPutContracts)} contracts / ${formatPercent(shortPutPct)} MTM`}
          tone={shortPutPct > 60 ? "bad" : shortPutPct > 35 ? "warn" : "neutral"}
        />
        <RiskCard
          label="Short Calls"
          value={compactCurrency(totals.shortCallNotional)}
          detail={`${formatNumber(totals.shortCallContracts)} contracts`}
          tone="neutral"
        />
        <RiskCard
          label="Front Expiry"
          value={compactCurrency(totals.frontExpiryNotional)}
          detail={`${formatPercent(frontExpiryPct)} of current MTM`}
          tone={frontExpiryPct > 25 ? "bad" : frontExpiryPct > 15 ? "warn" : "neutral"}
        />
        <RiskCard
          label="Assignments YTD"
          value={formatNumber(totals.assignmentCountYtd)}
          detail="Inferred high-confidence events"
          tone={totals.assignmentCountYtd > 25 ? "warn" : "neutral"}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-3 mb-4">
        <RiskAlert
          title="Short-put assignment load"
          value={`${formatPercent(shortPutPct)} MTM`}
          detail={`${formatCurrency(totals.shortPutNotional)} of cash-secured strike notional is open.`}
          severity={shortPutPct > 60 ? "hot" : shortPutPct > 35 ? "watch" : "ok"}
        />
        <RiskAlert
          title="Top-five concentration"
          value={formatPercent(totals.topFiveMtmPercent)}
          detail="Share of portfolio MTM held by the largest five underlying positions."
          severity={totals.topFiveMtmPercent > 35 ? "watch" : "ok"}
        />
        <RiskAlert
          title="Open unrealized drag"
          value={formatCurrency(totals.totalUnrealizedPnl)}
          detail={`Worst current drags: ${largestUnrealizedLosers
            .map((row) => `${row.symbol} ${formatCurrency(row.unrealizedPnl)}`)
            .join(", ")}`}
          severity={totals.totalUnrealizedPnl < -50_000 ? "hot" : totals.totalUnrealizedPnl < 0 ? "watch" : "ok"}
        />
      </div>

      <div className="space-y-4">
        <div className="p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
          <div className="mb-2 flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-[var(--gruvbox-fg4)]">Underlying Risk</h2>
            <span className="text-xs text-[var(--gruvbox-fg4)]">
              Sorted by combined MTM + option assignment notional
            </span>
          </div>
          <Table
            data={sortedPositions}
            columns={positionColumns}
            onRowClick={(row) => router.push(`/ibkr/positions/${row.symbol}`)}
            keyExtractor={(row) => row.symbol}
            emptyMessage="No position risk found"
            sortKey={positionSortKey}
            sortDirection={sortDirection}
            onSort={handlePositionSort}
          />
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
            <h2 className="text-sm font-semibold text-[var(--gruvbox-fg4)] mb-2">Expiry Ladder</h2>
            <Table
              data={dashboard.expiryRows}
              columns={expiryColumns}
              keyExtractor={(row) => row.expiry || "unknown"}
              emptyMessage="No open options found"
            />
          </div>

          <div className="p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
            <h2 className="text-sm font-semibold text-[var(--gruvbox-fg4)] mb-2">
              Recent Assignments / Exercises
            </h2>
            <div className="space-y-2">
              {dashboard.assignmentEvents.slice(0, 8).map((event) => (
                <div
                  key={`${event.date}-${event.underlyingSymbol}-${event.eventType}-${event.strike}`}
                  className="flex items-center justify-between gap-3 rounded border border-[var(--gruvbox-bg2)] bg-[var(--gruvbox-bg-hard)] px-3 py-2 text-sm"
                >
                  <div>
                    <div className="font-semibold text-[var(--gruvbox-yellow)]">
                      {event.underlyingSymbol} · {event.eventType.replaceAll("_", " ")}
                    </div>
                    <div className="text-xs text-[var(--gruvbox-fg4)]">
                      {event.date} · {event.putCall} {event.expiry} {event.strike}
                    </div>
                  </div>
                  <div className="text-right font-data">
                    <div className="text-[var(--gruvbox-fg)]">{formatNumber(event.contracts)} contracts</div>
                    <div className="text-xs text-[var(--gruvbox-fg4)]">
                      {formatCurrency(event.stockNotional)} stock notional
                    </div>
                  </div>
                </div>
              ))}
              {dashboard.assignmentEvents.length === 0 && (
                <div className="p-6 text-center text-[var(--gruvbox-fg4)]">No assignment events found</div>
              )}
            </div>
          </div>
        </div>

        <div className="p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
          <div className="mb-2 flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-[var(--gruvbox-fg4)]">Largest Open Option Risks</h2>
            <span className="text-xs text-[var(--gruvbox-fg4)]">All open option lots, grouped by contract</span>
          </div>
          <Table
            data={sortedOptions}
            columns={optionColumns}
            keyExtractor={(row) => row.key}
            emptyMessage="No open options found"
            sortKey={optionSortKey}
            sortDirection={sortDirection}
            onSort={handleOptionSort}
          />
        </div>
      </div>
    </div>
  );
}
