"""Point-in-time feature builder.

Fights are replayed in chronological order. Each snapshot is taken from a
fighter's history before the current fight is appended. tests/test_features.py
checks this by truncation: deleting later fights must not change earlier rows.

Sources list winners first often enough to leak the label, so assembled rows
get a seeded corner swap (f1/f2 exchanged, diffs negated, label flipped).
"""

import math
import random
import sqlite3
from dataclasses import dataclass, field
from datetime import date as date_type
from datetime import datetime

from octagon.features.elo import Elo, experience_multiplier


@dataclass
class Bout:
    """One fight as the builder consumes it, already in chronological order."""

    fight_id: int
    date: str                    # ISO
    fighter1: str
    fighter2: str
    winner: str                  # 'fighter1' | 'fighter2' | 'draw' | 'nc'
    method: str | None
    end_round: int | None
    duration_s: int | None
    weight_class: str | None
    title_fight: int
    scheduled_rounds: int | None
    stats1: dict | None          # fight_stats row for each corner (or None)
    stats2: dict | None
    odds1: float | None          # decimal closing odds (or None)
    odds2: float | None


@dataclass
class PastFight:
    """One completed fight from a single fighter's perspective."""

    date: date_type
    result: str                  # 'win' | 'loss' | 'draw' | 'nc'
    method: str | None
    end_round: int | None
    duration_s: int | None
    stats: dict | None           # own fight_stats
    opp_stats: dict | None       # opponent's fight_stats (what we absorbed)
    opp_elo_pre: float = 1500.0  # opponent's Elo entering that fight (strength of schedule)
    opponent: str | None = None  # name, for rematches and common opponents
    opp_style: dict | None = None  # opponent's archetype scores entering that fight
    own_elo_pre: float = 1500.0  # own rating before this result, never today's rating


@dataclass
class FighterHistory:
    fights: list[PastFight] = field(default_factory=list)


def _ratio(num: float | None, den: float | None) -> float | None:
    """Safe division: None when the denominator is missing or zero."""
    if num is None or not den:
        return None
    return num / den


def _window_stats(window: list[PastFight], suffix: str,
                  include_style: bool = False) -> dict[str, float | None]:
    """Rolling per-minute/accuracy stats over the last N statted fights.

    Rates are computed as (sum of numerators / sum of denominators) across
    the window rather than averaging per-fight rates — a 30-second KO
    shouldn't count as much striking evidence as a 25-minute war.
    """
    minutes = sum(f.duration_s for f in window) / 60 if window else 0
    _own = [f.stats for f in window]
    _opp = [f.opp_stats for f in window]

    def total(key: str, opponent: bool = False) -> int | None:
        rows = _opp if opponent else _own
        values = [r.get(key) for r in rows if r and r.get(key) is not None]
        return sum(values) if values else None

    out = {}
    if include_style:
        tgt_total = sum(filter(None, (total("head_landed"), total("body_landed"),
                                      total("leg_landed")))) or None
        pos_total = sum(filter(None, (total("distance_landed"), total("clinch_landed"),
                                      total("ground_landed")))) or None
        opp_pos_total = sum(filter(None, (total("distance_landed", True),
                                          total("clinch_landed", True),
                                          total("ground_landed", True)))) or None
        out |= {
            f"leg_share_{suffix}": _ratio(total("leg_landed"), tgt_total),
            f"head_share_{suffix}": _ratio(total("head_landed"), tgt_total),
            f"ground_share_{suffix}": _ratio(total("ground_landed"), pos_total),
            f"clinch_share_{suffix}": _ratio(total("clinch_landed"), pos_total),
            f"ground_absorbed_share_{suffix}": _ratio(
                total("ground_landed", opponent=True), opp_pos_total),
        }

    return out | {
        f"slpm_{suffix}": _ratio(total("sig_landed"), minutes),
        f"sapm_{suffix}": _ratio(total("sig_landed", opponent=True), minutes),
        f"sig_acc_{suffix}": _ratio(total("sig_landed"), total("sig_attempted")),
        f"sig_def_{suffix}": (
            None if total("sig_attempted", opponent=True) in (None, 0)
            else 1 - total("sig_landed", opponent=True) / total("sig_attempted", opponent=True)
        ),
        f"td15_{suffix}": _ratio(total("td_landed"), minutes / 15 if minutes else None),
        f"td_acc_{suffix}": _ratio(total("td_landed"), total("td_attempted")),
        f"td_def_{suffix}": (
            None if total("td_attempted", opponent=True) in (None, 0)
            else 1 - total("td_landed", opponent=True) / total("td_attempted", opponent=True)
        ),
        f"sub15_{suffix}": _ratio(total("sub_attempts"), minutes / 15 if minutes else None),
        f"kd15_{suffix}": _ratio(total("knockdowns"), minutes / 15 if minutes else None),
        f"ctrl_pct_{suffix}": _ratio(total("ctrl_seconds"), minutes * 60 if minutes else None),
    }


def fighter_snapshot(
    history: FighterHistory,
    on_date: date_type,
    tott: dict | None,
    elo_rating: float,
    regional_fights: list[dict] | None = None,
) -> dict[str, float | None]:
    """All point-in-time features for one fighter entering a fight."""
    from octagon.features.regional import career_snapshot, regional_snapshot

    fights = history.fights
    decisive = [f for f in fights if f.result in ("win", "loss")]
    wins = [f for f in decisive if f.result == "win"]
    losses = [f for f in decisive if f.result == "loss"]

    # Current streak: consecutive wins (+) or losses (-); draw/nc breaks it.
    streak = 0
    for f in reversed(fights):
        if f.result == "win" and streak >= 0:
            streak += 1
        elif f.result == "loss" and streak <= 0:
            streak -= 1
        else:
            break

    age = None
    if tott and tott.get("dob"):
        dob = datetime.strptime(tott["dob"], "%Y-%m-%d").date()
        age = (on_date - dob).days / 365.25

    last = fights[-1].date if fights else None
    timed = [f for f in fights if f.duration_s is not None]
    total_min = sum(f.duration_s for f in timed) / 60 if timed else None
    statted = [f for f in fights if f.stats and f.duration_s]
    ended = [f for f in fights if f.end_round is not None]
    finishes = [f for f in decisive if f.method in ("KO/TKO", "SUB")]

    def rate(subset: list[PastFight], base: list[PastFight]) -> float | None:
        return _ratio(len(subset), len(base))

    snapshot = {
        "age": age,
        "height_cm": tott.get("height_cm") if tott else None,
        "reach_cm": tott.get("reach_cm") if tott else None,
        "southpaw": (1.0 if tott.get("stance") == "Southpaw" else 0.0) if tott and tott.get("stance") else None,
        "n_fights": float(len(fights)),
        "wins": float(len(wins)),
        "losses": float(len(losses)),
        "win_pct": rate(wins, decisive),
        "streak": float(streak),
        "layoff_days": float((on_date - last).days) if last else None,
        "fights_12m": float(sum(1 for f in fights if (on_date - f.date).days <= 365)),
        "fights_24m": float(sum(1 for f in fights if (on_date - f.date).days <= 730)),
        "total_octagon_min": total_min,
        "avg_fight_min": _ratio(total_min, len(timed)),
        "ko_win_rate": rate([f for f in wins if f.method == "KO/TKO"], decisive),
        "sub_win_rate": rate([f for f in wins if f.method == "SUB"], decisive),
        "dec_win_rate": rate([f for f in wins if f.method and f.method.endswith("DEC")], decisive),
        # Conditional on a win so a .500 KO artist is not scored like a .250
        # decision fighter. Used by the method model.
        "ko_share": rate([f for f in wins if f.method == "KO/TKO"], wins),
        "sub_share": rate([f for f in wins if f.method == "SUB"], wins),
        "ko_share_l5": rate(
            [f for f in decisive[-5:] if f.result == "win" and f.method == "KO/TKO"],
            [f for f in decisive[-5:] if f.result == "win"]),
        "sub_share_l5": rate(
            [f for f in decisive[-5:] if f.result == "win" and f.method == "SUB"],
            [f for f in decisive[-5:] if f.result == "win"]),
        "ko_end_rate_l5": rate(
            [f for f in decisive[-5:] if f.method == "KO/TKO"], decisive[-5:]),
        "sub_end_rate_l5": rate(
            [f for f in decisive[-5:] if f.method == "SUB"], decisive[-5:]),
        "dec_end_rate_l5": rate(
            [f for f in decisive[-5:] if f.method and str(f.method).endswith("DEC")],
            decisive[-5:]),
        "times_koed": float(len([f for f in losses if f.method == "KO/TKO"])),
        "times_subbed": float(len([f for f in losses if f.method == "SUB"])),
        "late_finish_rate": rate(
            [f for f in wins if f.method in ("KO/TKO", "SUB") and (f.end_round or 0) >= 3],
            decisive),
        "r1_win_rate": rate(
            [f for f in wins if f.method in ("KO/TKO", "SUB") and f.end_round == 1],
            decisive),
        "r1_loss_rate": rate(
            [f for f in losses if f.method in ("KO/TKO", "SUB") and f.end_round == 1],
            decisive),
        "finish_involvement": rate(finishes, decisive),
        "avg_end_round": (sum(f.end_round for f in ended) / len(ended)) if ended else None,
        "elo": elo_rating,
        "opp_elo_l5": (sum(f.opp_elo_pre for f in fights[-5:]) / len(fights[-5:])
                       if fights else None),
    }
    snapshot |= _window_stats(statted[-3:], "l3")
    snapshot |= _window_stats(statted[-5:], "l5", include_style=True)
    snapshot |= regional_snapshot(regional_fights or [], on_date.isoformat())
    snapshot |= career_snapshot(
        [(f.date.isoformat(), f.result, f.method) for f in fights],
        regional_fights or [], on_date.isoformat())
    snapshot["age_past_prime"] = max(0.0, age - 32.0) if age is not None else None

    from octagon.features.research import form_snapshot
    from octagon.features.style import style_scores

    snapshot |= form_snapshot(fights, on_date, elo_rating)
    snapshot |= {f"style_{key}": value for key, value in style_scores(snapshot).items()}
    return snapshot


def matchup_features(f1: dict, f2: dict) -> dict[str, float | None]:
    """How each fighter's offense meets the *other's* specific defense.

    A wrestler's takedown rate matters differently against 90% takedown
    defense than against 40%; snapshots can't see that because they're
    per-fighter. Each feature is offense(A) x vulnerability(B), emitted as
    the antisymmetric difference A-side minus B-side — so under a corner
    swap it negates like every other diff_* column, and the logistic
    model (diff_* only) gets to use it too.
    """
    def fragility(s: dict, key: str) -> float | None:
        """Share of a fighter's fights lost by KO (or sub) — the chin."""
        n = s.get("n_fights")
        koed = s.get(key)
        return (koed / n) if n and koed is not None else None

    def cross(a: dict, b: dict) -> dict[str, float | None]:
        def prod(x: float | None, y: float | None) -> float | None:
            return x * y if x is not None and y is not None else None

        tdd = b.get("td_def_l5")
        sigd = b.get("sig_def_l5")
        return {
            "td_pressure": prod(a.get("td15_l5"),
                                (1 - tdd) if tdd is not None else None),
            "strike_pressure": prod(a.get("slpm_l5"),
                                    (1 - sigd) if sigd is not None else None),
            "power_chin": prod(a.get("kd15_l5"), fragility(b, "times_koed")),
            "sub_threat": prod(a.get("sub15_l5"),
                               b.get("ground_absorbed_share_l5")),
            "sub_finish": prod(a.get("sub15_l5"), fragility(b, "times_subbed")),
        }

    forward, backward = cross(f1, f2), cross(f2, f1)
    out = {
        f"matchup_{key}": (forward[key] - backward[key]
                           if forward[key] is not None and backward[key] is not None
                           else None)
        for key in forward
    }
    from octagon.features.style import style_matchup

    out.update(style_matchup(f1, f2))
    return out


def bout_features(f1: dict, f2: dict) -> dict[str, float | None]:
    """Symmetric pairing stats (mean/min/max). Differentials cannot see
    whether both fighters finish early or both go to the scorecards.
    """
    def pair(key: str, how: str = "mean") -> float | None:
        a, b = f1.get(key), f2.get(key)
        if a is None or b is None:
            return None
        if how == "min":
            return min(a, b)
        if how == "max":
            return max(a, b)
        return (a + b) / 2.0

    def fragility(snap: dict, key: str) -> float | None:
        n, count = snap.get("n_fights"), snap.get(key)
        return (count / n) if n and count is not None else None

    def pair_fragility(key: str) -> float | None:
        a, b = fragility(f1, key), fragility(f2, key)
        return (a + b) / 2.0 if a is not None and b is not None else None

    def gap(key: str) -> float | None:
        a, b = f1.get(key), f2.get(key)
        if a is None or b is None:
            return None
        return abs(a - b)

    r1_pace = [
        (s.get("r1_win_rate") or 0.0) + (s.get("r1_loss_rate") or 0.0)
        for s in (f1, f2)
        if s.get("r1_win_rate") is not None or s.get("r1_loss_rate") is not None
    ]

    return {
        "bout_finish_involvement": pair("finish_involvement"),
        "bout_finish_max": pair("finish_involvement", "max"),
        "bout_ko_rate": pair("ko_win_rate"),
        "bout_sub_rate": pair("sub_win_rate"),
        "bout_dec_rate": pair("dec_win_rate"),
        "bout_ko_share": pair("ko_share"),
        "bout_sub_share": pair("sub_share"),
        "bout_ko_share_max": pair("ko_share", "max"),
        "bout_late_finish_rate": pair("late_finish_rate"),
        "bout_ko_end_rate_l5": pair("ko_end_rate_l5"),
        "bout_sub_end_rate_l5": pair("sub_end_rate_l5"),
        "bout_dec_end_rate_l5": pair("dec_end_rate_l5"),
        "bout_avg_end_round": pair("avg_end_round"),
        "bout_r1_pace": (sum(r1_pace) / len(r1_pace)) if r1_pace else None,
        "bout_koed_rate": pair_fragility("times_koed"),
        "bout_subbed_rate": pair_fragility("times_subbed"),
        "bout_kd15": pair("kd15_l5"),
        "bout_sub15": pair("sub15_l5"),
        "bout_slpm": pair("slpm_l5"),
        "bout_ctrl_pct": pair("ctrl_pct_l5"),
        "bout_elo_gap": gap("elo"),
        "bout_min_fights": pair("n_fights", "min"),
        "bout_max_layoff_days": pair("layoff_days", "max"),
        "bout_max_age": pair("age", "max"),
    }


_ELO_SCORES = {"fighter1": 1.0, "fighter2": 0.0, "draw": 0.5}


def build_feature_rows(
    bouts: list[Bout],
    tott_by_name: dict[str, dict],
    regional_by_name: dict[str, list[dict]] | None = None,
    elo_k: float = 32.0,
    seed: int = 42,
    elo_experience_boost: float = 0.0,
    elo_finish_multiplier: float = 1.0,
) -> list[dict]:
    """Replay bouts chronologically; emit one modeling row per decisive fight.

    Draws and no-contests produce no row (no label) but still update fighter
    histories — a draw is real cage time and real absorbed damage.

    Bouts with winner == 'upcoming' (a future card) emit a row with
    label=None built from history as of the card date, are never corner-
    swapped, and leave histories and Elo untouched — nothing has happened.
    """
    from octagon.db.parsing import normalize_name
    from octagon.features.research import pairing_research
    from octagon.features.style import style_scores as _style_scores

    rng = random.Random(seed)
    elo = Elo(k=elo_k)
    # Separate books on strike/grapple rate diffs, not W/L.
    strike_elo = Elo(k=elo_k)
    grapple_elo = Elo(k=elo_k)
    histories: dict[str, FighterHistory] = {}
    rows: list[dict] = []
    regional_by_name = regional_by_name or {}

    for bout in bouts:
        on_date = date_type.fromisoformat(bout.date)
        snaps = {}
        for corner, name in [("f1", bout.fighter1), ("f2", bout.fighter2)]:
            history = histories.setdefault(name, FighterHistory())
            regional = regional_by_name.get(normalize_name(name))
            snaps[corner] = fighter_snapshot(
                history, on_date, tott_by_name.get(name), elo.get(name),
                regional_fights=regional)
            snaps[corner]["strike_elo"] = strike_elo.get(name)
            snaps[corner]["grapple_elo"] = grapple_elo.get(name)

        if bout.winner in ("fighter1", "fighter2", "upcoming"):
            row = {
                "fight_id": bout.fight_id,
                "date": bout.date,
                "weight_class": bout.weight_class,
                "gender": "F" if (bout.weight_class or "").startswith("Women") else "M",
                "title_fight": bout.title_fight,
                "scheduled_rounds": bout.scheduled_rounds,
                "f1_name": bout.fighter1,
                "f2_name": bout.fighter2,
                "f1_odds": bout.odds1,
                "f2_odds": bout.odds2,
                "label": {"fighter1": 1, "fighter2": 0}.get(bout.winner),
                "method": bout.method,
                "end_round": bout.end_round,
                "swapped": 0,
            }
            for key, value in snaps["f1"].items():
                row[f"f1_{key}"] = value
            for key, value in snaps["f2"].items():
                row[f"f2_{key}"] = value
            for key in snaps["f1"]:
                a, b = snaps["f1"][key], snaps["f2"][key]
                row[f"diff_{key}"] = (a - b) if a is not None and b is not None else None
            for key, value in matchup_features(snaps["f1"], snaps["f2"]).items():
                row[f"diff_{key}"] = value
            anti, sym = pairing_research(
                histories[bout.fighter1], histories[bout.fighter2],
                bout.fighter1, bout.fighter2, on_date)
            for key, value in anti.items():
                row[f"diff_{key}"] = value
            row.update(sym)
            row.update(bout_features(snaps["f1"], snaps["f2"]))
            if row["label"] is not None and rng.random() < 0.5:
                row = swap_corners(row)
            rows.append(row)

        if bout.winner == "upcoming":  # nothing happened yet — no updates
            continue

        # Only after the snapshots: append this fight to both histories.
        for name, opp_name, own, opp, opp_snap, result in [
            (bout.fighter1, bout.fighter2, bout.stats1, bout.stats2, snaps["f2"],
             {"fighter1": "win", "fighter2": "loss"}.get(bout.winner, bout.winner)),
            (bout.fighter2, bout.fighter1, bout.stats2, bout.stats1, snaps["f1"],
             {"fighter1": "loss", "fighter2": "win"}.get(bout.winner, bout.winner)),
        ]:
            histories[name].fights.append(PastFight(
                date=on_date, result=result, method=bout.method,
                end_round=bout.end_round, duration_s=bout.duration_s,
                stats=own, opp_stats=opp, opp_elo_pre=opp_snap["elo"],
                opponent=opp_name, opp_style=_style_scores(opp_snap),
                own_elo_pre=elo.get(name)))
        if bout.winner != "nc":  # nothing was decided in a no-contest
            # Histories were just appended, so "prior fights" is length - 1.
            k1 = experience_multiplier(len(histories[bout.fighter1].fights) - 1,
                                       elo_experience_boost)
            k2 = experience_multiplier(len(histories[bout.fighter2].fights) - 1,
                                       elo_experience_boost)
            mov = (elo_finish_multiplier if bout.method in ("KO/TKO", "SUB")
                   else 1.0)
            elo.update(bout.fighter1, bout.fighter2, _ELO_SCORES[bout.winner],
                       k_multiplier=mov, k_multiplier_a=k1, k_multiplier_b=k2)
            evidence = _domain_evidence(bout.duration_s)
            strike_score = _striking_score(bout)
            if strike_score is not None:
                strike_elo.update(bout.fighter1, bout.fighter2, strike_score,
                                  k_multiplier=evidence)
            grapple_score = _grappling_score(bout)
            if grapple_score is not None:
                grapple_elo.update(bout.fighter1, bout.fighter2, grapple_score,
                                   k_multiplier=evidence)

    return rows


# Minutes of prior evidence. A 20-second exchange moves domain Elo less than
# a 15-minute fight; the observed score itself stays who-won-the-domain.
_DOMAIN_PRIOR_MINUTES = 5.0


def _domain_evidence(duration_s: int | None) -> float:
    if not duration_s:
        return 1.0
    minutes = duration_s / 60.0
    return minutes / (minutes + _DOMAIN_PRIOR_MINUTES)


def _soft_score(diff: float, scale: float) -> float:
    """Map a stat differential to (0, 1). +scale is about 0.73; large gaps saturate."""
    return 1.0 / (1.0 + math.exp(-diff / scale))


def _striking_score(bout: Bout) -> float | None:
    """Fighter1's striking score from significant strikes landed per minute."""
    if not bout.stats1 or not bout.stats2 or not bout.duration_s:
        return None
    a, b = bout.stats1.get("sig_landed"), bout.stats2.get("sig_landed")
    if a is None or b is None:
        return None
    minutes = bout.duration_s / 60.0
    return _soft_score((a - b) / minutes, scale=2.0)


def _grappling_score(bout: Bout) -> float | None:
    """Fighter1's grappling score. Two minutes of control counts as one takedown."""
    if not bout.stats1 or not bout.stats2 or not bout.duration_s:
        return None
    td_a, td_b = bout.stats1.get("td_landed"), bout.stats2.get("td_landed")
    if td_a is None or td_b is None:
        return None
    ctrl_a = bout.stats1.get("ctrl_seconds") or 0
    ctrl_b = bout.stats2.get("ctrl_seconds") or 0
    composite = (td_a - td_b) + (ctrl_a - ctrl_b) / 120.0
    return _soft_score(composite / (bout.duration_s / 900.0), scale=2.0)


def swap_corners(row: dict) -> dict:
    """Exchange the two fighters in an assembled row.

    f1_*/f2_* swap, diff_* negates, the label flips. Applying this twice
    must return the original row — tests rely on that involution.
    """
    swapped = dict(row)
    for key in row:
        if key.startswith("f1_"):
            other = "f2_" + key[3:]
            swapped[key], swapped[other] = row[other], row[key]
        elif key.startswith("diff_"):
            swapped[key] = -row[key] if row[key] is not None else None
    swapped["label"] = 1 - row["label"]
    swapped["swapped"] = 1 - row["swapped"]
    return swapped


def load_bouts(conn: sqlite3.Connection) -> list[Bout]:
    """Read fights in true chronological order.

    Within one event the CSV lists the main event first, but prelims happen
    first in real time — and in the old tournament era one man fought several
    times in a night, so intra-event order genuinely matters for his record.
    Descending fight_id within a date approximates card order.
    """
    stats: dict[tuple[int, str], dict] = {}
    for row in conn.execute("SELECT * FROM fight_stats"):
        stats[(row["fight_id"], row["corner"])] = dict(row)

    odds: dict[int, tuple[float, float]] = {
        row["fight_id"]: (row["fighter1_odds"], row["fighter2_odds"])
        for row in conn.execute("SELECT * FROM odds")
    }

    bouts = []
    for row in conn.execute("SELECT * FROM fights ORDER BY date ASC, fight_id DESC"):
        fid = row["fight_id"]
        bouts.append(Bout(
            fight_id=fid, date=row["date"],
            fighter1=row["fighter1"], fighter2=row["fighter2"],
            winner=row["winner"], method=row["method"],
            end_round=row["end_round"], duration_s=row["duration_s"],
            weight_class=row["weight_class"], title_fight=row["title_fight"],
            scheduled_rounds=row["scheduled_rounds"],
            stats1=stats.get((fid, "fighter1")), stats2=stats.get((fid, "fighter2")),
            odds1=odds.get(fid, (None, None))[0], odds2=odds.get(fid, (None, None))[1],
        ))
    return bouts


def load_tott(conn: sqlite3.Connection) -> dict[str, dict]:
    """Tale-of-the-tape by name. Shared names map to None rather than guessing."""
    from octagon.db.parsing import normalize_name

    by_name: dict[str, list[dict]] = {}
    for row in conn.execute("SELECT uid, name, height_cm, reach_cm, stance, dob FROM fighters"):
        by_name.setdefault(row["name"], []).append(dict(row))
    profiles = {name: rows[0] for name, rows in by_name.items() if len(rows) == 1}
    # Match punctuation/accents only when the normalized profile is unique.
    # This joins fight-result "Waldo Cortes Acosta" to "Waldo Cortes-Acosta".
    normalized: dict[str, list[dict]] = {}
    for rows in by_name.values():
        for row in rows:
            normalized.setdefault(normalize_name(row["name"]), []).append(row)
    for row in conn.execute("SELECT fighter1, fighter2 FROM fights"):
        for name in row:
            candidates = normalized.get(normalize_name(name), [])
            if name not in profiles and len(candidates) == 1:
                profiles[name] = dict(candidates[0], name=name)
    # Verified UFC athlete, not the same-named 1977-born regional fighter:
    # https://ufcstats.com/fighter-details/52ef95b5860fb28c
    for row in by_name.get("Jean Silva", []):
        if row["uid"] == "52ef95b5860fb28c":
            profiles["Jean Silva"] = row
    # UFC explicitly bills Tarin under this profile slug. Fight-result CSVs
    # use Tarin, while the profile CSV still uses Malpica Rivera.
    # https://www.ufc.com/athlete/regina-malpica-rivera
    if "Regina Tarin" not in by_name and "Regina Malpica Rivera" in profiles:
        profiles["Regina Tarin"] = dict(profiles["Regina Malpica Rivera"], name="Regina Tarin")
    return profiles


def build_features(conn: sqlite3.Connection, elo_k: float, seed: int,
                   elo_experience_boost: float = 0.0,
                   elo_finish_multiplier: float = 1.0):
    """SQLite -> feature DataFrame (import pandas here to keep tests light)."""
    import pandas as pd
    from octagon.features.regional import load_regional

    rows = build_feature_rows(
        load_bouts(conn),
        load_tott(conn),
        regional_by_name=load_regional(conn),
        elo_k=elo_k,
        seed=seed,
        elo_experience_boost=elo_experience_boost,
        elo_finish_multiplier=elo_finish_multiplier,
    )
    return pd.DataFrame(rows)


def elo_kwargs(cfg: dict) -> dict:
    """The Elo settings build_feature_rows takes, read from config.yaml."""
    elo = cfg.get("elo") or {}
    return {
        "elo_k": float(elo.get("k_factor", 32.0)),
        "elo_experience_boost": float(elo.get("experience_boost", 0.0)),
        "elo_finish_multiplier": float(elo.get("finish_multiplier", 1.0)),
    }
