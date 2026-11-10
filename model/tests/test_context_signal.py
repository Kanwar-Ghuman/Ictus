"""Measuring what day-before context would add to the bot's number."""

from datetime import date

import pytest

from octagon.eval import context_signal as cs
from octagon.trading.prepare import CardPreparer


def row(label, base, nudged, signals=(), lean=None, n=0):
    return {"label": label, "base": base, "nudged": nudged, "signals": list(signals),
            "youtube_lean": lean, "youtube_n_signals": n}


def test_the_bots_number_is_the_stack_or_skill_alone():
    assert cs.bot_number(0.8, None) == 0.8
    assert cs.bot_number(0.8, float("nan")) == 0.8
    stacked = cs.bot_number(0.8, 0.6)
    assert 0.6 < stacked < 0.8  # the line, pushed a little toward the skill number


def test_only_fights_the_context_moved_are_compared():
    rows = [row(1, 0.6, 0.6), row(1, 0.5, 0.56, ["YouTube lean"]), row(0, 0.5, 0.44, ["YouTube lean"])]
    summary = cs.summarize(rows)
    assert summary["all"]["n"] == 3 and summary["moved"]["n"] == 2
    assert summary["moved"]["nudged_log_loss"] < summary["moved"]["base_log_loss"]
    assert summary["by_signal"]["YouTube lean"]["n"] == 2
    assert summary["by_signal"]["Headline sentiment"] is None


def test_no_verdict_until_enough_fights_were_moved():
    few = cs.verdict({"n": 7, "base_log_loss": 0.66, "nudged_log_loss": 0.62})
    assert few.startswith("Too early to say")
    enough = {"n": cs.MIN_MOVED_FIGHTS, "base_log_loss": 0.66, "nudged_log_loss": 0.62}
    assert "helped" in cs.verdict(enough)
    worse = enough | {"nudged_log_loss": 0.70}
    assert "did not help" in cs.verdict(worse)
    assert cs.verdict(None).startswith("Too early to say")


def test_youtube_is_scored_on_its_own_and_against_the_bot():
    rows = [
        row(1, 0.7, 0.7, lean=0.5, n=10),    # leaned f1, bot agreed, f1 won
        row(0, 0.7, 0.7, lean=-0.5, n=10),   # leaned f2 against the bot, f2 won
        row(1, 0.7, 0.7, lean=-0.5, n=10),   # leaned f2 against the bot, f1 won
        row(1, 0.7, 0.7, lean=0.5, n=2),     # too few comments to count
        row(1, 0.7, 0.7, lean=0.05, n=10),   # no clear lean
    ]
    assert cs.youtube_direction(rows) == {"leaned": 3, "right": 2, "disagreed": 2,
                                          "right_when_disagreed": 1}


@pytest.fixture
def preparer(tmp_path):
    (tmp_path / "cards").mkdir()
    (tmp_path / "cards" / "tonight.yaml").write_text("date: x")
    prep = CardPreparer(tmp_path, tmp_path / "scratch")
    calls = []
    prep._fetch_context = lambda card: calls.append(card.name)
    return prep, calls, tmp_path


def wait_for_threads():
    import threading

    for thread in threading.enumerate():
        if thread is not threading.current_thread() and thread.daemon:
            thread.join(timeout=2)


def test_context_is_fetched_once_and_only_close_to_the_fights(preparer):
    prep, calls, root = preparer
    today = date(2026, 11, 13)
    prep.ensure_context("tonight", "2026-11-20", today)  # a week out: news would go stale
    prep.ensure_context("tonight", "2026-11-12", today)  # already happened
    wait_for_threads()
    assert calls == []
    prep.ensure_context("tonight", "2026-11-14", today)  # the day before
    prep.ensure_context("tonight", "2026-11-14", today)
    wait_for_threads()
    assert calls == ["tonight.yaml"]


def test_a_saved_context_is_never_fetched_again(preparer):
    prep, calls, root = preparer
    saved = root / "data" / "card_context"
    saved.mkdir(parents=True)
    (saved / "tonight.json").write_text("{}")
    prep.ensure_context("tonight", "2026-11-14", date(2026, 11, 14))
    wait_for_threads()
    assert calls == []
