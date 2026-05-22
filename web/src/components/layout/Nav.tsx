"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

const navItems = [
  { href: "/ibkr", label: "IBKR" },
  { href: "/fbn", label: "FBN" },
  { href: "/equity", label: "Equity" },
];

export function Nav() {
  const pathname = usePathname();
  const { signOut } = useAuth();

  const isActive = (href: string) => pathname.startsWith(href);

  return (
    <nav className="bg-[var(--gruvbox-bg-hard)] border-b border-[var(--gruvbox-bg2)]">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-12">
          <div className="flex items-center gap-1">
            <Link
              href="/ibkr"
              className="text-[var(--gruvbox-orange)] font-bold text-lg mr-6 hover:text-[var(--gruvbox-yellow)] transition-colors"
            >
              Operator
            </Link>

            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`
                  px-3 py-1.5 rounded text-sm font-medium transition-colors
                  ${isActive(item.href)
                    ? "bg-[var(--gruvbox-bg2)] text-[var(--gruvbox-orange)]"
                    : "text-[var(--gruvbox-fg3)] hover:text-[var(--gruvbox-fg)] hover:bg-[var(--gruvbox-bg1)]"
                  }
                `}
              >
                {item.label}
              </Link>
            ))}
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => signOut()}
              className="text-[var(--gruvbox-fg4)] text-sm hover:text-[var(--gruvbox-red)] transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
