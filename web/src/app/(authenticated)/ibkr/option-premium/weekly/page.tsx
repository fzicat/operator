"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { supabase, toCamelCaseArray } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { Trade, OptionPremiumWeekly } from "@/types";
import { isOptionTrade, calculateClosedOpenPremium } from "@/lib/utils/fifo";
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

/**
 * Premium for an option trade, using the same sign convention as `credit`:
 * selling to open yields a positive (collected) premium, buying yields negative.
 */
function tradePremium(trade: Trade): number {
  const multiplier = trade.multiplier ?? 100;
  return -(trade.quantity ?? 0) * (trade.tradePrice ?? 0) * multiplier;
}

export default function OptionPremiumWeeklyPage() {
  const router = useRouter();
  const { setError } = useError();
  const [stats, setStats] = useState<OptionPremiumWeekly[]>([]);
  const [totalOpen, setTotalOpen] = useState(0);
  const [totalClose, setTotalClose] = useState(0);
  const [totalClosedOpen, setTotalClosedOpen] = useState(0);
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
      trades = trades.filter((t) => isOptionTrade(t));
      trades = calculateClosedOpenPremium(trades);

      // Group by week ending Friday — extract local date, then map to Friday
      const weeklyMap: Record<string, { open: number; close: number; closedOpen: number }> = {};
      for (const trade of trades) {
        const d = parseAsNY(trade.dateTime);
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        const tradeDateStr = `${y}-${m}-${day}`;
        const weekStr = getWeekEndingFridayStr(tradeDateStr);
        if (!weeklyMap[weekStr]) weeklyMap[weekStr] = { open: 0, close: 0, closedOpen: 0 };

        const premium = tradePremium(trade);
        if (trade.openCloseIndicator === "O") {
          weeklyMap[weekStr].open += premium;
        } else if (trade.openCloseIndicator === "C") {
          weeklyMap[weekStr].close += premium;
        }
        weeklyMap[weekStr].closedOpen += trade.closed_open_premium ?? 0;
      }

      // Start from the week of January 5, 2026 (ending Friday Jan 9)
      const startWeek = "2026-01-09";

      // Get all week-ending Fridays from startWeek to the latest week
      const allWeeks: string[] = Object.keys(weeklyMap).filter((w) => w >= startWeek).sort();

      // Fill missing weeks between startWeek and the latest
      if (allWeeks.length > 0) {
        const lastWeek = allWeeks[allWeeks.length - 1];
        let currentWeek = startWeek;
        while (currentWeek <= lastWeek) {
          if (!weeklyMap[currentWeek]) weeklyMap[currentWeek] = { open: 0, close: 0, closedOpen: 0 };
          currentWeek = addDaysToDateStr(currentWeek, 7);
        }
      }

      // Convert to array, filter to start from startWeek
      const result: OptionPremiumWeekly[] = Object.entries(weeklyMap)
        .filter(([weekEnding]) => weekEnding >= startWeek)
        .map(([weekEnding, v]) => ({
          weekEnding,
          open: v.open,
          close: v.close,
          closedOpen: v.closedOpen,
        }))
        .sort((a, b) => b.weekEnding.localeCompare(a.weekEnding));

      const openTotal = result.reduce((sum, s) => sum + s.open, 0);
      const closeTotal = result.reduce((sum, s) => sum + s.close, 0);
      const closedOpenTotal = result.reduce((sum, s) => sum + s.closedOpen, 0);

      setStats(result);
      setTotalOpen(openTotal);
      setTotalClose(closeTotal);
      setTotalClosedOpen(closedOpenTotal);
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
      render: (s: OptionPremiumWeekly) => formatDate(s.weekEnding),
    },
    {
      key: "open",
      header: "Open",
      align: "right" as const,
      render: (s: OptionPremiumWeekly) => (
        <NumericCell value={s.open} format="currency" colorCode />
      ),
    },
    {
      key: "close",
      header: "Close",
      align: "right" as const,
      render: (s: OptionPremiumWeekly) => (
        <NumericCell value={s.close} format="currency" colorCode />
      ),
    },
    {
      key: "closedOpen",
      header: "Open Prem Closed",
      align: "right" as const,
      render: (s: OptionPremiumWeekly) => (
        <NumericCell value={s.closedOpen} format="currency" colorCode />
      ),
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <IBKRMenu />
          <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">
            Option Premium (Weekly, Ending Friday)
          </h1>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => router.push("/ibkr/option-premium/daily")}
        >
          Daily
        </Button>
      </div>

      <Table
        data={stats}
        columns={columns}
        keyExtractor={(s) => s.weekEnding}
        emptyMessage="No option premium data available"
      />

      <div className="mt-4 p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
        <div className="flex justify-between items-center font-data mb-2">
          <span className="text-[var(--gruvbox-fg4)] font-semibold">TOTAL OPEN</span>
          <span
            className={`text-lg font-bold ${totalOpen >= 0
              ? "text-[var(--gruvbox-blue)]"
              : "text-[var(--gruvbox-orange)]"
              }`}
          >
            {totalOpen.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
        <div className="flex justify-between items-center font-data mb-2">
          <span className="text-[var(--gruvbox-fg4)] font-semibold">TOTAL CLOSE</span>
          <span
            className={`text-lg font-bold ${totalClose >= 0
              ? "text-[var(--gruvbox-blue)]"
              : "text-[var(--gruvbox-orange)]"
              }`}
          >
            {totalClose.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
        <div className="flex justify-between items-center font-data">
          <span className="text-[var(--gruvbox-fg4)] font-semibold">TOTAL OPEN PREM CLOSED</span>
          <span
            className={`text-lg font-bold ${totalClosedOpen >= 0
              ? "text-[var(--gruvbox-blue)]"
              : "text-[var(--gruvbox-orange)]"
              }`}
          >
            {totalClosedOpen.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
        </div>
      </div>
    </div>
  );
}
