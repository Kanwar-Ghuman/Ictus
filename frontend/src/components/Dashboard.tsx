"use client";

import { ControlPanel } from "@/components/ControlPanel";
import { SavedPicks } from "@/components/SavedPicks";
import { EventHeader } from "@/components/EventHeader";
import { FightCard } from "@/components/FightCard";
import { ModelPicks } from "@/components/ModelPicks";
import { PageHero } from "@/components/PageHero";
import { Banner } from "@/components/ui";
import { useBot } from "@/hooks/useBot";
import type { Plan, Prepare, SavedCard, Status } from "@/lib/types";

/** The whole page: tonight's event, the start/stop box, any notices, the model's picks, and betting. */
export function Dashboard({ saved }: { saved: SavedCard }) {
  const { status, plan, prepare, offline, pending, error, needsPredictions, prepareStuck, act } = useBot();

  if (offline || !status) return <SavedPicks card={saved} />;

  const fights = plan?.fights ?? [];
  const canStart = Boolean(plan?.card) && fights.some((fight) => fight.include);

  return (
    <div>
      <PageHero>
        <EventHeader status={status} plan={plan} />
        <div className="hero-action">
          <ControlPanel status={status} canStart={canStart} pending={pending} error={error} act={act} />
        </div>
      </PageHero>

      <div className="sheet-page">
        {needsPredictions && (
          <PredictionsBanner prepare={prepare} stuck={prepareStuck} busy={pending !== null}
            onRetry={() => void act("prepare")} />
        )}
        <EventNotice status={status} plan={plan} />
        <ModelPicks fights={fights} />
        <section id="betting" className="band">
          <div className="site-width">
            <p className="section-lead">The bot&apos;s chance vs. Kalshi&apos;s price</p>
            <div className="feature-card">
              <h2 className="card-title">Betting</h2>
              <div className="feature-stage feature-stage-cool">
                {fights.length === 0 ? (
                  <p className="sheet sheet-pad">{feedLineup(status)}</p>
                ) : (
                  <div className="fight-grid">
                    {fights.map((fight) => (
                      <FightCard key={`${fight.f1}-${fight.f2}`} fight={fight}
                        liveStatus={status.feed?.fights.find((f) => f.bout_id === fight.bout_id)?.status ?? fight.status}
                        decision={status.decisions.find((decision) => decision.ticker === fight.ticker)}
                        result={fight.ticker ? status.results?.markets[fight.ticker] : undefined}
                        orders={status.orders.filter((order) => order.ticker === fight.ticker)}
                        running={status.running} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

/** The bot builds missing predictions by itself. This follows it, and offers a retry if it fails. */
function PredictionsBanner({ prepare, stuck, busy, onRetry }: {
  prepare: Prepare | null; stuck: boolean; busy: boolean; onRetry: () => void;
}) {
  const retry = prepare?.state === "failed" && (
    <button type="button" onClick={onRetry} disabled={busy}
      className="btn btn-primary">
      Try again
    </button>
  );
  return (
    <Banner action={retry}
      title={stuck ? "Couldn't build predictions for this event" : "Building predictions for this event"}>
      {prepare?.message || "The bot is running the model on tonight's card. It takes a minute or two."}
    </Banner>
  );
}

/** Why nothing can be traded right now, if that is the case. */
function EventNotice({ status, plan }: { status: Status; plan: Plan | null }) {
  if (plan?.event.status === "final") {
    return (
      <Banner title="This event is over">
        The next card shows up here automatically once ESPN and Kalshi list it.
      </Banner>
    );
  }
  if (!plan?.problem || plan.needs_predictions) return null;
  return (
    <Banner title={plan.problem}>
      {status.feed_connected ? "The bot keeps checking." : "Check that the fight feed is running."}
    </Banner>
  );
}

/** Before any predictions exist, list the fights ESPN shows so the page is not empty. */
function feedLineup(status: Status): string {
  const lineup = (status.feed?.fights ?? []).map((fight) => `${fight.fighter_a} vs ${fight.fighter_b}`);
  return lineup.join(" · ") || "No fights yet.";
}
