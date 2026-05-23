"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { supabase, toCamelCaseArray } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { Trade, WeeklyStat } from "@/types";
import { calculatePnL } from "@/lib/utils/fifo";
import { Table, NumericCell } from "@/components/ui/Table";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { IBKRMenu } from "@/components/layout/IBKRMenu";
import { formatDate, parseAsNY, addDaysToDateStr, getDayOfWeek } from "@/lib/utils/format";

/**
 * Given a YYYY-MM-DD string, return the week-ending Friday as YYYY-MM-DD.
 * Uses string-based date arithmetic to avoid DST drift.
 */
function getWeekEndingFridayStr(dateStr: string): string {
  const day = getDayOfWeek(dateStr); // 0=Sun, 5=Fri, 6=Sat
  const daysUntilFriday = day <= 5 ? 5 - day : 5 - day + 7;
  return addDaysToDateStr(dateStr, daysUntilFriday);
}

export default function WeeklyStatsPage() {
  const router = useRouter();
  const { setError } = useError();
  const [stats, setStats] = useState<WeeklyStat[]>([]);
  const [totalPnl, setTotalPnl] = useState(0);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      const { data: tradesData, error: tradesError } = await supabase
        .from("trades")
        .select("*")
        .order("date_time");

      if (tradesError) throw tradesError;

      let trades = toCamelCaseArray<Trade>(tradesData || []);
      trades = trades.filter((t) => t.symbol !== "USD.CAD");
      trades = calculatePnL(trades);

      // Group by week ending Friday — extract local date, then map to Friday
      const weeklyMap: Record<string, number> = {};
      for (const trade of trades) {
        const d = parseAsNY(trade.dateTime);
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        const tradeDateStr = `${y}-${m}-${day}`;
        const weekStr = getWeekEndingFridayStr(tradeDateStr);
        if (!weeklyMap[weekStr]) weeklyMap[weekStr] = 0;
        weeklyMap[weekStr] += trade.realized_pnl ?? 0;
      }

      // Start from the week of January 5, 2026 (ending Friday Jan 9)
      const startWeek = "2026-01-09";

      // Get all week-ending Fridays from startWeek to the latest week
      const allWeeks: string[] = Object.keys(weeklyMap).filter(w => w >= startWeek).sort();

      // Fill missing weeks between startWeek and the latest
      if (allWeeks.length > 0) {
        const lastWeek = allWeeks[allWeeks.length - 1];
        let currentWeek = startWeek;
        while (currentWeek <= lastWeek) {
          if (!weeklyMap[currentWeek]) weeklyMap[currentWeek] = 0;
          currentWeek = addDaysToDateStr(currentWeek, 7);
        }
      }

      // Convert to array, filter to start from startWeek
      const result: WeeklyStat[] = Object.entries(weeklyMap)
        .filter(([weekEnding]) => weekEnding >= startWeek)
        .map(([weekEnding, pnl]) => ({
          weekEnding,
          realizedPnl: pnl,
        }))
        .sort((a, b) => b.weekEnding.localeCompare(a.weekEnding));

      const total = result.reduce((sum, s) => sum + s.realizedPnl, 0);

      setStats(result);
      setTotalPnl(total);
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

  const columns = [
    {
      key: "weekEnding",
      header: "Week Ending",
      className: "text-[var(--gruvbox-aqua)]",
      render: (s: WeeklyStat) => formatDate(s.weekEnding),
    },
    {
      key: "realizedPnl",
      header: "Realized PnL",
      align: "right" as const,
      render: (s: WeeklyStat) => (
        <NumericCell value={s.realizedPnl} format="currency" colorCode />
      ),
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <IBKRMenu />
          <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">
            Weekly Stats (Ending Friday)
          </h1>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => router.push("/ibkr/stats/daily")}
        >
          Daily
        </Button>
      </div>

      <Table
        data={stats}
        columns={columns}
        keyExtractor={(s) => s.weekEnding}
        emptyMessage="No weekly stats available"
      />

      <div className="mt-4 p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
        {(() => {
          const avgPnl = stats.length > 0 ? totalPnl / stats.length : 0;
          return (
            <div className="flex justify-between items-center font-data mb-2">
              <span className="text-[var(--gruvbox-fg4)]">AVERAGE</span>
              <span
                className={avgPnl >= 0
                  ? "text-[var(--gruvbox-blue)]"
                  : "text-[var(--gruvbox-orange)]"}
              >
                {avgPnl.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
            </div>
          );
        })()}
        <div className="flex justify-between items-center font-data">
          <span className="text-[var(--gruvbox-fg4)] font-semibold">TOTAL</span>
          <span
            className={`text-lg font-bold ${totalPnl >= 0
              ? "text-[var(--gruvbox-blue)]"
              : "text-[var(--gruvbox-orange)]"
              }`}
          >
            {totalPnl.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
      </div>
    </div>
  );
}
