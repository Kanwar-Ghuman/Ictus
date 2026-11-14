import { pct } from "@/lib/format";
import type { ModelPick, PlanFight } from "@/lib/types";

const METHODS: Record<string, string> = { "KO/TKO": "KO/TKO", SUB: "Submission", DEC: "Decision" };

/**
 * The model's own call for every fight: winner, method, and round.
 * This is not what the bot bets. Betting is the section below.
 */
export function ModelPicks({ fights, note }: { fights: PlanFight[]; note?: string }) {
  const picked = fights.filter((fight) => fight.pick);
  if (picked.length === 0) return null;
  const finished = picked.filter((fight) => fight.winner);
  const correct = finished.filter((fight) => fight.pick!.winner === fight.winner);

  const lead = finished.length > 0
    ? `${correct.length} of ${finished.length} winners right so far`
    : "Winner, method, and round for every fight";

  return (
    <section id="picks" className="band">
      <div className="site-width">
        <p className="section-lead">{lead}</p>
        <div className="feature-card feature-card-table">
          <h2 className="card-title">Model picks</h2>
          <div className="overflow-x-auto">
            <table className="picks">
                  <thead>
                    <tr>
                      <th>Fight</th>
                      <th>Pick</th>
                      <th>Method</th>
                      <th>Round</th>
                      <th className="num">Confidence</th>
                      <th>Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {picked.map((fight) => (
                      <PickRow key={`${fight.f1}-${fight.f2}`} fight={fight} pick={fight.pick!} />
                    ))}
                  </tbody>
            </table>
          </div>
        </div>
        <p className="note">
          {note ?? "These are the model's predictions on their own. The bot bets a different number, the sportsbook odds nudged by the model, shown under Betting."}
        </p>
      </div>
    </section>
  );
}

function PickRow({ fight, pick }: { fight: PlanFight; pick: ModelPick }) {
  return (
    <tr>
      <td>
        {fight.f1} <span className="text-mist">vs</span> {fight.f2}
        {fight.weight_class && <span className="sub">{fight.weight_class}</span>}
      </td>
      <td className="pick">{pick.winner}</td>
      <td>{pick.method ? METHODS[pick.method] ?? pick.method : "—"}</td>
      <td>{roundLabel(pick)}</td>
      <td className="num">{pct(pick.confidence)}</td>
      <td><Result fight={fight} pick={pick} /></td>
    </tr>
  );
}

function roundLabel(pick: ModelPick): string {
  if (pick.method === "DEC") return "Goes the distance";
  return pick.round ? `Round ${pick.round}` : "—";
}

/** How the fight actually ended, once it has, and whether the winner pick was right. */
function Result({ fight, pick }: { fight: PlanFight; pick: ModelPick }) {
  if (!fight.winner) return <span className="text-ash">—</span>;
  const right = pick.winner === fight.winner;
  const how = [fight.result?.method, fight.result?.round ? `R${fight.result.round}` : null]
    .filter(Boolean).join(", ");
  return (
    <span className={right ? "text-hit" : "text-blood"}>
      {right ? "✓" : "✗"} {fight.winner}
      {how && <span className="text-ash"> · {how}</span>}
    </span>
  );
}
