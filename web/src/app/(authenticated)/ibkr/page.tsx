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
  calculateTotals,
} from "@/lib/utils/fifo";
import { Table, NumericCell } from "@/components/ui/Table";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";

type SortDirection = "asc" | "desc";

export default function IBKRPage() {
  const router = useRouter();
  const { setError } = useError();
  const [positions, setPositions] = useState<Position[]>([]);
  const [totals, setTotals] = useState<ReturnType<typeof calculateTotals> | null>(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [updatingMtm, setUpdatingMtm] = useState(false);
  const [sortKey, setSortKey] = useState<string | null>("mtm");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      // Fetch trades
      const { data: tradesData, error: tradesError } = await supabase
        .from("trades")
        .select("*")
        .order("date_time");

      if (tradesError) throw tradesError;

      // Fetch normalized market quotes
      const { data: quotesData, error: quotesError } = await supabase
        .from("market_quotes")
        .select("*");

      if (quotesError) throw quotesError;

      // Fetch symbol targets
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

      // Process trades
      let processedTrades = toCamelCaseArray<Trade>(tradesData || []);
      // Filter out USD.CAD
      processedTrades = processedTrades.filter((t) => t.symbol !== "USD.CAD");
      processedTrades = calculatePnL(processedTrades);
      processedTrades = calculateCredit(processedTrades);
      processedTrades = applyMtmPrices(processedTrades, marketQuotes);

      // Calculate positions
      const totalMtm = processedTrades.reduce(
        (sum, t) => sum + (t.mtm_value ?? 0),
        0
      );
      const positionsData = calculatePositions(processedTrades, totalMtm, targetPercents);
      // Sort by MTM descending
      positionsData.sort((a, b) => b.mtm - a.mtm);
      setPositions(positionsData);
      setTotals(calculateTotals(positionsData));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleImport = async () => {
    try {
      setImporting(true);
      // Call the import API endpoint
      const res = await fetch("/api/ibkr/import", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Import failed");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  const handleUpdateMtm = async () => {
    try {
      setUpdatingMtm(true);
      const res = await fetch("/api/ibkr/mtm", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "MTM update failed");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "MTM update failed");
    } finally {
      setUpdatingMtm(false);
    }
  };

  const handleSort = useCallback((key: string) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("desc");
    }
  }, [sortKey]);

  const sortedPositions = useMemo(() => {
    if (!sortKey) return positions;
    const sorted = [...positions].sort((a, b) => {
      const aVal = (a as unknown as Record<string, unknown>)[sortKey];
      const bVal = (b as unknown as Record<string, unknown>)[sortKey];

      // Handle string comparison for symbol
      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortDirection === "asc"
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }

      // Handle numeric comparison
      const aNum = typeof aVal === "number" ? aVal : 0;
      const bNum = typeof bVal === "number" ? bVal : 0;
      return sortDirection === "asc" ? aNum - bNum : bNum - aNum;
    });
    return sorted;
  }, [positions, sortKey, sortDirection]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  const columns = [
    { key: "symbol", header: "Symbol", sortable: true, className: "text-[var(--gruvbox-yellow)] font-semibold" },
    {
      key: "value",
      header: "Value",
      sortable: true,
      align: "right" as const,
      render: (p: Position) => <NumericCell value={p.value} format="currency" />,
    },
    {
      key: "mtm",
      header: "MTM",
      sortable: true,
      align: "right" as const,
      className: "text-[var(--gruvbox-blue)]",
      render: (p: Position) => <NumericCell value={p.mtm} format="currency" />,
    },
    {
      key: "mtmPercent",
      header: "MTM %",
      sortable: true,
      align: "right" as const,
      render: (p: Position) => <NumericCell value={p.mtmPercent} format="percent" />,
    },
    {
      key: "targetPercent",
      header: "Tgt %",
      sortable: true,
      align: "right" as const,
      className: "text-[var(--gruvbox-aqua)]",
      render: (p: Position) => (
        <span
          className={
            Math.abs(p.mtmPercent - p.targetPercent) <= 2
              ? "text-[var(--gruvbox-green)]"
              : "text-[var(--gruvbox-red)]"
          }
        >
          {p.targetPercent > 0 ? `${p.targetPercent.toFixed(2)}%` : "-"}
        </span>
      ),
    },
    {
      key: "unrealizedPnl",
      header: "Unrlzd PnL",
      sortable: true,
      align: "right" as const,
      render: (p: Position) => (
        <NumericCell value={p.unrealizedPnl} format="currency" colorCode />
      ),
    },
    {
      key: "stockQty",
      header: "Stock",
      sortable: true,
      align: "right" as const,
      className: "text-[var(--gruvbox-purple)]",
      render: (p: Position) => <NumericCell value={p.stockQty} />,
    },
    {
      key: "callQty",
      header: "Call",
      sortable: true,
      align: "right" as const,
      className: "text-[var(--gruvbox-purple)]",
      render: (p: Position) => <NumericCell value={p.callQty} />,
    },
    {
      key: "putQty",
      header: "Put",
      sortable: true,
      align: "right" as const,
      className: "text-[var(--gruvbox-purple)]",
      render: (p: Position) => <NumericCell value={p.putQty} />,
    },
    {
      key: "stockPnl",
      header: "Stk PnL",
      sortable: true,
      align: "right" as const,
      render: (p: Position) => (
        <NumericCell value={p.stockPnl} format="currency" colorCode />
      ),
    },
    {
      key: "callPnl",
      header: "Call PnL",
      sortable: true,
      align: "right" as const,
      render: (p: Position) => (
        <NumericCell value={p.callPnl} format="currency" colorCode />
      ),
    },
    {
      key: "putPnl",
      header: "Put PnL",
      sortable: true,
      align: "right" as const,
      render: (p: Position) => (
        <NumericCell value={p.putPnl} format="currency" colorCode />
      ),
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">
          IBKR Positions
        </h1>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleImport}
            loading={importing}
          >
            Import
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleUpdateMtm}
            loading={updatingMtm}
          >
            Update MTM
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => router.push("/ibkr/trades")}
          >
            Trades
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => router.push("/ibkr/stats/daily")}
          >
            Stats
          </Button>
        </div>
      </div>

      <Table
        data={sortedPositions}
        columns={columns}
        onRowClick={(position) =>
          router.push(`/ibkr/positions/${position.symbol}`)
        }
        keyExtractor={(p) => p.symbol}
        emptyMessage="No positions found"
        sortKey={sortKey}
        sortDirection={sortDirection}
        onSort={handleSort}
      />

      {totals && (
        <div className="mt-4 p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
          <div className="grid grid-cols-2 gap-4 text-sm font-data">
            <div>
              <span className="text-[var(--gruvbox-fg4)]">Total Value:</span>{" "}
              <span className="text-[var(--gruvbox-fg)]">
                {totals.totalValue.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </span>
            </div>
            <div>
              <span className="text-[var(--gruvbox-fg4)]">Unrealized PnL:</span>{" "}
              <span
                className={
                  totals.totalUnrealizedPnl >= 0
                    ? "text-[var(--gruvbox-blue)]"
                    : "text-[var(--gruvbox-orange)]"
                }
              >
                {totals.totalUnrealizedPnl.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </span>
            </div>
            <div>
              <span className="text-[var(--gruvbox-fg4)]">Total MTM:</span>{" "}
              <span className="text-[var(--gruvbox-blue)]">
                {totals.totalMtm.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </span>
            </div>
            <div>
              <span className="text-[var(--gruvbox-fg4)]">Realized PnL:</span>{" "}
              <span
                className={
                  totals.totalStockPnl + totals.totalCallPnl + totals.totalPutPnl >= 0
                    ? "text-[var(--gruvbox-blue)]"
                    : "text-[var(--gruvbox-orange)]"
                }
              >
                {(
                  totals.totalStockPnl +
                  totals.totalCallPnl +
                  totals.totalPutPnl
                ).toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </span>
            </div>
            <div>
              <span className="text-[var(--gruvbox-fg4)]">Call Unrlzd:</span>{" "}
              <span
                className={
                  totals.totalCallUnrealizedPnl >= 0
                    ? "text-[var(--gruvbox-blue)]"
                    : "text-[var(--gruvbox-orange)]"
                }
              >
                {totals.totalCallUnrealizedPnl.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </span>
            </div>
            <div>
              <span className="text-[var(--gruvbox-fg4)]">Put Unrlzd:</span>{" "}
              <span
                className={
                  totals.totalPutUnrealizedPnl >= 0
                    ? "text-[var(--gruvbox-blue)]"
                    : "text-[var(--gruvbox-orange)]"
                }
              >
                {totals.totalPutUnrealizedPnl.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
