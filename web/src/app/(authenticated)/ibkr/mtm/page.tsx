"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { supabase, toCamelCaseArray } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { MarketQuote, Position, Trade } from "@/types";
import {
  calculatePnL,
  calculateCredit,
  applyMtmPrices,
  calculatePositions,
} from "@/lib/utils/fifo";
import { Table, NumericCell } from "@/components/ui/Table";
import { Spinner } from "@/components/ui/Spinner";
import { IBKRMenu } from "@/components/layout/IBKRMenu";

type SortDirection = "asc" | "desc";

type MtmRow = Position & { totalUnrealizedPnl: number };

export default function IBKRMtmPage() {
  const router = useRouter();
  const { setError } = useError();
  const [rows, setRows] = useState<MtmRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<string | null>("mtm");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      const { data: tradesData, error: tradesError } = await supabase
        .from("trades")
        .select("*")
        .order("date_time");

      if (tradesError) throw tradesError;

      const { data: quotesData, error: quotesError } = await supabase
        .from("market_quotes")
        .select("*");

      if (quotesError) throw quotesError;

      const { data: targetsData, error: targetsError } = await supabase
        .from("symbol_targets")
        .select("symbol, target_percent");

      if (targetsError) throw targetsError;

      const marketQuotes: Record<string, MarketQuote> = {};
      (quotesData || []).forEach((quote: MarketQuote) => {
        marketQuotes[quote.contract_key] = quote;
      });

      const targetPercents: Record<string, number> = {};
      (targetsData || []).forEach((t: { symbol: string; target_percent: number }) => {
        targetPercents[t.symbol] = t.target_percent;
      });

      let processedTrades = toCamelCaseArray<Trade>(tradesData || []);
      processedTrades = processedTrades.filter((t) => t.symbol !== "USD.CAD");
      processedTrades = calculatePnL(processedTrades);
      processedTrades = calculateCredit(processedTrades);
      processedTrades = applyMtmPrices(processedTrades, marketQuotes);

      const totalMtm = processedTrades.reduce(
        (sum, t) => sum + (t.mtm_value ?? 0),
        0
      );
      const positionsData = calculatePositions(processedTrades, totalMtm, targetPercents);
      const withTotal: MtmRow[] = positionsData.map((p) => ({
        ...p,
        totalUnrealizedPnl:
          p.stockUnrealizedPnl + p.callUnrealizedPnl + p.putUnrealizedPnl,
      }));
      withTotal.sort((a, b) => b.mtm - a.mtm);
      setRows(withTotal);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSort = useCallback((key: string) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("desc");
    }
  }, [sortKey]);

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    const sorted = [...rows].sort((a, b) => {
      const aVal = (a as unknown as Record<string, unknown>)[sortKey];
      const bVal = (b as unknown as Record<string, unknown>)[sortKey];

      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortDirection === "asc"
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }

      const aNum = typeof aVal === "number" ? aVal : 0;
      const bNum = typeof bVal === "number" ? bVal : 0;
      return sortDirection === "asc" ? aNum - bNum : bNum - aNum;
    });
    return sorted;
  }, [rows, sortKey, sortDirection]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  const columns = [
    {
      key: "symbol",
      header: "Symbol",
      sortable: true,
      className: "text-[var(--gruvbox-yellow)] font-semibold",
    },
    {
      key: "mtm",
      header: "MTM",
      sortable: true,
      align: "right" as const,
      className: "text-[var(--gruvbox-blue)]",
      render: (p: MtmRow) => <NumericCell value={p.mtm} format="currency" />,
    },
    {
      key: "stockUnrealizedPnl",
      header: "Stk Unrlzd PnL",
      sortable: true,
      align: "right" as const,
      render: (p: MtmRow) => (
        <NumericCell value={p.stockUnrealizedPnl} format="currency" colorCode />
      ),
    },
    {
      key: "callUnrealizedPnl",
      header: "Call Unrlzd PnL",
      sortable: true,
      align: "right" as const,
      render: (p: MtmRow) => (
        <NumericCell value={p.callUnrealizedPnl} format="currency" colorCode />
      ),
    },
    {
      key: "putUnrealizedPnl",
      header: "Put Unrlzd PnL",
      sortable: true,
      align: "right" as const,
      render: (p: MtmRow) => (
        <NumericCell value={p.putUnrealizedPnl} format="currency" colorCode />
      ),
    },
    {
      key: "totalUnrealizedPnl",
      header: "Total Unrlzd PnL",
      sortable: true,
      align: "right" as const,
      render: (p: MtmRow) => (
        <NumericCell value={p.totalUnrealizedPnl} format="currency" colorCode />
      ),
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <IBKRMenu />
          <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">
            IBKR MTM
          </h1>
        </div>
      </div>

      <Table
        data={sortedRows}
        columns={columns}
        onRowClick={(row) => router.push(`/ibkr/positions/${row.symbol}`)}
        keyExtractor={(p) => p.symbol}
        emptyMessage="No positions found"
        sortKey={sortKey}
        sortDirection={sortDirection}
        onSort={handleSort}
      />
    </div>
  );
}
