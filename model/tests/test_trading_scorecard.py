"""Closing-line value is per fill. Uncertainty resamples events, not bets."""

import json
from decimal import Decimal as D

from octagon.trading.scorecard import Fill, fills_from_journal, load_journal, summarize


def test_mean_clv_and_draw_settlement():
    fills = [
        Fill("e1", "T", "yes", D("0.40"), D(10), D("0.17"), D("0.55"), "yes", "paper"),
        Fill("e1", "U", "no", D("0.30"), D(4), D("0.06"), D("0.25"), "draw", "paper"),
    ]
    report = summarize(fills, n_bootstrap=20)
    assert report["mean_clv_cents"] == D("5")  # (15 + (-5)) / 2
    # YES wins: 10 - 4.00 - 0.17. Draw on NO: 2.00 - 1.20 - 0.06.
    assert report["roi"] == (D("5.83") + D("0.74")) / (D("4.17") + D("1.26"))


def test_interval_resamples_events():
    fills = [
        Fill("win", "A", "yes", D("0.40"), D(1), D("0.02"), D("0.50"), "yes", "paper"),
        Fill("win", "B", "yes", D("0.40"), D(1), D("0.02"), D("0.50"), "yes", "paper"),
        Fill("loss", "C", "yes", D("0.40"), D(1), D("0.02"), None, "no", "paper"),
    ]
    report = summarize(fills, n_bootstrap=50, seed=1)
    assert report["n_events"] == 2
    assert report["n_with_close"] == 2
    assert report["roi_ci95"][0] < report["roi_ci95"][1]


def test_journal_uses_the_last_prefight_mid(tmp_path):
    rows = [
        {"kind": "configuration", "data": {
            "espn_event_id": "night",
            "mappings": [{"ticker": "T", "yes_fighter": "A", "f1": "A", "f2": "B"}],
        }},
        {"kind": "prefight_price", "data": {"ticker": "T", "p_f1": "0.40"}},
        {"kind": "prefight_price", "data": {"ticker": "T", "p_f1": "0.62"}},
        {"kind": "decisions", "data": [{
            "ticker": "T", "action": "paper", "side": "yes", "price_dollars": "0.50",
            "contracts": 10, "fee_dollars": "0.18", "event_id": "night",
        }]},
        {"kind": "decisions", "data": [{"ticker": "T", "action": "skip", "reason": "no"}]},
    ]
    fills = fills_from_journal(rows, {"T": "yes"})
    assert len(fills) == 1
    assert fills[0].close_mid == D("0.62")
    assert fills[0].settlement == "yes"
    path = tmp_path / "observations.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    settlements = tmp_path / "settlements.json"
    settlements.write_text(json.dumps({"T": "yes"}))
    report = load_journal(path, settlements)
    assert report["n_fills"] == 1
    assert report["mean_clv_cents"] == 12.0
