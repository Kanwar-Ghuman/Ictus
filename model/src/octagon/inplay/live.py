"""Turn an ESPN fightcenter bout into between-rounds model inputs.

ESPN reports cumulative fight totals as display strings ("13/26", "1:34").
These map one-to-one to the ufcstats round columns used in training. During
a round ESPN refreshes them only every ~30 s and the broadcast is ahead of
it, so inputs are accepted only during the break (STATUS_END_OF_ROUND),
when round k's totals are complete.
"""

from __future__ import annotations

import re

BREAK_STATUS = "STATUS_END_OF_ROUND"
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


def parse_stats(stats: dict) -> dict[str, float]:
    """ESPN fighter stats -> cumulative model stats (see model.DIFF_STATS)."""
    out: dict[str, float] = {}
    for field, name in PAIR_FIELDS.items():
        out[f"{name}_l"], out[f"{name}_a"] = _pair(stats.get(field, ""))
    out["kd"] = _count(stats.get("knockDowns", ""))
    out["sub"] = _count(stats.get("submissions", ""))
    out["ctrl"] = _seconds(stats.get("timeInControl", ""))
    return out


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
    by_name = {normalize(str((bout.get(c) or {}).get("name", ""))): bout.get(c) or {}
               for c in ("fighter_a", "fighter_b")}
    a, b = by_name.get(normalize(f1)), by_name.get(normalize(f2))
    if a is None or b is None:
        raise ValueError("ESPN fighters do not match the card")
    return round_k, parse_stats(a.get("stats") or {}), parse_stats(b.get("stats") or {})
