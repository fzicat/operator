"use client";

import { useState, useEffect, useCallback } from "react";
import { supabase } from "@/lib/supabase";
import { useError } from "@/lib/error-context";
import { EquityEntry } from "@/types";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate, formatInteger } from "@/lib/utils/format";
import { EquityMenu } from "@/components/layout/EquityMenu";

interface PivotRow {
  date: string;
  columns: Record<string, number>;
  total: number;
}

export default function EquityPivotPage() {
  const { setError } = useError();
  const [accountCadData, setAccountCadData] = useState<PivotRow[]>([]);
  const [categoryCadData, setCategoryCadData] = useState<PivotRow[]>([]);
  const [accountNetData, setAccountNetData] = useState<PivotRow[]>([]);
  const [categoryNetData, setCategoryNetData] = useState<PivotRow[]>([]);
  const [accounts, setAccounts] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedSection, setExpandedSection] = useState<string | null>(
    "categoryNet"
  );

  const loadData = useCallback(async () => {
    try {
      setLoading(true);

      const { data, error } = await supabase
        .from("equity")
        .select("*")
        .order("date", { ascending: false });

      if (error) throw error;

      const rawEntries = data as EquityEntry[];

      // Process entries
      const entries = rawEntries.map((entry) => {
        let balanceCad = entry.balance * entry.rate;
        if (entry.currency === "SAT") {
          balanceCad = balanceCad / 100_000_000;
        }
        const balanceNet = balanceCad * (1 - entry.tax);
        return { ...entry, balance_cad: balanceCad, balance_net: balanceNet };
      });

      // Get unique accounts and categories
      const uniqueAccounts = [...new Set(entries.map((e) => e.account))].sort();
      const uniqueCategories = [...new Set(entries.map((e) => e.category))].sort();
      setAccounts(uniqueAccounts);
      setCategories(uniqueCategories);

      // Group by date
      const dateGroups: Record<string, EquityEntry[]> = {};
      for (const entry of entries) {
        if (!dateGroups[entry.date]) {
          dateGroups[entry.date] = [];
        }
        dateGroups[entry.date].push(entry);
      }

      const dates = Object.keys(dateGroups).sort((a, b) => b.localeCompare(a));

      // Build pivot tables
      const accountCad: PivotRow[] = [];
      const categoryCad: PivotRow[] = [];
      const accountNet: PivotRow[] = [];
      const categoryNet: PivotRow[] = [];

      for (const date of dates) {
        const dateEntries = dateGroups[date];

        // Account CAD
        const accountCadCols: Record<string, number> = {};
        let accountCadTotal = 0;
        for (const acc of uniqueAccounts) {
          const sum = dateEntries
            .filter((e) => e.account === acc)
            .reduce((s, e) => s + (e.balance_cad || 0), 0);
          accountCadCols[acc] = sum;
          accountCadTotal += sum;
        }
        accountCad.push({ date, columns: accountCadCols, total: accountCadTotal });

        // Category CAD
        const categoryCadCols: Record<string, number> = {};
        let categoryCadTotal = 0;
        for (const cat of uniqueCategories) {
          const sum = dateEntries
            .filter((e) => e.category === cat)
            .reduce((s, e) => s + (e.balance_cad || 0), 0);
          categoryCadCols[cat] = sum;
          categoryCadTotal += sum;
        }
        categoryCad.push({ date, columns: categoryCadCols, total: categoryCadTotal });

        // Account Net
        const accountNetCols: Record<string, number> = {};
        let accountNetTotal = 0;
        for (const acc of uniqueAccounts) {
          const sum = dateEntries
            .filter((e) => e.account === acc)
            .reduce((s, e) => s + (e.balance_net || 0), 0);
          accountNetCols[acc] = sum;
          accountNetTotal += sum;
        }
        accountNet.push({ date, columns: accountNetCols, total: accountNetTotal });

        // Category Net
        const categoryNetCols: Record<string, number> = {};
        let categoryNetTotal = 0;
        for (const cat of uniqueCategories) {
          const sum = dateEntries
            .filter((e) => e.category === cat)
            .reduce((s, e) => s + (e.balance_net || 0), 0);
          categoryNetCols[cat] = sum;
          categoryNetTotal += sum;
        }
        categoryNet.push({ date, columns: categoryNetCols, total: categoryNetTotal });
      }

      setAccountCadData(accountCad);
      setCategoryCadData(categoryCad);
      setAccountNetData(accountNet);
      setCategoryNetData(categoryNet);
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

  const renderPivotTable = (
    data: PivotRow[],
    columnNames: string[],
    title: string,
    sectionKey: string
  ) => {
    const isExpanded = expandedSection === sectionKey;

    return (
      <div className="border border-[var(--gruvbox-bg3)] rounded overflow-hidden">
        <button
          onClick={() => setExpandedSection(isExpanded ? null : sectionKey)}
          className="w-full flex items-center justify-between p-3 bg-[var(--gruvbox-bg1)] hover:bg-[var(--gruvbox-bg2)] transition-colors"
        >
          <h3 className="text-[var(--gruvbox-yellow)] font-semibold">{title}</h3>
          <span className="text-[var(--gruvbox-fg4)]">
            {isExpanded ? "[-]" : "[+]"}
          </span>
        </button>
        {isExpanded && (
          <div className="overflow-x-auto">
            <table className="data-table font-data text-sm">
              <thead>
                <tr>
                  <th className="text-left">Date</th>
                  {columnNames.map((name) => (
                    <th key={name} className="text-right">
                      {name}
                    </th>
                  ))}
                  <th className="text-right text-[var(--gruvbox-aqua)] font-bold">
                    Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((row) => (
                  <tr key={row.date}>
                    <td className="text-[var(--gruvbox-fg4)]">
                      {formatDate(row.date)}
                    </td>
                    {columnNames.map((name) => (
                      <td key={name} className="text-right">
                        {formatInteger(row.columns[name] || 0)}
                      </td>
                    ))}
                    <td className="text-right text-[var(--gruvbox-aqua)] font-bold">
                      {formatInteger(row.total)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <EquityMenu />
          <h1 className="text-xl font-semibold text-[var(--gruvbox-orange)]">
            Equity Pivot Tables
          </h1>
        </div>
      </div>

      <div className="space-y-4">
        {renderPivotTable(
          accountCadData,
          accounts,
          "Balance CAD by Account",
          "accountCad"
        )}
        {renderPivotTable(
          categoryCadData,
          categories,
          "Balance CAD by Category",
          "categoryCad"
        )}
        {renderPivotTable(
          accountNetData,
          accounts,
          "Balance Net by Account",
          "accountNet"
        )}
        {renderPivotTable(
          categoryNetData,
          categories,
          "Balance Net by Category",
          "categoryNet"
        )}
      </div>
    </div>
  );
}
