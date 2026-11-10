import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { SpinningLogo } from "@/components/SpinningLogo";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-inter" });

export const metadata: Metadata = {
  title: "Ictus — UFC trading bot",
  description: "Set a spending limit and let the model trade tonight's UFC fights on Kalshi.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} h-full`}>
      <body className="flex min-h-full flex-col">
        <header className="nav">
          <div className="site-width nav-row">
            <div className="nav-left">
              <SpinningLogo />
              <nav className="nav-links" aria-label="On this page">
                <a href="#picks">Model picks</a>
                <a href="#betting">Betting</a>
              </nav>
            </div>
            <p className="nav-meta">UFC × Kalshi</p>
          </div>
        </header>
        <main id="main" className="flex-1">{children}</main>
        <footer className="site-foot">
          <p className="site-width">
            No model guarantees a profit. Only bet what you can afford to lose.
          </p>
        </footer>
      </body>
    </html>
  );
}
