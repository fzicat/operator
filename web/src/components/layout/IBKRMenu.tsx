"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const menuItems = [
  { href: "/ibkr", label: "Positions", match: (p: string) => p === "/ibkr" || p.startsWith("/ibkr/positions") },
  { href: "/ibkr/risk", label: "Risk Dashboard", match: (p: string) => p.startsWith("/ibkr/risk") },
  { href: "/ibkr/stats/daily", label: "Stats", match: (p: string) => p.startsWith("/ibkr/stats") },
  { href: "/ibkr/charts", label: "Charts", match: (p: string) => p.startsWith("/ibkr/charts") },
  { href: "/ibkr/performance", label: "Performance", match: (p: string) => p.startsWith("/ibkr/performance") },
  { href: "/ibkr/pnl", label: "PnL", match: (p: string) => p.startsWith("/ibkr/pnl") },
  { href: "/ibkr/mtm", label: "MTM", match: (p: string) => p.startsWith("/ibkr/mtm") },
];

export function IBKRMenu() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="IBKR menu"
        aria-expanded={open}
        className="p-1.5 rounded text-[var(--gruvbox-fg3)] hover:text-[var(--gruvbox-fg)] hover:bg-[var(--gruvbox-bg1)] transition-colors"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="w-5 h-5"
        >
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-1 min-w-[10rem] bg-[var(--gruvbox-bg-hard)] border border-[var(--gruvbox-bg2)] rounded shadow-lg z-50 py-1">
          {menuItems.map((item) => {
            const active = item.match(pathname);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={`block px-3 py-1.5 text-sm transition-colors ${
                  active
                    ? "text-[var(--gruvbox-orange)] bg-[var(--gruvbox-bg1)]"
                    : "text-[var(--gruvbox-fg3)] hover:text-[var(--gruvbox-fg)] hover:bg-[var(--gruvbox-bg1)]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
