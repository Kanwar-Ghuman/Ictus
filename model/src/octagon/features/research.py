"""Point-in-time fight research: form, rematches, common opponents.

Built only from each fighter's history *before* the bout being scored, so
these inherit the same leakage contract as the rest of the feature table.
Pairing features (H2H, common opponents) have no per-corner raw counterpart
— they are antisymmetric (or symmetric) by construction.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_type

_STYLE_KEYS = ("striker", "wrestler", "grappler", "pressure")
_DECISIVE = ("win", "loss")
_FINISH = ("KO/TKO", "SUB")
_STYLE_FLOOR = 0.15  # below this, a debut/empty profile is not an archetype


def primary_style(scores: dict | None) -> str | None:
    """Dominant archetype, or None when the profile is too thin to name."""
    if not scores:
        return None
    key = max(scores, key=scores.get)
    return key if float(scores[key]) >= _STYLE_FLOOR else None


def form_snapshot(
    fights: list,
    on_date: date_type,
    elo_rating: float,
) -> dict[str, float | None]:
    """Recent-form and style-conditioned records from a fighter's past bouts."""
    decisive = [f for f in fights if f.result in _DECISIVE]

    last = fights[-1] if fights else None
    ko_losses = [f for f in fights if f.result == "loss" and f.method == "KO/TKO"]

    def _form(window: list) -> float | None:
        if not window:
            return None
        scores = []
        for f in window:
            expected = 1.0 / (1.0 + 10.0 ** (
                (f.opp_elo_pre - f.own_elo_pre) / 400.0))
            # Outperforming pre-fight expectations is positive form. Losing
            # to an elite opponent should hurt LESS than losing to a novice.
            scores.append(2.0 * (float(f.result == "win") - expected))
        return sum(scores) / len(scores)

    vs: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # wins, n
    for f in decisive:
        style = primary_style(getattr(f, "opp_style", None))
        if style is None:
            continue
        vs[style][1] += 1
        if f.result == "win":
            vs[style][0] += 1

    bar = max(1600.0, float(elo_rating or 1500.0))
    quality = [f for f in decisive if f.opp_elo_pre >= bar]
    quality_wins = [f for f in quality if f.result == "win"]

    comebacks: list[bool] = []
    for i, f in enumerate(fights[1:], 1):
        if fights[i - 1].result == "loss" and f.result in _DECISIVE:
            comebacks.append(f.result == "win")

    statted = [f for f in fights if f.stats and f.opp_stats and f.duration_s]
    wars = [f for f in statted[-5:] if _was_war(f)]

    out: dict[str, float | None] = {
        "last_result": (
            {"win": 1.0, "loss": -1.0}.get(last.result, 0.0) if last else None),
        "last_was_finish": (
            (1.0 if last.method in _FINISH else 0.0) if last else None),
        "last_end_round": (
            float(last.end_round) if last and last.end_round else None),
        "days_since_ko": (
            float((on_date - ko_losses[-1].date).days) if ko_losses else None),
        "form_l3": _form([f for f in decisive[-3:]]),
        "form_l5": _form([f for f in decisive[-5:]]),
        # Rate against elite opposition, not "elite wins / whole career".
        # One elite fight is not a rate: leave it missing and keep the count.
        "quality_n": float(len(quality)) if decisive else None,
        "quality_win_rate": (
            len(quality_wins) / len(quality) if len(quality) >= 2 else None),
        "comeback_rate": (
            sum(comebacks) / len(comebacks) if comebacks else None),
        "war_share_l5": (
            len(wars) / len(statted[-5:]) if statted[-5:] else None),
    }
    for key in _STYLE_KEYS:
        wins_n, n = vs[key]
        out[f"vs_{key}_win_pct"] = (wins_n / n) if n >= 2 else None
    return out


def _was_war(fight) -> bool:
    """A long, high-output fight — the kind that leaves damage and tests cardio."""
    if not fight.duration_s or fight.duration_s < 600:
        return False
    landed = (fight.stats.get("sig_landed") or 0) + (fight.opp_stats.get("sig_landed") or 0)
    return landed / (fight.duration_s / 60.0) >= 8.0


def pairing_research(
    history1,
    history2,
    name1: str,
    name2: str,
    on_date: date_type,
) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """Rematch and common-opponent research for this specific pairing.

    Returns (antisymmetric features, symmetric bout_ features). Under a
    corner swap the antisym values negate and the bout_ values stay put.
    """
    meetings = [f for f in history1.fights if getattr(f, "opponent", None) == name2]
    decisive_h2h = [f for f in meetings if f.result in _DECISIVE]
    wins = sum(1 for f in decisive_h2h if f.result == "win")
    losses = len(decisive_h2h) - wins
    last = meetings[-1] if meetings else None

    opps1 = {f.opponent for f in history1.fights if getattr(f, "opponent", None)}
    opps2 = {f.opponent for f in history2.fights if getattr(f, "opponent", None)}
    shared = (opps1 & opps2) - {name1, name2}

    def win_rate_vs(history, opponents: set[str]) -> float | None:
        bouts = [f for f in history.fights
                 if getattr(f, "opponent", None) in opponents and f.result in _DECISIVE]
        if not bouts:
            return None
        return sum(1 for f in bouts if f.result == "win") / len(bouts)

    r1, r2 = win_rate_vs(history1, shared), win_rate_vs(history2, shared)
    anti = {
        "h2h_edge": (float(wins - losses) if decisive_h2h else None),
        "h2h_last": (
            {"win": 1.0, "loss": -1.0}.get(last.result) if last else None),
        "common_record": (
            (r1 - r2) if r1 is not None and r2 is not None else None),
    }
    sym = {
        "bout_h2h_meetings": float(len(meetings)) if meetings else None,
        "bout_h2h_days": (
            float((on_date - last.date).days) if last else None),
        "bout_common_n": float(len(shared)) if shared else None,
    }
    return anti, sym


def _num(row: dict, key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if value != value else value  # NaN check


def _archetype(row: dict, prefix: str) -> str | None:
    scores = {key: (_num(row, f"{prefix}_style_{key}") or 0.0) for key in _STYLE_KEYS}
    if max(scores.values()) <= 0:
        slpm = _num(row, f"{prefix}_slpm_l5") or 0.0
        td = _num(row, f"{prefix}_td15_l5") or 0.0
        if slpm <= 0 and td <= 0:
            return None
        scores = {
            "striker": slpm,
            "wrestler": td,
            "grappler": _num(row, f"{prefix}_sub15_l5") or 0.0,
            "pressure": _num(row, f"{prefix}_ctrl_pct_l5") or 0.0,
        }
    ordered = sorted(scores, key=scores.get, reverse=True)
    # Saturated scores can tie (a busy wrestler is also a busy striker).
    # Do not invent a dominant style from dictionary insertion order.
    if abs(scores[ordered[0]] - scores[ordered[1]]) < 1e-9:
        return None
    return ordered[0]


def _form_word(value: float) -> str:
    if value >= 0.25:
        return "hot"
    if value <= -0.25:
        return "cold"
    return "mixed"


def research_brief(row: dict, f1: str, f2: str) -> list[str]:
    """Readable matchup notes for a prediction report. Never a probability."""
    lines: list[str] = []

    a1, a2 = _archetype(row, "f1"), _archetype(row, "f2")
    if a1 and a2:
        if a1 == a2:
            lines.append(f"Style: both profile as {a1}s — a same-look fight.")
        else:
            lines.append(f"Style: {f1} profiles as a {a1}; {f2} as a {a2}.")

    slpm1, slpm2 = _num(row, "f1_slpm_l5"), _num(row, "f2_slpm_l5")
    td1, td2 = _num(row, "f1_td15_l5"), _num(row, "f2_td15_l5")
    tdd1, tdd2 = _num(row, "f1_td_def_l5"), _num(row, "f2_td_def_l5")
    if td1 is not None and tdd2 is not None and td1 >= 2.0:
        lines.append(
            f"Wrestling contrast: {f1} lands {td1:.1f} takedowns/15 into "
            f"{f2}'s {tdd2:.0%} TDD.")
    elif td2 is not None and tdd1 is not None and td2 >= 2.0:
        lines.append(
            f"Wrestling contrast: {f2} lands {td2:.1f} takedowns/15 into "
            f"{f1}'s {tdd1:.0%} TDD.")
    elif slpm1 is not None and slpm2 is not None and abs(slpm1 - slpm2) >= 1.5:
        louder = f1 if slpm1 > slpm2 else f2
        lines.append(
            f"Pace: {louder} is the volume striker "
            f"({max(slpm1, slpm2):.1f} vs {min(slpm1, slpm2):.1f} SLpM).")

    form1, form2 = _num(row, "f1_form_l5"), _num(row, "f2_form_l5")
    last1, last2 = _num(row, "f1_last_result"), _num(row, "f2_last_result")
    form_bits = []
    if form1 is not None and form2 is not None and abs(form1 - form2) >= 0.2:
        hotter = f1 if form1 > form2 else f2
        form_bits.append(
            f"{hotter} holds the pre-fight-expectation-adjusted form edge "
            f"({_form_word(form1)} vs {_form_word(form2)} over the last 5)")
    last_bits = []
    if last1 is not None:
        last_bits.append(f"{f1} {'won' if last1 > 0 else 'lost'} last time out")
    if last2 is not None:
        last_bits.append(f"{f2} {'won' if last2 > 0 else 'lost'} last time out")
    if form_bits:
        lines.append("Form: " + form_bits[0] + ".")
    elif last_bits:
        lines.append("Last fights: " + "; ".join(last_bits) + ".")

    vs1 = _num(row, "f1_vs_wrestler_win_pct") if a2 == "wrestler" else (
        _num(row, "f1_vs_striker_win_pct") if a2 == "striker" else (
            _num(row, "f1_vs_grappler_win_pct") if a2 == "grappler" else None))
    vs2 = _num(row, "f2_vs_wrestler_win_pct") if a1 == "wrestler" else (
        _num(row, "f2_vs_striker_win_pct") if a1 == "striker" else (
            _num(row, "f2_vs_grappler_win_pct") if a1 == "grappler" else None))
    if vs1 is not None and a2:
        lines.append(f"Style record: {f1} is {vs1:.0%} against {a2}s in the UFC.")
    elif vs2 is not None and a1:
        lines.append(f"Style record: {f2} is {vs2:.0%} against {a1}s in the UFC.")

    meetings = _num(row, "bout_h2h_meetings")
    last_h2h = _num(row, "diff_h2h_last")
    days = _num(row, "bout_h2h_days")
    if meetings:
        winner = f1 if (last_h2h or 0) > 0 else f2 if (last_h2h or 0) < 0 else None
        ago = f" {int(days)} days ago" if days is not None else ""
        if winner:
            lines.append(
                f"Rematch: they have met {int(meetings)} time"
                f"{'s' if meetings != 1 else ''} previously; "
                f"{winner} won the last one{ago}.")
        else:
            lines.append(
                f"Rematch: {int(meetings)} previous meeting"
                f"{'s' if meetings != 1 else ''}{ago}.")

    common = _num(row, "bout_common_n")
    shared_edge = _num(row, "diff_common_record")
    if common:
        if shared_edge is not None and abs(shared_edge) >= 0.05:
            better = f1 if shared_edge > 0 else f2
            lines.append(
                f"Common opponents ({int(common)}): {better}'s record "
                f"against them is better.")
        else:
            lines.append(f"Common opponents: {int(common)} shared names on the record.")

    return lines
