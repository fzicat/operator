"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const menuItems = [
  { href: "/equity", label: "Overview", match: (p: string) => p === "/equity" },
  { href: "/equity/pivot", label: "Pivot Tables", match: (p: string) => p.startsWith("/equity/pivot") },
];

export function EquityMenu() {
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
        aria-label="Equity menu"
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
