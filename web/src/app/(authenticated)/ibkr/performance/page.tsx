"use client";

import { useState, useEffect, useCallback } from "react";
import { supabase, toCamelCaseArray } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { Trade } from "@/types";
import { calculatePnL } from "@/lib/utils/fifo";
import { Spinner } from "@/components/ui/Spinner";
import { IBKRMenu } from "@/components/layout/IBKRMenu";
import { formatCurrency, formatDate, formatPercent } from "@/lib/utils/format";

interface NavRow {
  date: string;
  total: number | null;
  deposits_withdrawals: number | null;
}

interface Performance {
  startDate: string;
  endDate: string;
  startingValue: number;
  endingValue: number;
  netFlows: number;
  baseValue: number;
  netProfit: number;
  performancePct: number | null;
}

/**
 * Total performance derived from the NAV series.
 *
 * Deposits/withdrawals are not profit, so they are removed from the gain and
 * folded into the capital base — mirroring the CLI's methodology
 * (base = starting value + net flows; performance = profit / base).
 *
 * The starting NAV is the first reported total (its end-of-day value already
 * reflects any deposit made on the start date), so only flows *after* the start
 * date are counted.
 */
function computePerformance(rows: NavRow[]): Performance | null {
  const readings = rows.filter((r) => r.total != null);
  if (readings.length < 2) return null;

  const start = readings[0];
  const end = readings[readings.length - 1];
  const startingValue = Number(start.total);
  const endingValue = Number(end.total);

  const netFlows = rows
    .filter((r) => r.date > start.date && r.date <= end.date)
    .reduce((sum, r) => sum + (r.deposits_withdrawals ?? 0), 0);

  const netProfit = endingValue - startingValue - netFlows;
  const baseValue = startingValue + netFlows;

  return {
    startDate: start.date,
    endDate: end.date,
    startingValue,
    endingValue,
    netFlows,
    baseValue,
    netProfit,
    performancePct: baseValue !== 0 ? (netProfit / baseValue) * 100 : null,
  };
}

/** Tailwind text color for a signed value (positive = blue, negative = orange). */
function signColor(value: number): string {
  return value >= 0 ? "text-[var(--gruvbox-blue)]" : "text-[var(--gruvbox-orange)]";
}

export default function IBKRPerformancePage() {
  const { setError } = useError();
  const [perf, setPerf] = useState<Performance | null>(null);
  const [realizedPnl, setRealizedPnl] = useState(0);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      const [{ data: navData, error: navError }, { data: tradesData, error: tradesError }] =
        await Promise.all([
          supabase.from("nav").select("date, total, deposits_withdrawals").order("date"),
          supabase.from("trades").select("*").order("date_time"),
        ]);

      if (navError) throw navError;
      if (tradesError) throw tradesError;

      setPerf(computePerformance((navData || []) as NavRow[]));

      const trades = calculatePnL(
        toCamelCaseArray<Trade>(tradesData || []).filter((t) => t.symbol !== "USD.CAD")
      );
      setRealizedPnl(trades.reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <IBKRMenu />
        <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">Performance</h1>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Total performance % */}
        <div className="p-4 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
          <div className="text-sm font-semibold text-[var(--gruvbox-fg4)] mb-1">
            Total Performance
          </div>
          <div
            className={`text-3xl font-bold font-data ${
              perf?.performancePct != null ? signColor(perf.performancePct) : "text-[var(--gruvbox-fg4)]"
            }`}
          >
            {perf?.performancePct != null ? formatPercent(perf.performancePct) : "—"}
          </div>
          {perf && (
            <div className={`mt-1 font-data ${signColor(perf.netProfit)}`}>
              {formatCurrency(perf.netProfit)}
            </div>
          )}
        </div>

        {/* Total realized PnL from trades */}
        <div className="p-4 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
          <div className="text-sm font-semibold text-[var(--gruvbox-fg4)] mb-1">
            Total Realized PnL
          </div>
          <div className={`text-3xl font-bold font-data ${signColor(realizedPnl)}`}>
            {formatCurrency(realizedPnl)}
          </div>
          <div className="mt-1 text-xs text-[var(--gruvbox-fg4)]">from trades</div>
        </div>
      </div>

      {/* NAV breakdown */}
      {perf ? (
        <div className="mt-4 p-4 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
          <div className="text-sm font-semibold text-[var(--gruvbox-fg4)] mb-3">NAV Breakdown</div>
          <dl className="space-y-2 font-data text-sm">
            <Row label="Period Start" value={formatDate(perf.startDate)} />
            <Row label="Period End" value={formatDate(perf.endDate)} />
            <Row label="Starting Value" value={formatCurrency(perf.startingValue)} />
            <Row label="Ending NAV" value={formatCurrency(perf.endingValue)} />
            <Row label="Net Deposits / Withdrawals" value={formatCurrency(perf.netFlows)} />
            <Row label="Performance Base" value={formatCurrency(perf.baseValue)} />
            <Row
              label="Net Profit"
              value={formatCurrency(perf.netProfit)}
              valueClass={signColor(perf.netProfit)}
            />
          </dl>
        </div>
      ) : (
        <div className="mt-4 p-6 text-center text-[var(--gruvbox-fg4)]">
          Not enough NAV data to compute performance
        </div>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex justify-between items-center">
      <dt className="text-[var(--gruvbox-fg4)]">{label}</dt>
      <dd className={valueClass ?? "text-[var(--gruvbox-fg)]"}>{value}</dd>
    </div>
  );
}
