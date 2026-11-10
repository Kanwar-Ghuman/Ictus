"""Does day-before context make the bot's number better?

"Context" is what `octagon fetch-context` saves for a card the day before:
YouTube comment lean, headline sentiment, short-notice and late-replacement
flags, and pro records for debutants. The bot does not use any of it. This
scores what would have happened if it had: for every finished fight with a
saved context, the bot's number as it stands against the same number after
`context.soft_adjust_p_f1`.

Rules that keep it honest:

* A card counts only if its context was fetched on or before fight day.
* The comparison is on log loss, where a confident wrong number costs most.
* No verdict until enough fights were actually moved by the context. A few
  cards cannot tell a small nudge from luck.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from octagon.eval.scorecard import actual_results, frozen_path, match_result
from octagon.models.market import predict_stack
from octagon.scraping import context as card_context
from octagon.trading.signal import STACK_A, STACK_B

# Fights the context has to have moved before the comparison means anything.
MIN_MOVED_FIGHTS = 40
MOVED = 1e-6
# Which signal a note from soft_adjust_p_f1 belongs to.
SIGNALS = {"YouTube": "YouTube lean", "headline": "Headline sentiment",
           "flagged": "Short notice or late replacement", "debut": "Debutant's pro record"}


def bot_number(p_skill: float, p_market: float | None) -> float:
    """What the bot bets: the line nudged by skill, or skill alone with no line."""
    if p_market is None or not math.isfinite(p_market):
        return float(p_skill)
    return float(predict_stack(STACK_A, STACK_B, np.asarray([p_market]), np.asarray([p_skill]))[0])


def card_rows(conn, frame: pd.DataFrame, payload: dict) -> list[dict]:
    """One row per finished fight: the label, the bot's number, and the nudged number."""
    results = actual_results(conn, str(frame["date"].iat[0])[:10])
    rows = []
    for _, saved in frame.iterrows():
        f1, f2 = saved["f1_name"], saved["f2_name"]
        result, f1_corner = match_result(results, f1, f2)
        if result is None or result["winner"] not in ("fighter1", "fighter2"):
            continue
        line = saved.get("p_market")
        line = float(line) if line is not None and math.isfinite(float(line)) else None
        skill = float(saved["p_skill"])
        base = bot_number(skill, line)
        nudged, notes = card_context.adjust_bout(
            payload, f1, f2, base,
            f1_n_fights=float(saved.get("f1_ufc_fights") or 0),
            f2_n_fights=float(saved.get("f2_ufc_fights") or 0),
            has_market_odds=line is not None, skill_p=skill)
        signals = card_context.bout_signals(payload, f1, f2)
        rows.append({
            "bout": f"{f1} vs {f2}", "label": int(result["winner"] == f1_corner),
            "base": base, "nudged": nudged,
            # Only signals that changed the number, not ones merely noted.
            "signals": sorted({name for key, name in SIGNALS.items()
                               for note in notes if key in note and "not applied" not in note}),
            "youtube_lean": signals["youtube_lean"],
            "youtube_n_signals": signals["youtube_n_signals"],
        })
    return rows


def collect(conn, cards_dir: Path) -> tuple[list[dict], list[dict]]:
    """(every scored fight, one summary line per card that has a saved context)."""
    rows, cards = [], []
    for card_path in sorted(cards_dir.glob("*.yaml")):
        payload = card_context.load_context(card_path)
        frozen = frozen_path(card_path.stem)
        if payload is None or not frozen.exists():
            continue
        frame = pd.read_parquet(frozen)
        info = {"card": card_path.stem, "date": str(frame["date"].iat[0])[:10],
                "fetched_at": payload.get("fetched_at"), "fights": 0, "status": "scored"}
        if "p_skill" not in frame:
            info["status"] = "predictions too old to score"
        elif not info["fetched_at"]:
            info["status"] = "saved context has no fetch date; left out"
        elif str(info["fetched_at"])[:10] > info["date"]:
            info["status"] = "context fetched after the fights; left out"
        else:
            scored = card_rows(conn, frame, payload)
            for row in scored:
                row["card"] = card_path.stem
            rows += scored
            info["fights"] = len(scored)
            if not scored:
                info["status"] = "no results in the database yet"
        cards.append(info)
    return rows, cards


def _log_loss(labels: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(labels * np.log(p) + (1 - labels) * np.log(1 - p)).mean())


def compare(rows: list[dict]) -> dict | None:
    """Log loss and winners called, before and after the nudge."""
    if not rows:
        return None
    labels = np.array([r["label"] for r in rows], dtype=float)
    base = np.array([r["base"] for r in rows])
    nudged = np.array([r["nudged"] for r in rows])
    return {"n": len(rows),
            "base_log_loss": _log_loss(labels, base), "nudged_log_loss": _log_loss(labels, nudged),
            "base_correct": int(((base > 0.5) == labels).sum()),
            "nudged_correct": int(((nudged > 0.5) == labels).sum())}


def youtube_direction(rows: list[dict]) -> dict:
    """When YouTube clearly leaned one way, how often was it right, and against the bot?"""
    leaned = [r for r in rows if r["youtube_lean"] is not None
              and r["youtube_n_signals"] >= card_context.YOUTUBE_MIN_SIGNALS
              and abs(r["youtube_lean"]) > 0.15]
    right = [r for r in leaned if (r["youtube_lean"] > 0) == bool(r["label"])]
    disagree = [r for r in leaned if (r["youtube_lean"] > 0) != (r["base"] > 0.5)]
    return {"leaned": len(leaned), "right": len(right), "disagreed": len(disagree),
            "right_when_disagreed": sum((r["youtube_lean"] > 0) == bool(r["label"])
                                        for r in disagree)}


def summarize(rows: list[dict]) -> dict:
    moved = [r for r in rows if abs(r["nudged"] - r["base"]) > MOVED]
    by_signal = {name: compare([r for r in moved if name in r["signals"]])
                 for name in SIGNALS.values()}
    return {"all": compare(rows), "moved": compare(moved), "by_signal": by_signal,
            "youtube": youtube_direction(rows), "verdict": verdict(compare(moved))}


def verdict(moved: dict | None) -> str:
    n = moved["n"] if moved else 0
    if n < MIN_MOVED_FIGHTS:
        return (f"Too early to say. The context has moved {n} finished fights; "
                f"this needs {MIN_MOVED_FIGHTS} before it can tell a real effect from luck.")
    gain = moved["base_log_loss"] - moved["nudged_log_loss"]
    if gain > 0:
        return (f"The context helped on {n} fights (log loss better by {gain:.4f}). "
                "Worth testing as a real input.")
    return (f"The context did not help on {n} fights (log loss worse by {-gain:.4f}). "
            "Keep it out of the bot's number.")


def render(summary: dict, cards: list[dict]) -> str:
    def line(label: str, result: dict | None) -> str:
        if result is None:
            return f"| {label} | 0 | | | | |"
        return (f"| {label} | {result['n']} | {result['base_log_loss']:.4f} | "
                f"{result['nudged_log_loss']:.4f} | {result['base_correct']} | "
                f"{result['nudged_correct']} |")

    yt = summary["youtube"]
    lines = [
        "# Does day-before context improve the bot's number?", "",
        "The bot does not use YouTube lean, headline sentiment, short-notice flags, or",
        "debutants' pro records. This compares its number as it stands with the same",
        "number after those nudges, on fights that have finished. Lower log loss is better.", "",
        f"**{summary['verdict']}**", "",
        "| Fights | n | Log loss, bot's number | Log loss, with context | Winners called | With context |",
        "|---|---:|---:|---:|---:|---:|",
        line("All scored fights", summary["all"]),
        line("Fights the context moved", summary["moved"]),
    ]
    lines += [line(f"Moved by: {name}", result) for name, result in summary["by_signal"].items()]
    lines += [
        "", "## YouTube on its own", "",
        f"YouTube comments clearly leaned to one fighter in {yt['leaned']} finished fights and",
        f"that fighter won {yt['right']} of them. It disagreed with the bot's pick in",
        f"{yt['disagreed']}, and was right in {yt['right_when_disagreed']} of those.", "",
        "## Cards", "", "| Card | Date | Context fetched | Fights scored | Status |",
        "|---|---|---|---:|---|",
    ]
    lines += [f"| {c['card']} | {c['date']} | {c['fetched_at'] or ''} | {c['fights']} | {c['status']} |"
              for c in cards]
    lines += ["", "Rebuild with `uv run python -m octagon score-context` after `refresh-data`.", ""]
    return "\n".join(lines)


def run(conn, cards_dir: Path, report: Path) -> dict:
    rows, cards = collect(conn, cards_dir)
    summary = summarize(rows)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render(summary, cards), encoding="utf-8")
    report.with_suffix(".json").write_text(
        json.dumps({"summary": summary, "cards": cards, "fights": rows}, indent=2), encoding="utf-8")
    return summary
