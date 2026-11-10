import type { ReactNode } from "react";

/** Full-bleed opening band: copy on the left, the color sweep on the right. */
export function PageHero({ children }: { children: ReactNode }) {
  return (
    <section className="hero">
      <div className="hero-ribbon" aria-hidden="true">
        <svg viewBox="0 0 900 980" preserveAspectRatio="xMaxYMid slice">
          <defs>
            <linearGradient id="ribbon-main" x1="20" y1="900" x2="880" y2="40" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#1c1917" />
              <stop offset="28%" stopColor="#7c2d12" />
              <stop offset="55%" stopColor="#c2410c" />
              <stop offset="78%" stopColor="#e8a87c" />
              <stop offset="100%" stopColor="#f5e6d3" />
            </linearGradient>
            <linearGradient id="ribbon-hot" x1="900" y1="0" x2="200" y2="700" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#f6e7d4" />
              <stop offset="40%" stopColor="#e07a3d" />
              <stop offset="100%" stopColor="#9a3412" />
            </linearGradient>
            <linearGradient id="ribbon-cool" x1="0" y1="200" x2="800" y2="900" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#f5f0ea" />
              <stop offset="50%" stopColor="#a1624a" />
              <stop offset="100%" stopColor="#44403c" />
            </linearGradient>
            <filter id="ribbon-soft" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="10" />
            </filter>
          </defs>
          <g fill="none" strokeLinecap="round">
            <path
              d="M980,-60 C640,80 900,160 560,300 C180,460 820,500 470,720 C250,860 120,820 -40,980"
              stroke="url(#ribbon-cool)"
              strokeWidth="150"
              opacity="0.55"
              filter="url(#ribbon-soft)"
            />
            <path
              d="M960,-20 C600,90 860,200 500,340 C120,500 760,540 420,760 C220,890 40,860 -80,1020"
              stroke="url(#ribbon-main)"
              strokeWidth="118"
            />
            <path
              d="M1020,30 C700,120 920,240 580,370 C220,520 800,580 480,790"
              stroke="url(#ribbon-hot)"
              strokeWidth="72"
              opacity="0.9"
            />
            <path
              d="M900,70 C640,150 820,250 520,360 C240,470 680,530 400,700"
              stroke="#fff"
              strokeWidth="16"
              opacity="0.45"
            />
          </g>
        </svg>
      </div>
      <div className="site-width hero-inner">{children}</div>
    </section>
  );
}
