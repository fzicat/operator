"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { supabase } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { BitcoinBuy } from "@/types";
import { Table, NumericCell } from "@/components/ui/Table";
import { Spinner } from "@/components/ui/Spinner";
import { Select } from "@/components/ui/Select";
import { formatDate } from "@/lib/utils/format";
import { BitcoinMenu } from "@/components/layout/BitcoinMenu";

type SortDirection = "asc" | "desc";

export default function BitcoinPage() {
  const { setError } = useError();
  const [buys, setBuys] = useState<BitcoinBuy[]>([]);
  const [account, setAccount] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<string | null>("date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      const { data, error } = await supabase
        .from("bitcoin")
        .select("*")
        .order("date", { ascending: false });

      if (error) throw error;

      const processed = (data as BitcoinBuy[]).map((b) => ({
        ...b,
        sats: Math.round(b.quantity * 100_000_000),
        buy_price: b.quantity ? b.cost_cad / b.quantity : 0,
      }));

      setBuys(processed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const accountOptions = useMemo(() => {
    const accts = [...new Set(buys.map((b) => b.account))].sort();
    return [
      { value: "ALL", label: "All accounts" },
      ...accts.map((a) => ({ value: a, label: a })),
    ];
  }, [buys]);

  const filtered = useMemo(
    () => (account === "ALL" ? buys : buys.filter((b) => b.account === account)),
    [buys, account]
  );

  const handleSort = useCallback((key: string) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("desc");
    }
  }, [sortKey]);

  const sortedBuys = useMemo(() => {
    if (!sortKey) return filtered;
    const sorted = [...filtered].sort((a, b) => {
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
  }, [filtered, sortKey, sortDirection]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  const totalQty = filtered.reduce((s, b) => s + b.quantity, 0);
  const totalCost = filtered.reduce((s, b) => s + b.cost_cad, 0);
  const avgCost = totalQty ? totalCost / totalQty : 0;
  const totalSats = Math.round(totalQty * 100_000_000);

  const columns = [
    {
      key: "date",
      header: "Date",
      sortable: true,
      className: "text-[var(--gruvbox-fg4)]",
      render: (b: BitcoinBuy) => formatDate(b.date),
    },
    {
      key: "exchange",
      header: "Exchange",
      sortable: true,
      className: "text-[var(--gruvbox-aqua)]",
    },
    {
      key: "account",
      header: "Account",
      sortable: true,
      className: "text-[var(--gruvbox-purple)]",
    },
    {
      key: "quantity",
      header: "Quantity",
      sortable: true,
      align: "right" as const,
      render: (b: BitcoinBuy) => b.quantity.toFixed(8),
    },
    {
      key: "sats",
      header: "Sats",
      sortable: true,
      align: "right" as const,
      render: (b: BitcoinBuy) => (b.sats ?? 0).toLocaleString("en-US"),
    },
    {
      key: "cost_cad",
      header: "Cost CAD",
      sortable: true,
      align: "right" as const,
      className: "text-[var(--gruvbox-green)]",
      render: (b: BitcoinBuy) => <NumericCell value={b.cost_cad} format="currency" />,
    },
    {
      key: "buy_price",
      header: "Price CAD",
      sortable: true,
      align: "right" as const,
      className: "text-[var(--gruvbox-yellow)]",
      render: (b: BitcoinBuy) => <NumericCell value={b.buy_price} format="currency" />,
    },
    {
      key: "fees_cad",
      header: "Fees $",
      sortable: true,
      align: "right" as const,
      render: (b: BitcoinBuy) => <NumericCell value={b.fees_cad} format="currency" />,
    },
    {
      key: "notes",
      header: "Notes",
      className: "text-[var(--gruvbox-fg4)]",
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BitcoinMenu />
          <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">
            Bitcoin Buys
          </h1>
        </div>
        <Select
          options={accountOptions}
          value={account}
          onChange={(e) => setAccount(e.target.value)}
          className="w-auto"
        />
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
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
      </div>

      <Table
        data={sortedBuys}
        columns={columns}
        keyExtractor={(b) => b.id?.toString() || `${b.date}-${b.exchange}`}
        emptyMessage="No bitcoin buys"
        sortKey={sortKey}
        sortDirection={sortDirection}
        onSort={handleSort}
      />
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
