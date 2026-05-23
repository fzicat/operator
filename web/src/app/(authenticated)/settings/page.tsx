"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { Button } from "@/components/ui/Button";

export default function SettingsPage() {
  const router = useRouter();
  const { signOut } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const handleLogout = async () => {
    await signOut();
    router.replace("/login");
  };

  return (
    <div className="max-w-md">
      <h1 className="text-xl font-bold text-[var(--gruvbox-orange)] mb-6">
        Settings
      </h1>

      <div className="space-y-6">
        <section>
          <h2 className="text-sm font-medium text-[var(--gruvbox-fg3)] mb-2">
            Theme
          </h2>
          <Button variant="secondary" onClick={toggleTheme}>
            {theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          </Button>
          <p className="text-xs text-[var(--gruvbox-fg4)] mt-2">
            Current: {theme}
          </p>
        </section>

        <section>
          <h2 className="text-sm font-medium text-[var(--gruvbox-fg3)] mb-2">
            Account
          </h2>
          <Button variant="danger" onClick={handleLogout}>
            Logout
          </Button>
        </section>
      </div>
    </div>
  );
}
