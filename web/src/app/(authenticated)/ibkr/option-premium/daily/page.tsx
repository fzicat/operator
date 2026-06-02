"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { supabase, toCamelCaseArray } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { Trade, OptionPremiumDaily } from "@/types";
import {
  isOptionTrade,
  calculateClosedOpenPremium,
  calculateOutstandingPremiumByDay,
  outstandingPremiumAsOf,
} from "@/lib/utils/fifo";
import { Table, NumericCell } from "@/components/ui/Table";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { IBKRMenu } from "@/components/layout/IBKRMenu";
import { formatDate, getDayName, addDaysToDateStr, getDayOfWeek, parseAsNY } from "@/lib/utils/format";

/**
 * Premium for an option trade, using the same sign convention as `credit`:
 * selling to open yields a positive (collected) premium, buying yields negative.
 */
function tradePremium(trade: Trade): number {
  const multiplier = trade.multiplier ?? 100;
  return -(trade.quantity ?? 0) * (trade.tradePrice ?? 0) * multiplier;
}

export default function OptionPremiumDailyPage() {
  const router = useRouter();
  const { setError } = useError();
  const [stats, setStats] = useState<OptionPremiumDaily[]>([]);
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

      // Outstanding short option premium snapshots (CLI "OP" command)
      const opPoints = calculateOutstandingPremiumByDay(trades);

      // Group by date — use parseAsNY to extract the local date
      const dailyMap: Record<string, { open: number; close: number; closedOpen: number }> = {};
      for (const trade of trades) {
        const d = parseAsNY(trade.dateTime);
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        const dateStr = `${y}-${m}-${day}`;
        if (!dailyMap[dateStr]) dailyMap[dateStr] = { open: 0, close: 0, closedOpen: 0 };

        const premium = tradePremium(trade);
        if (trade.openCloseIndicator === "O") {
          dailyMap[dateStr].open += premium;
        } else if (trade.openCloseIndicator === "C") {
          dailyMap[dateStr].close += premium;
        }
        dailyMap[dateStr].closedOpen += trade.closed_open_premium ?? 0;
      }

      const dates = Object.keys(dailyMap).sort();
      if (dates.length === 0) {
        setStats([]);
        setTotalOpen(0);
        setTotalClose(0);
        setTotalClosedOpen(0);
        setLoading(false);
        return;
      }

      // Start from Monday January 5, 2026
      const startDateStr = "2026-01-05";
      const minDateStr = dates[0] > startDateStr ? dates[0] : startDateStr;
      const maxDateStr = dates[dates.length - 1];

      const result: OptionPremiumDaily[] = [];
      let openTotal = 0;
      let closeTotal = 0;
      let closedOpenTotal = 0;

      let currentDateStr = minDateStr;
      while (currentDateStr <= maxDateStr) {
        const dayOfWeek = getDayOfWeek(currentDateStr);
        const entry = dailyMap[currentDateStr] ?? { open: 0, close: 0, closedOpen: 0 };

        // Include if weekday OR if has any premium activity
        if (
          (dayOfWeek !== 0 && dayOfWeek !== 6) ||
          entry.open !== 0 ||
          entry.close !== 0 ||
          entry.closedOpen !== 0
        ) {
          const op = outstandingPremiumAsOf(opPoints, currentDateStr);
          result.push({
            date: currentDateStr,
            dayName: getDayName(currentDateStr),
            open: entry.open,
            close: entry.close,
            closedOpen: entry.closedOpen,
            opCall: op.call,
            opPut: op.put,
            opTotal: op.call + op.put,
          });
          openTotal += entry.open;
          closeTotal += entry.close;
          closedOpenTotal += entry.closedOpen;
        }

        currentDateStr = addDaysToDateStr(currentDateStr, 1);
      }

      // Reverse to show most recent first
      result.reverse();

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
      key: "date",
      header: "Date",
      className: "text-[var(--gruvbox-aqua)]",
      render: (s: OptionPremiumDaily) => formatDate(s.date),
    },
    {
      key: "dayName",
      header: "Day",
      className: "text-[var(--gruvbox-yellow)]",
    },
    {
      key: "open",
      header: "Open",
      align: "right" as const,
      render: (s: OptionPremiumDaily) => (
        <NumericCell value={s.open} format="currency" colorCode />
      ),
    },
    {
      key: "close",
      header: "Close",
      align: "right" as const,
      render: (s: OptionPremiumDaily) => (
        <NumericCell value={s.close} format="currency" colorCode />
      ),
    },
    {
      key: "closedOpen",
      header: "Open Prem Closed",
      align: "right" as const,
      render: (s: OptionPremiumDaily) => (
        <NumericCell value={s.closedOpen} format="currency" colorCode />
      ),
    },
    {
      key: "opCall",
      header: "Calls",
      align: "right" as const,
      className: "text-[var(--gruvbox-red)]",
      render: (s: OptionPremiumDaily) => (
        <NumericCell value={s.opCall} format="currency" />
      ),
    },
    {
      key: "opPut",
      header: "Puts",
      align: "right" as const,
      className: "text-[var(--gruvbox-green)]",
      render: (s: OptionPremiumDaily) => (
        <NumericCell value={s.opPut} format="currency" />
      ),
    },
    {
      key: "opTotal",
      header: "Total OP",
      align: "right" as const,
      className: "text-[var(--gruvbox-yellow)]",
      render: (s: OptionPremiumDaily) => (
        <NumericCell value={s.opTotal} format="currency" />
      ),
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <IBKRMenu />
          <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">
            Option Premium (Daily)
          </h1>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => router.push("/ibkr/option-premium/weekly")}
        >
          Weekly
        </Button>
      </div>

      <Table
        data={stats}
        columns={columns}
        keyExtractor={(s) => s.date}
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
