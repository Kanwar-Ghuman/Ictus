"""Turn an ESPN fightcenter bout into in-play model inputs.

ESPN reports cumulative fight totals as display strings ("13/26", "1:34").
These map one-to-one to the ufcstats round columns used in training. Totals
during a round are partial and the broadcast is ahead of them; the live path
still prices them against the round clock. Break totals stay on
STATUS_END_OF_ROUND, when round k is complete.
"""

from __future__ import annotations

import re

BREAK_STATUS = "STATUS_END_OF_ROUND"
ROUND_SECONDS = 300
PAIR_FIELDS = {"sigStrikes": "sig", "totalStrikes": "tot", "headStrikes": "head",
               "bodyStrikes": "body", "legStrikes": "leg", "takedowns": "td"}


def _pair(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text or "")
    if not match:
        raise ValueError(f"Unparseable ESPN pair {text!r}")
    landed, attempted = int(match.group(1)), int(match.group(2))
    if landed > attempted:
        raise ValueError("ESPN landed exceeds attempted")
    return landed, attempted


def _count(text: str) -> int:
    if not re.fullmatch(r"\s*\d+\s*", text or ""):
        raise ValueError(f"Unparseable ESPN count {text!r}")
    return int(text)


def _seconds(text: str) -> int:
    match = re.fullmatch(r"\s*(\d+):([0-5]\d)\s*", text or "")
    if not match:
        raise ValueError(f"Unparseable ESPN time {text!r}")
    return int(match.group(1)) * 60 + int(match.group(2))


# Bottom fighter, opponent has at least twice the control. A sub attempt
# only counts when the gap is still under three minutes.
HELD_GAP_SECONDS = 90
HELD_CONTROL_RATIO = 2
DOMINANT_GAP_SECONDS = 180


def held_without_threat(stats: dict, opponent: dict) -> bool:
    """Fighter is being controlled and has no knockdown or live submission path."""
    gap = opponent.get("ctrl", 0) - stats.get("ctrl", 0)
    if gap < HELD_GAP_SECONDS:
        return False
    if opponent.get("ctrl", 0) < HELD_CONTROL_RATIO * max(stats.get("ctrl", 0), 1):
        return False
    if stats.get("kd", 0) > 0:
        return False
    if stats.get("sub", 0) > 0 and gap < DOMINANT_GAP_SECONDS:
        return False
    return True


def parse_stats(stats: dict) -> dict[str, float]:
    """ESPN fighter stats -> cumulative model stats (see model.DIFF_STATS)."""
    out: dict[str, float] = {}
    for field, name in PAIR_FIELDS.items():
        out[f"{name}_l"], out[f"{name}_a"] = _pair(stats.get(field, ""))
    out["kd"] = _count(stats.get("knockDowns", ""))
    out["sub"] = _count(stats.get("submissions", ""))
    out["ctrl"] = _seconds(stats.get("timeInControl", ""))
    return out


def _oriented_stats(bout: dict, f1: str, f2: str, normalize) -> tuple[dict, dict]:
    by_name = {normalize(str((bout.get(c) or {}).get("name", ""))): bout.get(c) or {}
               for c in ("fighter_a", "fighter_b")}
    a, b = by_name.get(normalize(f1)), by_name.get(normalize(f2))
    if a is None or b is None:
        raise ValueError("ESPN fighters do not match the card")
    return parse_stats(a.get("stats") or {}), parse_stats(b.get("stats") or {})


def fight_progress(bout: dict, f1: str, f2: str, normalize) -> tuple[float, dict, dict, str]:
    """(elapsed rounds, f1 stats, f2 stats, phase) while a bout is in progress.

    ``break`` is a completed round. ``live`` is the current round, with the
    ESPN clock counting down from five minutes. Anything else is refused.
    """
    if bout.get("status") != "in_progress":
        raise ValueError("Bout is not in progress")
    if bout.get("status_detail") == BREAK_STATUS:
        round_k, stats_1, stats_2 = break_inputs(bout, f1, f2, normalize)
        return float(round_k), stats_1, stats_2, "break"
    round_k = bout.get("round")
    if not isinstance(round_k, int) or isinstance(round_k, bool) or round_k < 1:
        raise ValueError("Unknown round")
    clock = bout.get("clock")
    if not isinstance(clock, str) or not clock.strip():
        raise ValueError("Live clock is missing")
    remaining = _seconds(clock)
    if remaining > ROUND_SECONDS:
        raise ValueError("Live clock is outside a five-minute round")
    elapsed = (round_k - 1) + (ROUND_SECONDS - remaining) / ROUND_SECONDS
    if elapsed <= 0:
        raise ValueError("Live clock has not started")
    stats_1, stats_2 = _oriented_stats(bout, f1, f2, normalize)
    return elapsed, stats_1, stats_2, "live"


def break_inputs(bout: dict, f1: str, f2: str, normalize) -> tuple[int, dict, dict]:
    """(completed round k, f1 stats, f2 stats) during a between-rounds break.

    Raises ValueError for anything else: live action, unknown status, stats
    missing or malformed, or fighter identities that do not match the card.
    """
    if bout.get("status") != "in_progress" or bout.get("status_detail") != BREAK_STATUS:
        raise ValueError("Not in a between-rounds break")
    round_k = bout.get("round")
    if not isinstance(round_k, int) or isinstance(round_k, bool) or round_k < 1:
        raise ValueError("Unknown completed round")
    stats_1, stats_2 = _oriented_stats(bout, f1, f2, normalize)
    return round_k, stats_1, stats_2
