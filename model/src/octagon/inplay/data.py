"""Round-end training rows for the between-rounds model.

One row per (fight, completed round k) where the fight CONTINUED past round
k: the only moments a between-rounds trade could be placed. Stats are each
corner's cumulative totals through round k, restricted to what ESPN's live
fightcenter also reports (see ``live.py``), so training inputs and live
inputs mean the same thing.

Pre-fight priors attached per fight, all known before the opening bell:
* ``p_market`` — vig-free closing line (bootstrap odds, 2014–2023)
* ``p_skill``  — the skill model's saved out-of-sample prediction (2022+)
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from octagon.db.greco import _clean, _parse_count
from octagon.db.parsing import parse_mmss_to_seconds, parse_of_pair

# name -> (landed, attempted) columns, or a single count/seconds column.
PAIRS = {"sig": "SIG.STR.", "tot": "TOTAL STR.", "head": "HEAD", "body": "BODY",
         "leg": "LEG", "td": "TD"}
STATS = [f"{name}_{part}" for name in PAIRS for part in ("l", "a")] + ["kd", "sub", "ctrl"]


def _round_rows(stats_csv: Path) -> dict[tuple[str, str], dict[int, dict[str, float]]]:
    """(event, fighter) -> round -> that round's raw stats."""
    out: dict[tuple[str, str], dict[int, dict[str, float]]] = {}
    with open(stats_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            label = row["ROUND"].strip()
            if not label.startswith("Round "):
                continue
            k = int(label.split()[1])
            stats: dict[str, float] = {}
            for name, column in PAIRS.items():
                landed, attempted = parse_of_pair(row[column])
                stats[f"{name}_l"], stats[f"{name}_a"] = landed, attempted
            stats["kd"] = _parse_count(row["KD"])
            stats["sub"] = _parse_count(row["SUB.ATT"])
            stats["ctrl"] = parse_mmss_to_seconds(row["CTRL"])
            if any(v is None for v in stats.values()):
                continue  # an incomplete round poisons every later cumulative
            key = (_clean(row["EVENT"]), _clean(row["FIGHTER"]))
            out.setdefault(key, {})[k] = stats
    return out


def _devig(o1: float, o2: float) -> float:
    q1, q2 = 1 / o1, 1 / o2
    return q1 / (q1 + q2)


def build_round_dataset(db_path: Path, greco_dir: Path, reports_dir: Path) -> pd.DataFrame:
    rounds = _round_rows(greco_dir / "ufc_fight_stats.csv")
    conn = sqlite3.connect(db_path)
    fights = pd.read_sql_query(
        """SELECT f.fight_id, f.date, e.name AS event, f.fighter1, f.fighter2, f.winner,
                  f.scheduled_rounds, f.end_round, f.method, f.weight_class,
                  o.fighter1_odds, o.fighter2_odds
           FROM fights f JOIN events e USING(event_id)
           LEFT JOIN odds o ON o.fight_id = f.fight_id
           WHERE f.winner IN ('fighter1', 'fighter2') AND f.end_round IS NOT NULL
                 AND f.scheduled_rounds IN (3, 5)""",
        conn,
    )
    conn.close()

    skill = _skill_priors(reports_dir)
    records = []
    for f in fights.itertuples(index=False):
        r1 = rounds.get((_clean(f.event), _clean(f.fighter1)))
        r2 = rounds.get((_clean(f.event), _clean(f.fighter2)))
        if not r1 or not r2:
            continue
        p_market = (_devig(f.fighter1_odds, f.fighter2_odds)
                    if f.fighter1_odds and f.fighter2_odds and f.fighter1_odds > 1 and f.fighter2_odds > 1
                    else np.nan)
        p_skill = skill.get((f.date, _clean(f.fighter1), _clean(f.fighter2)), np.nan)
        c1 = dict.fromkeys(STATS, 0.0)
        c2 = dict.fromkeys(STATS, 0.0)
        # A between-rounds row exists only if round k finished and k+1 began.
        for k in range(1, min(int(f.end_round), int(f.scheduled_rounds))):
            if k not in r1 or k not in r2:
                break
            for s in STATS:
                c1[s] += r1[k][s]
                c2[s] += r2[k][s]
            records.append({
                "fight_id": f.fight_id, "date": f.date, "round": k,
                "scheduled_rounds": int(f.scheduled_rounds),
                "label": int(f.winner == "fighter1"), "method": f.method,
                "p_market": p_market, "p_skill": p_skill,
                **{f"f1_{s}": c1[s] for s in STATS}, **{f"f2_{s}": c2[s] for s in STATS},
            })
    return pd.DataFrame.from_records(records)


def _skill_priors(reports_dir: Path) -> dict[tuple[str, str, str], float]:
    """Saved out-of-sample skill predictions, oriented to (date, fighter1, fighter2)."""
    out: dict[tuple[str, str, str], float] = {}
    for split in ("valid", "test"):
        path = reports_dir / f"predictions_{split}.parquet"
        if not path.exists():
            continue
        frame = pd.read_parquet(path, columns=["date", "f1_name", "f2_name", "p_blend"])
        for row in frame.itertuples(index=False):
            date = str(row.date)[:10]
            a, b = _clean(row.f1_name), _clean(row.f2_name)
            out[(date, a, b)] = float(row.p_blend)
            out[(date, b, a)] = 1 - float(row.p_blend)
    return out
