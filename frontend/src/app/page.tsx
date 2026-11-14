import { readFileSync } from "node:fs";
import path from "node:path";

import { Dashboard } from "@/components/Dashboard";
import type { SavedCard } from "@/lib/types";

const EMPTY: SavedCard = { event: null, date: null, fights: [] };

/** The card written by `octagon predict` and shipped with this site. */
function savedCard(): SavedCard {
  try {
    const raw = readFileSync(path.join(process.cwd(), "public", "picks.json"), "utf8");
    const data = JSON.parse(raw) as SavedCard;
    if (!data || !Array.isArray(data.fights)) return EMPTY;
    return data;
  } catch {
    return EMPTY;
  }
}

export default function Home() {
  return <Dashboard saved={savedCard()} />;
}
