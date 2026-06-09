export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatInteger(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString("en-US", {
    maximumFractionDigits: 0,
  });
}

export function formatNumber(value: number | null | undefined, decimals = 0): string {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return `${value.toFixed(2)}%`;
}

/**
 * Parse a date string treating the raw value as EST (America/New_York).
 *
 * IBKR trade times are in New York time but stored in a TIMESTAMPTZ column
 * without timezone offset, so PostgreSQL treated them as UTC. Supabase then
 * returns them with a +00:00 or Z suffix. We strip that suffix and parse
 * the raw components as local time (user is in EST).
 */
export function parseAsNY(dateStr: string): Date {
  // Strip timezone suffix — the raw digits represent EST, not UTC
  let clean = dateStr.replace(/Z$/, "").replace(/[+-]\d{2}:\d{2}$/, "");

  // Date-only strings (YYYY-MM-DD) — treat as local date at midnight
  if (/^\d{4}-\d{2}-\d{2}$/.test(clean)) {
    const [y, m, d] = clean.split("-").map(Number);
    return new Date(y, m - 1, d);
  }
  // DateTime — construct with explicit components to avoid UTC interpretation
  const [datePart, timePart] = clean.split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  if (timePart) {
    const [h, min, s] = timePart.split(":").map(Number);
    return new Date(y, m - 1, d, h, min, s || 0);
  }
  return new Date(y, m - 1, d);
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "-";
  const date = parseAsNY(dateStr);
  return date.toLocaleDateString("en-CA"); // YYYY-MM-DD format
}

export function formatDateTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "-";
  const date = parseAsNY(dateStr);
  return `${date.toLocaleDateString("en-CA")} ${date.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })}`;
}

export function getDayName(dateStr: string): string {
  const date = parseAsNY(dateStr);
  return date.toLocaleDateString("en-US", { weekday: "long" });
}

export function getLastDayOfMonth(year: number, month: number): Date {
  return new Date(year, month + 1, 0);
}

/**
 * Add days to a YYYY-MM-DD string, returning a new YYYY-MM-DD string.
 * Uses local date arithmetic (via parseAsNY) to avoid DST drift.
 */
export function addDaysToDateStr(dateStr: string, days: number): string {
  const d = parseAsNY(dateStr);
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * Get the day of week (0=Sun, 6=Sat) for a YYYY-MM-DD string.
 * Uses local date (via parseAsNY) to avoid DST issues.
 */
export function getDayOfWeek(dateStr: string): number {
  return parseAsNY(dateStr).getDay();
}

export function getLastDayOfPreviousMonth(): Date {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), 0);
}
