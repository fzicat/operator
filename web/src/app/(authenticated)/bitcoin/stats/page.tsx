"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { supabase } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { BitcoinBuy, BitcoinSummary } from "@/types";
import { Table, NumericCell } from "@/components/ui/Table";
import { Spinner } from "@/components/ui/Spinner";
import { BitcoinMenu } from "@/components/layout/BitcoinMenu";
import { parseAsNY } from "@/lib/utils/format";

function summarize(
  buys: BitcoinBuy[],
  keyFn: (b: BitcoinBuy) => string
): BitcoinSummary[] {
  const map: Record<string, { buys: number; quantity: number; cost: number }> = {};
  for (const b of buys) {
    const k = keyFn(b);
    if (!map[k]) map[k] = { buys: 0, quantity: 0, cost: 0 };
    map[k].buys += 1;
    map[k].quantity += b.quantity;
    map[k].cost += b.cost_cad;
  }
  return Object.entries(map)
    .map(([name, v]) => ({
      name,
      buys: v.buys,
      quantity: v.quantity,
      cost: v.cost,
      avgCost: v.quantity ? v.cost / v.quantity : 0,
    }))
    .sort((a, b) => b.cost - a.cost);
}

export default function BitcoinStatsPage() {
  const { setError } = useError();
  const [buys, setBuys] = useState<BitcoinBuy[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const { data, error } = await supabase
        .from("bitcoin")
        .select("*")
        .order("date", { ascending: false });
      if (error) throw error;
      setBuys(data as BitcoinBuy[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const byAccount = useMemo(() => summarize(buys, (b) => b.account), [buys]);
  const byExchange = useMemo(() => summarize(buys, (b) => b.exchange), [buys]);
  const byYear = useMemo(
    () =>
      summarize(buys, (b) => String(parseAsNY(b.date).getFullYear())).sort(
        (a, b) => b.name.localeCompare(a.name)
      ),
    [buys]
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  const totalQty = buys.reduce((s, b) => s + b.quantity, 0);
  const totalCost = buys.reduce((s, b) => s + b.cost_cad, 0);
  const avgCost = totalQty ? totalCost / totalQty : 0;
  const totalSats = Math.round(totalQty * 100_000_000);
  const totalFees = buys.reduce((s, b) => s + (b.fees_cad || 0), 0);

  const totalRow: BitcoinSummary = {
    name: "Total",
    buys: buys.length,
    quantity: totalQty,
    cost: totalCost,
    avgCost,
  };

  const summaryColumns = [
    { key: "name", header: "Name" },
    {
      key: "buys",
      header: "Buys",
      align: "right" as const,
      render: (s: BitcoinSummary) => s.buys.toLocaleString("en-US"),
    },
    {
      key: "quantity",
      header: "BTC",
      align: "right" as const,
      render: (s: BitcoinSummary) => s.quantity.toFixed(8),
    },
    {
      key: "cost",
      header: "Cost CAD",
      align: "right" as const,
      className: "text-[var(--gruvbox-green)]",
      render: (s: BitcoinSummary) => <NumericCell value={s.cost} format="currency" />,
    },
    {
      key: "avgCost",
      header: "Avg Cost",
      align: "right" as const,
      className: "text-[var(--gruvbox-yellow)]",
      render: (s: BitcoinSummary) => <NumericCell value={s.avgCost} format="currency" />,
    },
  ];

  const rowClassName = (s: BitcoinSummary) =>
    s.name === "Total"
      ? "font-bold !bg-[var(--gruvbox-bg1)] border-t border-[var(--gruvbox-bg3)]"
      : "";

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <BitcoinMenu />
        <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">
          Bitcoin Stats
        </h1>
      </div>

      {/* Overall summary */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <SummaryCard label="Total Buys" value={buys.length.toLocaleString("en-US")} />
        <SummaryCard label="Total BTC" value={totalQty.toFixed(8)} />
        <SummaryCard label="Total Sats" value={totalSats.toLocaleString("en-US")} />
        <SummaryCard
          label="Total Cost CAD"
          value={totalCost.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          highlight
        />
        <SummaryCard
          label="Avg Cost CAD/BTC"
          value={avgCost.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          highlight
        />
        <SummaryCard
          label="Total Fees CAD"
          value={totalFees.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        />
      </div>

      {/* Breakdown tables */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div>
          <h2 className="text-lg font-semibold text-[var(--gruvbox-yellow)] mb-2">
            By Account
          </h2>
          <Table
            data={[...byAccount, totalRow]}
            columns={summaryColumns}
            keyExtractor={(s) => s.name}
            rowClassName={rowClassName}
          />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-[var(--gruvbox-yellow)] mb-2">
            By Exchange
          </h2>
          <Table
            data={[...byExchange, totalRow]}
            columns={summaryColumns}
            keyExtractor={(s) => s.name}
            rowClassName={rowClassName}
          />
        </div>
      </div>

      <div className="mb-6">
        <h2 className="text-lg font-semibold text-[var(--gruvbox-yellow)] mb-2">
          By Year
        </h2>
        <Table
          data={[...byYear, totalRow]}
          columns={summaryColumns}
          keyExtractor={(s) => s.name}
          rowClassName={rowClassName}
        />
      </div>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="p-3 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)]">
      <div className="text-xs text-[var(--gruvbox-fg4)] mb-1">{label}</div>
      <div
        className={`font-data text-lg ${
          highlight ? "text-[var(--gruvbox-green)] font-bold" : "text-[var(--gruvbox-fg)]"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
