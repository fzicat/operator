"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { supabase, toCamelCaseArray } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { Trade } from "@/types";
import {
  isOptionTrade,
  calculatePnL,
  calculateOutstandingPremiumByDay,
  outstandingPremiumAsOf,
  calculateCashSecuredPutByDay,
  valueAsOf,
} from "@/lib/utils/fifo";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { IBKRMenu } from "@/components/layout/IBKRMenu";
import { OutstandingPremiumChart } from "@/components/ibkr/OutstandingPremiumChart";
import { DailyBarChart } from "@/components/ibkr/DailyBarChart";
import { addDaysToDateStr, getDayOfWeek, parseAsNY } from "@/lib/utils/format";

interface DailyPoint {
  date: string;
  pnl: number;
  csp: number;
  opCall: number;
  opPut: number;
  opTotal: number;
}

type RangeKey = "YTD" | "90D" | "30D" | "10D";

/** X-axis range options. `days` is the lookback window; null means year-to-date. */
const RANGES: { key: RangeKey; days: number | null }[] = [
  { key: "YTD", days: null },
  { key: "90D", days: 90 },
  { key: "30D", days: 30 },
  { key: "10D", days: 10 },
];

/** Local (NY) calendar date of a trade, as YYYY-MM-DD. */
function localDate(dateTime: string): string {
  const d = parseAsNY(dateTime);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export default function IBKRChartsPage() {
  const { setError } = useError();
  const [series, setSeries] = useState<DailyPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<RangeKey>("YTD");

  // Restrict the series to the selected x-axis range, measured back from the
  // latest data point so the charts always end on the most recent activity.
  const visibleSeries = useMemo(() => {
    if (series.length === 0) return series;
    const lastDate = series[series.length - 1].date;
    const days = RANGES.find((r) => r.key === range)?.days ?? null;
    const cutoff = days === null ? `${lastDate.slice(0, 4)}-01-01` : addDaysToDateStr(lastDate, -days);
    return series.filter((s) => s.date >= cutoff);
  }, [series, range]);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      const { data: tradesData, error: tradesError } = await supabase
        .from("trades")
        .select("*")
        .order("date_time");

      if (tradesError) throw tradesError;

      const allTrades = toCamelCaseArray<Trade>(tradesData || []);

      // Daily realized PnL — all instruments except the USD.CAD FX line.
      const pnlTrades = calculatePnL(allTrades.filter((t) => t.symbol !== "USD.CAD"));
      const pnlByDay: Record<string, number> = {};
      for (const t of pnlTrades) {
        const dateStr = localDate(t.dateTime);
        pnlByDay[dateStr] = (pnlByDay[dateStr] ?? 0) + (t.realized_pnl ?? 0);
      }

      // Option-based snapshots: outstanding short premium and cash-secured puts.
      const optionTrades = allTrades.filter((t) => isOptionTrade(t));
      const opPoints = calculateOutstandingPremiumByDay(optionTrades);
      const cspPoints = calculateCashSecuredPutByDay(optionTrades);

      // Days that had any real trade activity (excluding the FX line).
      const activeDates = new Set(
        allTrades.filter((t) => t.symbol !== "USD.CAD").map((t) => localDate(t.dateTime))
      );

      const sortedActive = [...activeDates].sort();
      if (sortedActive.length === 0) {
        setSeries([]);
        setLoading(false);
        return;
      }

      // Start from Monday January 5, 2026 (matches the other IBKR views).
      const startDateStr = "2026-01-05";
      const minDateStr = sortedActive[0] > startDateStr ? sortedActive[0] : startDateStr;
      const maxDateStr = sortedActive[sortedActive.length - 1];

      // Build a continuous series: every weekday, plus any day with activity.
      const result: DailyPoint[] = [];
      let currentDateStr = minDateStr;
      while (currentDateStr <= maxDateStr) {
        const dayOfWeek = getDayOfWeek(currentDateStr);
        const isWeekday = dayOfWeek !== 0 && dayOfWeek !== 6;

        if (isWeekday || activeDates.has(currentDateStr)) {
          const op = outstandingPremiumAsOf(opPoints, currentDateStr);
          result.push({
            date: currentDateStr,
            pnl: pnlByDay[currentDateStr] ?? 0,
            csp: valueAsOf(cspPoints, currentDateStr),
            opCall: op.call,
            opPut: op.put,
            opTotal: op.call + op.put,
          });
        }

        currentDateStr = addDaysToDateStr(currentDateStr, 1);
      }

      setSeries(result);
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
        <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">Charts</h1>
        <div className="ml-auto flex items-center gap-1">
          {RANGES.map((r) => (
            <Button
              key={r.key}
              size="sm"
              variant={range === r.key ? "primary" : "secondary"}
              onClick={() => setRange(r.key)}
            >
              {r.key}
            </Button>
          ))}
        </div>
      </div>

      {series.length === 0 ? (
        <div className="p-6 text-center text-[var(--gruvbox-fg4)]">No chart data available</div>
      ) : (
        <div className="space-y-4">
          <div className="p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
            <h2 className="text-sm font-semibold text-[var(--gruvbox-fg4)] mb-2">
              Outstanding Premium
            </h2>
            <OutstandingPremiumChart
              data={visibleSeries.map((s) => ({
                date: s.date,
                total: s.opTotal,
                call: s.opCall,
                put: s.opPut,
              }))}
              smaWindow={7}
            />
          </div>

          <div className="p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
            <h2 className="text-sm font-semibold text-[var(--gruvbox-fg4)] mb-2">Daily PnL</h2>
            <DailyBarChart
              data={visibleSeries.map((s) => ({ date: s.date, value: s.pnl }))}
              color="sign"
              valueLabel="PnL"
            />
          </div>

          <div className="p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
            <h2 className="text-sm font-semibold text-[var(--gruvbox-fg4)] mb-2">
              Daily Cash Secured Put
            </h2>
            <DailyBarChart
              data={visibleSeries.map((s) => ({ date: s.date, value: s.csp }))}
              color="var(--gruvbox-purple)"
              valueLabel="Cash Secured"
            />
          </div>
        </div>
      )}
    </div>
  );
}
