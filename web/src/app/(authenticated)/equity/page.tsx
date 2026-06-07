"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { supabase } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { EquityEntry, EquitySummary } from "@/types";
import { Table, NumericCell } from "@/components/ui/Table";
import { Spinner } from "@/components/ui/Spinner";
import { Select } from "@/components/ui/Select";
import { formatDate } from "@/lib/utils/format";
import { EquityMenu } from "@/components/layout/EquityMenu";

type SortDirection = "asc" | "desc";

export default function EquityPage() {
  const { setError } = useError();
  const [entries, setEntries] = useState<EquityEntry[]>([]);
  const [accountSummary, setAccountSummary] = useState<EquitySummary[]>([]);
  const [categorySummary, setCategorySummary] = useState<EquitySummary[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [uniqueDates, setUniqueDates] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      const { data, error } = await supabase
        .from("equity")
        .select("*")
        .order("date", { ascending: false });

      if (error) throw error;

      const rawEntries = data as EquityEntry[];

      // Process entries - calculate balance_cad and balance_net
      const processedEntries = rawEntries.map((entry) => {
        let balanceCad = entry.balance * entry.rate;

        // Special handling for SAT (Satoshis)
        if (entry.currency === "SAT") {
          balanceCad = balanceCad / 100_000_000;
        }

        const balanceNet = balanceCad * (1 - entry.tax);

        return {
          ...entry,
          balance_cad: balanceCad,
          balance_net: balanceNet,
        };
      });

      // Sort by description
      processedEntries.sort((a, b) =>
        a.description.toLowerCase().localeCompare(b.description.toLowerCase())
      );

      // Get unique dates
      const dates = [...new Set(processedEntries.map((e) => e.date))].sort(
        (a, b) => b.localeCompare(a)
      );
      setUniqueDates(dates);

      // Default to most recent date
      if (dates.length > 0 && !selectedDate) {
        setSelectedDate(dates[0]);
      }

      setEntries(processedEntries);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [setError, selectedDate]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Calculate summaries when date changes
  useEffect(() => {
    if (!selectedDate) return;

    const filtered = entries.filter((e) => e.date === selectedDate);

    // By Account
    const accountMap: Record<string, { cad: number; net: number }> = {};
    for (const entry of filtered) {
      if (!accountMap[entry.account]) {
        accountMap[entry.account] = { cad: 0, net: 0 };
      }
      accountMap[entry.account].cad += entry.balance_cad || 0;
      accountMap[entry.account].net += entry.balance_net || 0;
    }
    const accountSumm = Object.entries(accountMap)
      .map(([name, vals]) => ({
        name,
        balanceCad: vals.cad,
        balanceNet: vals.net,
      }))
      .sort((a, b) => b.balanceNet - a.balanceNet);
    setAccountSummary(accountSumm);

    // By Category
    const categoryMap: Record<string, { cad: number; net: number }> = {};
    for (const entry of filtered) {
      if (!categoryMap[entry.category]) {
        categoryMap[entry.category] = { cad: 0, net: 0 };
      }
      categoryMap[entry.category].cad += entry.balance_cad || 0;
      categoryMap[entry.category].net += entry.balance_net || 0;
    }
    const categorySumm = Object.entries(categoryMap)
      .map(([name, vals]) => ({
        name,
        balanceCad: vals.cad,
        balanceNet: vals.net,
      }))
      .sort((a, b) => b.balanceNet - a.balanceNet);
    setCategorySummary(categorySumm);
  }, [selectedDate, entries]);

  const handleSort = useCallback((key: string) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("desc");
    }
  }, [sortKey]);

  const filteredEntries = useMemo(() =>
    entries.filter((e) => e.date === selectedDate),
    [entries, selectedDate]
  );

  const sortedEntries = useMemo(() => {
    if (!sortKey) return filteredEntries;
    const sorted = [...filteredEntries].sort((a, b) => {
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
  }, [filteredEntries, sortKey, sortDirection]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Spinner size="lg" />
      </div>
    );
  }

  const totalCad = filteredEntries.reduce((sum, e) => sum + (e.balance_cad || 0), 0);
  const totalNet = filteredEntries.reduce((sum, e) => sum + (e.balance_net || 0), 0);

  const entryColumns = [
    {
      key: "account",
      header: "Account",
      sortable: true,
      className: "text-[var(--gruvbox-aqua)]",
    },
    {
      key: "category",
      header: "Category",
      sortable: true,
      className: "text-[var(--gruvbox-purple)]",
    },
    { key: "description", header: "Description", sortable: true },
    { key: "currency", header: "Curr", sortable: true },
    {
      key: "balance",
      header: "Balance",
      sortable: true,
      align: "right" as const,
      render: (e: EquityEntry) => <NumericCell value={e.balance} format="currency" />,
    },
    {
      key: "rate",
      header: "Rate",
      sortable: true,
      align: "right" as const,
      render: (e: EquityEntry) => e.rate.toFixed(4),
    },
    {
      key: "balance_cad",
      header: "Bal CAD",
      sortable: true,
      align: "right" as const,
      className: "text-[var(--gruvbox-green)]",
      render: (e: EquityEntry) => <NumericCell value={e.balance_cad} format="currency" />,
    },
    {
      key: "tax",
      header: "Tax",
      sortable: true,
      align: "right" as const,
      render: (e: EquityEntry) => (e.tax * 100).toFixed(0) + "%",
    },
    {
      key: "balance_net",
      header: "Bal Net",
      sortable: true,
      align: "right" as const,
      className: "text-[var(--gruvbox-green)] font-bold",
      render: (e: EquityEntry) => <NumericCell value={e.balance_net} format="currency" />,
    },
  ];

  const summaryColumns = [
    { key: "name", header: "Name" },
    {
      key: "balanceCad",
      header: "Balance Gross",
      align: "right" as const,
      className: "text-[var(--gruvbox-green)]",
      render: (s: EquitySummary) => <NumericCell value={s.balanceCad} format="currency" />,
    },
    {
      key: "balanceNet",
      header: "Balance Net",
      align: "right" as const,
      className: "text-[var(--gruvbox-green)] font-bold",
      render: (s: EquitySummary) => <NumericCell value={s.balanceNet} format="currency" />,
    },
  ];

  const totalRow: EquitySummary = {
    name: "Total",
    balanceCad: totalCad,
    balanceNet: totalNet,
  };
  const accountSummaryRows = [...accountSummary, totalRow];
  const categorySummaryRows = [...categorySummary, totalRow];
  const summaryRowClassName = (s: EquitySummary) =>
    s.name === "Total"
      ? "font-bold !bg-[var(--gruvbox-bg1)] border-t border-[var(--gruvbox-bg3)]"
      : "";

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <EquityMenu />
          <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">
            Equity Overview
          </h1>
        </div>
        <Select
          options={uniqueDates.map((date) => ({
            value: date,
            label: formatDate(date),
          }))}
          value={selectedDate || ""}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="w-auto"
        />
      </div>

      {/* Summaries */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div>
          <h2 className="text-lg font-semibold text-[var(--gruvbox-yellow)] mb-2">
            By Account
          </h2>
          <Table
            data={accountSummaryRows}
            columns={summaryColumns}
            keyExtractor={(s) => s.name}
            rowClassName={summaryRowClassName}
          />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-[var(--gruvbox-yellow)] mb-2">
            By Category
          </h2>
          <Table
            data={categorySummaryRows}
            columns={summaryColumns}
            keyExtractor={(s) => s.name}
            rowClassName={summaryRowClassName}
          />
        </div>
      </div>

      {/* Entries Table */}
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-[var(--gruvbox-yellow)] mb-2">
          Entries for {formatDate(selectedDate || "")}
        </h2>
        <Table
          data={sortedEntries}
          columns={entryColumns}
          keyExtractor={(e) => e.id?.toString() || e.description}
          emptyMessage="No entries for this date"
          sortKey={sortKey}
          sortDirection={sortDirection}
          onSort={handleSort}
        />
        <div className="mt-2 p-2 bg-[var(--gruvbox-bg1)] rounded border border-[var(--gruvbox-bg3)] flex justify-end gap-8 font-data text-sm">
          <div>
            <span className="text-[var(--gruvbox-fg4)]">Total CAD:</span>{" "}
            <span className="text-[var(--gruvbox-green)]">
              {totalCad.toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </span>
          </div>
          <div>
            <span className="text-[var(--gruvbox-fg4)]">Total Net:</span>{" "}
            <span className="text-[var(--gruvbox-green)] font-bold">
              {totalNet.toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
