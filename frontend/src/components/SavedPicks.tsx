import { ModelPicks } from "@/components/ModelPicks";
import { PageHero } from "@/components/PageHero";
import type { SavedCard } from "@/lib/types";

/** The latest published card. Shown on the deployed site, and locally while the bot is off. */
export function SavedPicks({ card }: { card: SavedCard }) {
  const fights = card.fights ?? [];
  return (
    <div>
      <PageHero>
        <div className="hero-copy">
          <p className="eyebrow">Model picks</p>
          <h1 className="hero-title">
            <span className="hero-strong">{card.event || "Model picks"}</span>
            <span className="hero-mute">{subtitle(card, fights.length)}</span>
          </h1>
        </div>
      </PageHero>
      <div className="sheet-page">
        <ModelPicks fights={fights} note="These are the model's predictions from the last run." />
      </div>
    </div>
  );
}

function subtitle(card: SavedCard, count: number): string {
  if (!card.event) return "No saved predictions yet.";
  const when = card.date ? new Date(`${card.date}T00:00:00`).toLocaleDateString("en-US", {
    month: "long", day: "numeric", year: "numeric",
  }) : "";
  return [when, `${count} fights`].filter(Boolean).join(" · ");
}
