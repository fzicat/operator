"use client";

import { useState, useEffect, useCallback } from "react";
import { supabase, toCamelCaseArray } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { Trade } from "@/types";
import { calculatePnL } from "@/lib/utils/fifo";
import { Spinner } from "@/components/ui/Spinner";
import { IBKRMenu } from "@/components/layout/IBKRMenu";
import { formatCurrency, formatDate, formatPercent, parseAsNY } from "@/lib/utils/format";

interface NavRow {
  date: string;
  total: number | null;
  deposits_withdrawals: number | null;
}

/** A return expressed both since-inception (cumulative) and annualized. */
interface ReturnResult {
  period: number; // fraction, e.g. 0.123 = +12.3%
  annualized: number | null;
}

interface Performance {
  startDate: string;
  endDate: string;
  startingValue: number;
  endingValue: number;
  netFlows: number;
  baseValue: number;
  netProfit: number;
  twr: ReturnResult | null;
  mwr: ReturnResult | null;
}

/** Whole days between two YYYY-MM-DD strings (local, DST-safe via parseAsNY). */
function daysBetween(a: string, b: string): number {
  return Math.round((parseAsNY(b).getTime() - parseAsNY(a).getTime()) / 86_400_000);
}

/** Sum of deposits/withdrawals on dates in the half-open interval (after, to]. */
function flowsBetween(rows: NavRow[], after: string, to: string): number {
  return rows
    .filter((r) => r.date > after && r.date <= to)
    .reduce((sum, r) => sum + (r.deposits_withdrawals ?? 0), 0);
}

function annualize(growthFactor: number, days: number): number | null {
  if (days <= 0 || growthFactor <= 0) return null;
  return Math.pow(growthFactor, 365 / days) - 1;
}

/**
 * Time-Weighted Return — chain-links the return of each sub-period between
 * consecutive NAV readings, removing the effect of when money flowed in or out.
 * A deposit on day D is treated as arriving at the end of its sub-period (the
 * reported NAV is end-of-day), so the capital base for that sub-period is the
 * prior reading.
 */
function computeTWR(rows: NavRow[], readings: NavRow[]): ReturnResult | null {
  if (readings.length < 2) return null;

  let factor = 1;
  for (let i = 1; i < readings.length; i++) {
    const prev = Number(readings[i - 1].total);
    if (prev === 0) continue; // undefined sub-period return — skip it
    const flows = flowsBetween(rows, readings[i - 1].date, readings[i].date);
    const subReturn = (Number(readings[i].total) - flows - prev) / prev;
    factor *= 1 + subReturn;
  }

  const days = daysBetween(readings[0].date, readings[readings.length - 1].date);
  return { period: factor - 1, annualized: annualize(factor, days) };
}

/**
 * Money-Weighted Return — the internal rate of return (IRR) that discounts all
 * cash flows to zero. Cash flows, from the investor's perspective:
 *   day 0      : −startingValue        (capital already at work)
 *   each flow  : −depositsWithdrawals  (deposit out of pocket, withdrawal in)
 *   final day  : +endingValue          (as if liquidated)
 * Solved by bisection on the daily rate.
 */
function computeMWR(rows: NavRow[], readings: NavRow[]): ReturnResult | null {
  if (readings.length < 2) return null;

  const start = readings[0];
  const end = readings[readings.length - 1];
  const days = daysBetween(start.date, end.date);
  if (days <= 0) return null;

  const flows: { t: number; amount: number }[] = [{ t: 0, amount: -Number(start.total) }];
  for (const r of rows) {
    if (r.date > start.date && r.date <= end.date && r.deposits_withdrawals) {
      flows.push({ t: daysBetween(start.date, r.date), amount: -r.deposits_withdrawals });
    }
  }
  flows.push({ t: days, amount: Number(end.total) });

  const npv = (rate: number) =>
    flows.reduce((sum, cf) => sum + cf.amount / Math.pow(1 + rate, cf.t), 0);

  // Bracket the daily rate, then bisect. The cash-flow shape (initial outflow,
  // terminal inflow) gives a single sign change in this range for normal data.
  let lo = -0.9;
  let hi = 10;
  let flo = npv(lo);
  let fhi = npv(hi);
  if (flo === 0) return rateToReturns(lo, days);
  if (fhi === 0) return rateToReturns(hi, days);
  if (flo * fhi > 0) return null; // can't bracket a root — don't report a guess

  for (let i = 0; i < 200; i++) {
    const mid = (lo + hi) / 2;
    const fmid = npv(mid);
    if (Math.abs(fmid) < 1e-7 || hi - lo < 1e-12) return rateToReturns(mid, days);
    if (flo * fmid < 0) {
      hi = mid;
      fhi = fmid;
    } else {
      lo = mid;
      flo = fmid;
    }
  }
  return rateToReturns((lo + hi) / 2, days);
}

/** Convert a solved daily IRR into period (since-inception) and annualized returns. */
function rateToReturns(daily: number, days: number): ReturnResult {
  return {
    period: Math.pow(1 + daily, days) - 1,
    annualized: Math.pow(1 + daily, 365) - 1,
  };
}

/**
 * Build the performance summary from the NAV series. The starting value is the
 * first reported total (its end-of-day value already includes any deposit on the
 * start date), so only flows *after* the start date are netted out.
 */
function computePerformance(rows: NavRow[]): Performance | null {
  const readings = rows.filter((r) => r.total != null);
  if (readings.length < 2) return null;

  const start = readings[0];
  const end = readings[readings.length - 1];
  const startingValue = Number(start.total);
  const endingValue = Number(end.total);
  const netFlows = flowsBetween(rows, start.date, end.date);

  return {
    startDate: start.date,
    endDate: end.date,
    startingValue,
    endingValue,
    netFlows,
    baseValue: startingValue + netFlows,
    netProfit: endingValue - startingValue - netFlows,
    twr: computeTWR(rows, readings),
    mwr: computeMWR(rows, readings),
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

      <div className="grid gap-4 sm:grid-cols-3">
        <ReturnCard title="TWR" subtitle="Time-Weighted" result={perf?.twr ?? null} />
        <ReturnCard title="MWR" subtitle="Money-Weighted (IRR)" result={perf?.mwr ?? null} />

        <div className="p-4 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
          <div className="text-sm font-semibold text-[var(--gruvbox-fg4)]">Total Realized PnL</div>
          <div className="text-xs text-[var(--gruvbox-fg4)] mb-2">from trades</div>
          <div className={`text-3xl font-bold font-data ${signColor(realizedPnl)}`}>
            {formatCurrency(realizedPnl)}
          </div>
        </div>
      </div>

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

      <p className="mt-4 text-xs text-[var(--gruvbox-fg4)] leading-relaxed">
        <span className="text-[var(--gruvbox-fg3)]">TWR</span> chain-links each sub-period&rsquo;s
        return, removing the effect of deposit/withdrawal timing — it measures the strategy.{" "}
        <span className="text-[var(--gruvbox-fg3)]">MWR</span> is the IRR over the actual cash flows
        — it reflects your dollar-weighted result. Large figure is since inception; the smaller line
        is the annualized equivalent.
      </p>
    </div>
  );
}

function ReturnCard({
  title,
  subtitle,
  result,
}: {
  title: string;
  subtitle: string;
  result: ReturnResult | null;
}) {
  return (
    <div className="p-4 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
      <div className="text-sm font-semibold text-[var(--gruvbox-fg4)]">{title}</div>
      <div className="text-xs text-[var(--gruvbox-fg4)] mb-2">{subtitle}</div>
      <div
        className={`text-3xl font-bold font-data ${
          result ? signColor(result.period) : "text-[var(--gruvbox-fg4)]"
        }`}
      >
        {result ? formatPercent(result.period * 100) : "—"}
      </div>
      <div className="mt-1 text-xs font-data text-[var(--gruvbox-fg4)]">
        {result?.annualized != null
          ? `${formatPercent(result.annualized * 100)} annualized`
          : " "}
      </div>
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
