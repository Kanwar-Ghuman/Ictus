"""API is read-only and 404s when reports are missing."""

import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from octagon.api import findings
from octagon.api.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """An API rooted at an empty temp directory, not the real reports/."""
    monkeypatch.setattr("octagon.config.project_root", lambda: tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "data" / "processed").mkdir(parents=True)
    (tmp_path / "config.yaml").write_text(
        "seed: 42\n"
        "data:\n  processed_dir: data/processed\n  db_path: data/ufc.db\n"
        "  media_path: data/fighter_media.json\n"
        "  media_image_dir: data/fighter_images\n"
        "splits:\n  train_end: '2021-12-31'\n  valid_end: '2023-12-31'\n"
        "abstain:\n  low: 0.45\n  high: 0.55\n", encoding="utf-8")
    findings.reset_cache()
    yield TestClient(create_app()), tmp_path
    findings.reset_cache()


def _write_split(root, split, n=200):
    rng = np.random.default_rng(0)
    p = rng.uniform(0.2, 0.8, n)
    pd.DataFrame({
        "fight_id": np.arange(n),
        "date": pd.date_range("2024-01-01", periods=n).astype(str),
        "f1_name": [f"A{i}" for i in range(n)], "f2_name": [f"B{i}" for i in range(n)],
        "weight_class": "Lightweight", "title_fight": 0,
        "label": (rng.uniform(size=n) < p).astype(int),
        "p_market": np.where(rng.uniform(size=n) < 0.7, p, np.nan),
        "p_lr": p, "p_gbm_cal": p, "p_blend": p,
    }).to_parquet(root / "reports" / f"predictions_{split}.parquet", index=False)
    findings.reset_cache()


def test_health_reports_whether_a_model_is_trained(client):
    api, _ = client
    body = api.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["trained"] is False


def test_overview_works_before_anything_has_been_trained(client):
    api, _ = client
    body = api.get("/api/overview").json()
    assert body["trained"] is False and body["model"] is None
    assert body["dataset"]["available"] is False
    assert body["abstain_band"] == [0.45, 0.55]
    assert "not betting advice" in body["disclaimer"].lower()


def test_missing_results_404_rather_than_returning_empty_numbers(client):
    api, _ = client
    for route in ("/api/metrics/test", "/api/calibration/test",
                  "/api/cards/nope", "/api/cards/nope/scorecard"):
        assert api.get(route).status_code == 404, route
    assert api.get("/api/cards").json() == []


def test_unknown_split_is_rejected(client):
    api, _ = client
    assert api.get("/api/metrics/train").status_code == 404


def test_metrics_scores_every_model_and_the_baselines(client):
    api, root = client
    _write_split(root, "test")
    body = api.get("/api/metrics/test").json()
    keys = [row["key"] for row in body["models"]]
    assert keys == ["p_market", "p_lr", "p_gbm_cal", "p_blend",
                    "p_blend_priced", "coin_flip"]
    for row in body["models"]:
        assert 0.0 <= row["accuracy"] <= 1.0
        assert row["log_loss"] > 0.0
    coin = next(r for r in body["models"] if r["key"] == "coin_flip")
    assert coin["log_loss"] == pytest.approx(0.6931, abs=1e-3)


def test_market_is_scored_only_on_fights_it_priced(client):
    """Comparing a full-sample model score to a partial market score is the
    easiest accidental way to claim an edge, so the paired row must match."""
    api, root = client
    _write_split(root, "test")
    rows = {r["key"]: r for r in api.get("/api/metrics/test").json()["models"]}
    assert rows["p_market"]["n"] == rows["p_blend_priced"]["n"]
    assert rows["p_market"]["n"] < rows["p_blend"]["n"]
    assert rows["p_market"]["priced_only"] is True


def test_abstain_curve_trades_coverage_for_accuracy(client):
    api, root = client
    _write_split(root, "test")
    points = api.get("/api/metrics/test").json()["abstain"]["points"]
    assert points[0]["coverage"] == pytest.approx(1.0)
    assert all(a["coverage"] >= b["coverage"]
               for a, b in zip(points, points[1:]))


def test_calibration_bins_are_populated_and_report_ece(client):
    api, root = client
    _write_split(root, "test")
    body = api.get("/api/calibration/test").json()
    blend = next(s for s in body["series"] if s["key"] == "p_blend")
    assert len(blend["bins"]) > 1
    assert all(b["n"] > 0 for b in blend["bins"])
    assert blend["ece"] >= 0.0


def test_thin_calibration_bins_are_dropped_but_still_count_toward_ece(client):
    """A five-fight bin lands on 0.0 or 1.0 by luck and would read as a
    dramatic miscalibration, so it is not plotted — but it is still real
    data, so it must not vanish from the error measure."""
    api, root = client
    _write_split(root, "test")
    loose = api.get("/api/calibration/test?min_count=1").json()
    strict = api.get("/api/calibration/test?min_count=50").json()
    thin = next(s for s in loose["series"] if s["key"] == "p_blend")
    thick = next(s for s in strict["series"] if s["key"] == "p_blend")

    assert len(thick["bins"]) < len(thin["bins"])
    assert all(b["n"] >= 50 for b in thick["bins"])
    assert thick["ece"] == pytest.approx(thin["ece"])


def test_a_model_with_no_predictions_is_omitted_not_shown_as_perfect(client, tmp_path):
    """The test era has no odds. An empty market series would score ECE
    0.000 and render as a flawless benchmark that was never evaluated."""
    api, root = client
    _write_split(root, "test")
    frame = pd.read_parquet(root / "reports" / "predictions_test.parquet")
    frame["p_market"] = np.nan
    frame.to_parquet(root / "reports" / "predictions_test.parquet", index=False)
    findings.reset_cache()

    body = api.get("/api/calibration/test").json()
    assert "p_market" not in [s["key"] for s in body["series"]]
    rows = api.get("/api/metrics/test").json()["models"]
    assert "p_market" not in [r["key"] for r in rows]


def test_api_exposes_no_write_routes():
    for route in create_app().routes:
        assert set(getattr(route, "methods", set())) <= {"GET", "HEAD"}, route


# --------------------------------------------------------------------------
# Cards: what the website's homepage reads (v2.7)
# --------------------------------------------------------------------------

def _write_card(root, slug, date, event="UFC Test Night", sections=("Main card",
                                                                    "Prelims")):
    """A frozen card file with the columns `octagon predict` writes."""
    from octagon.models import finish_round

    columns = finish_round.outcome_columns()
    rows = []
    for i, section in enumerate(sections):
        joint = {c: 1.0 / len(columns) for c in columns}
        rows.append({"date": date, "event": event,
                     "f1_name": f"Ann Alpha {i}", "f2_name": f"Bo Beta {i}",
                     "weight_class": "Lightweight", "scheduled_rounds": 3,
                     "bout_order": len(sections) - 1 - i,  # deliberately unsorted
                     "section": section, "p_f1_wins": 0.7,
                     "drivers": json.dumps([{"feature": "diff_elo", "value": 0.4}]),
                     **joint})
    pd.DataFrame(rows).to_parquet(
        root / "reports" / f"card_predictions_{slug}.parquet", index=False)
    findings.reset_cache()


def test_dashboard_picks_come_from_the_saved_card(client):
    """The homepage can show picks with the trading bot stopped."""
    _, root = client
    _write_card(root, "soon", "2999-01-01", sections=("Main card",))
    body = findings.dashboard_picks(today="2026-11-13")
    fight = body["fights"][0]
    assert body["event"] == "UFC Test Night" and body["date"] == "2999-01-01"
    assert fight["f1"] == "Ann Alpha 0" and fight["winner"] is None
    assert fight["pick"]["winner"] == "Ann Alpha 0"
    assert fight["pick"]["method"] in {"KO/TKO", "SUB", "DEC"}


def test_dashboard_picks_are_empty_when_nothing_is_saved(client):
    assert findings.dashboard_picks() == {"event": None, "date": None, "fights": []}


def test_site_picks_file_is_the_saved_card(client, tmp_path):
    _, root = client
    _write_card(root, "soon", "2999-01-01", sections=("Main card",))
    target = tmp_path / "picks.json"
    findings.write_site_picks(target)
    body = json.loads(target.read_text(encoding="utf-8"))
    assert body["fights"][0]["pick"]["winner"] == "Ann Alpha 0"


def test_next_card_prefers_the_soonest_card_still_to_come(client):
    api, root = client
    _write_card(root, "old", "2020-01-01")
    _write_card(root, "soon", "2999-01-01")
    _write_card(root, "later", "2999-06-01")

    body = api.get("/api/next-card").json()
    assert body["slug"] == "soon" and body["upcoming"] is True


def test_next_card_falls_back_to_the_most_recent_card(client):
    """Between events — most weeks — the last card is the interesting one."""
    api, root = client
    _write_card(root, "older", "2020-01-01")
    _write_card(root, "newer", "2021-01-01")

    body = api.get("/api/next-card").json()
    assert body["slug"] == "newer" and body["upcoming"] is False


def test_card_bouts_come_back_in_the_order_they_were_announced(client):
    """Main event first, as the card was published — not parquet row order."""
    api, root = client
    _write_card(root, "x", "2999-01-01", sections=("Main card", "Prelims"))
    bouts = api.get("/api/cards/x").json()["bouts"]
    assert [b["section"] for b in bouts] == ["Prelims", "Main card"]


def test_card_method_call_uses_marginal_method_then_conditional_round(client):
    """A concentrated KO round must not outrank a larger SUB method total."""
    api, root = client
    _write_card(root, "x", "2999-01-01", sections=("Main card",))
    path = root / "reports" / "card_predictions_x.parquet"
    frame = pd.read_parquet(path)
    from octagon.models import finish_round

    for column in finish_round.outcome_columns():
        frame[column] = 0.0
    frame.loc[0, ["f1_ko_r1", "f1_sub_r1", "f1_sub_r2", "f1_sub_r3",
                  "f1_dec", "f2_dec"]] = [0.20, 0.10, 0.15, 0.11, 0.14, 0.30]
    frame.to_parquet(path, index=False)
    findings.reset_cache()

    bout = api.get("/api/cards/x").json()["bouts"][0]
    assert bout["statement"] == "Ann Alpha 0 by submission in round 2"
    assert bout["top_outcome"] == {
        "label": "by submission in round 2",
        "probability": pytest.approx(0.15),
        "method": "SUB",
        "round": 2,
        "method_probability": pytest.approx(0.36),
        "round_probability": pytest.approx(0.15 / 0.36),
    }


def test_cards_predicted_before_v27_still_serve(client):
    """Older frozen files have no section, order or drivers column."""
    api, root = client
    _write_card(root, "x", "2999-01-01", sections=("Main card",))
    frame = pd.read_parquet(root / "reports" / "card_predictions_x.parquet")
    frame.drop(columns=["section", "bout_order", "drivers"]).to_parquet(
        root / "reports" / "card_predictions_x.parquet", index=False)
    findings.reset_cache()

    bout = api.get("/api/cards/x").json()["bouts"][0]
    assert bout["section"] is None and bout["drivers"] == []


def test_frozen_call_all_policy_serves_a_close_fight_as_a_pick(client):
    api, root = client
    _write_card(root, "x", "2999-01-01", sections=("Main card",))
    path = root / "reports" / "card_predictions_x.parquet"
    frame = pd.read_parquet(path)
    frame["p_f1_wins"] = 0.51
    frame["call_all"] = True
    frame["prediction_mode"] = "skill_only"
    frame.to_parquet(path, index=False)
    findings.reset_cache()
    bout = api.get("/api/cards/x").json()["bouts"][0]
    assert bout["called"] is True
    assert bout["statement"] is not None
    assert bout["confidence"] == 0.51
    assert bout["prediction_mode"] == "skill_only"


def test_fighters_without_media_still_render(client):
    api, root = client
    _write_card(root, "x", "2999-01-01", sections=("Main card",))
    media = api.get("/api/cards/x").json()["bouts"][0]["f1_media"]
    assert media["name"] == "Ann Alpha 0"
    assert media["portrait"] is None and media["country_code"] is None


def test_media_is_attached_to_the_matching_fighter(client):
    api, root = client
    _write_card(root, "x", "2999-01-01", sections=("Main card",))
    (root / "data").mkdir(exist_ok=True)
    (root / "data" / "fighter_media.json").write_text(json.dumps({
        # Stored under the normalized key, and found despite the accent.
        "alpha ann": {"portrait": "ann-alpha.png", "rank": "3",
                      "country_code": "RS", "record": "10-1-0"},
    }), encoding="utf-8")
    findings.reset_cache()

    media = api.get("/api/cards/x").json()["bouts"][0]["f1_media"]
    assert media["portrait"] == "/api/portraits/ann-alpha.png"
    assert media["rank"] == "3" and media["country_code"] == "RS"


def test_portrait_route_refuses_to_escape_the_image_directory(client):
    """The file name arrives from a URL; '..' must not reach the filesystem."""
    api, root = client
    images = root / "data" / "fighter_images"
    images.mkdir(parents=True)
    (images / "ann-alpha.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "secret.txt").write_text("nope", encoding="utf-8")
    findings.reset_cache()

    assert api.get("/api/portraits/ann-alpha.png").status_code == 200
    assert api.get("/api/portraits/..%2Fsecret.txt").status_code == 404
    assert api.get("/api/portraits/nothing.png").status_code == 404


def test_loaders_pick_up_a_rerun_without_a_restart(client):
    """`octagon predict` reruns while the server is up; the page must move."""
    api, root = client
    _write_card(root, "x", "2999-01-01", sections=("Main card",))
    findings.reset_cache()
    before = api.get("/api/cards/x").json()["bouts"][0]["p_f1_wins"]

    path = root / "reports" / "card_predictions_x.parquet"
    frame = pd.read_parquet(path)
    frame["p_f1_wins"] = 0.31
    frame.to_parquet(path, index=False)
    # No reset_cache(): the mtime moving is what has to be enough.

    assert before == pytest.approx(0.7)
    assert api.get("/api/cards/x").json()["bouts"][0]["p_f1_wins"] == pytest.approx(0.31)
