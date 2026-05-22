import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { ErrorProvider } from "@/lib/error-context";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Operator",
  description: "Trading portfolio management application",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} antialiased bg-[var(--gruvbox-bg)] text-[var(--gruvbox-fg)]`}
      >
        <AuthProvider>
          <ErrorProvider>{children}</ErrorProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
