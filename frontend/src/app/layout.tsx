import type { Metadata } from "next";
import { SpinningLogo } from "@/components/SpinningLogo";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ictus — UFC trading bot",
  description: "Set a spending limit and let the model trade tonight's UFC fights on Kalshi.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className="h-full">
    <body className="flex min-h-full flex-col">
      <header className="border-b border-line bg-paper">
        <div className="site-width flex items-center justify-between gap-4">
          <SpinningLogo />
          <p className="label text-[10px] text-ash">UFC × Kalshi</p>
        </div>
      </header>
      <main id="main" className="site-width flex-1 py-8 sm:py-10">{children}</main>
      <footer className="border-t border-line">
        <p className="site-width py-5 text-[11px] leading-relaxed text-mist">
          No model guarantees a profit. Only bet what you can afford to lose.
        </p>
      </footer>
    </body>
  </html>;
}
