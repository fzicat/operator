import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";
import { ErrorProvider } from "@/lib/error-context";
import { ThemeProvider } from "@/lib/theme";

const themeInitScript = `
(function(){try{var t=localStorage.getItem('theme')||'dark';document.documentElement.setAttribute('data-theme',t);}catch(e){}})();
`;

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
    <html lang="en" data-theme="dark">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} antialiased bg-[var(--gruvbox-bg)] text-[var(--gruvbox-fg)]`}
      >
        <ThemeProvider>
          <AuthProvider>
            <ErrorProvider>{children}</ErrorProvider>
          </AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
