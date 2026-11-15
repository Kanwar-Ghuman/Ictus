"""The fight-night readiness checklist: what it calls ready, stale, or broken."""

import os
import sqlite3
import time
from datetime import date

from octagon.trading import check


def database(path, latest):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE fights (date TEXT)")
        conn.execute("INSERT INTO fights VALUES (?)", (latest,))
    return path


def test_fight_data_is_flagged_once_an_event_is_missing(tmp_path):
    today = date(2026, 11, 11)
    assert check.fight_data(tmp_path / "none.db", today).level == check.FAIL
    assert check.fight_data(database(tmp_path / "fresh.db", "2026-11-07"), today).level == check.OK
    stale = check.fight_data(database(tmp_path / "stale.db", "2026-09-12"), today)
    assert stale.level == check.WARN and "60 days ago" in stale.text and "refresh-data" in stale.fix


def test_a_model_that_no_longer_matches_the_data_blocks_predictions(tmp_path, monkeypatch):
    features = tmp_path / "features.parquet"
    model = tmp_path / "gbm.joblib"
    assert check.model_files(tmp_path, features)[0].level == check.FAIL  # no model at all
    model.write_text("m")
    assert check.model_files(tmp_path, features)[0].level == check.FAIL  # no feature table
    features.write_text("f")
    monkeypatch.setattr(check, "_model_matches", lambda model, features: False)
    stale, inplay = check.model_files(tmp_path, features)
    assert stale.level == check.FAIL and "--reuse-params" in stale.fix
    assert inplay.level == check.WARN  # no in-fight model: pre-fight only
    monkeypatch.setattr(check, "_model_matches", lambda model, features: True)
    (tmp_path / "inplay.json").write_text("{}")
    assert [line.level for line in check.model_files(tmp_path, features)] == [check.OK, check.OK]


def test_predictions_have_to_be_recent_and_from_the_current_model(tmp_path):
    today = date(2026, 11, 13)
    cards = [{"slug": "tonight", "date": "2026-11-14"}, {"slug": "old", "date": "2026-11-07"}]
    model = tmp_path / "gbm.joblib"
    assert check.upcoming_card([], tmp_path, model, today).level == check.OK       # built on start
    assert check.upcoming_card(cards, tmp_path, model, today).level == check.OK    # card, no predictions
    frozen = tmp_path / "card_predictions_tonight.parquet"
    frozen.write_text("p")
    week_ago = time.mktime(date(2026, 11, 9).timetuple())
    os.utime(frozen, (week_ago, week_ago))
    early = check.upcoming_card(cards, tmp_path, model, today)
    assert early.level == check.WARN and "5 days before" in early.text
    model.write_text("m")  # a model trained after those predictions
    assert "older than the model" in check.upcoming_card(cards, tmp_path, model, today).text
    yesterday = time.mktime(date(2026, 11, 13).timetuple())
    os.utime(model, (week_ago, week_ago))
    os.utime(frozen, (yesterday, yesterday))
    assert check.upcoming_card(cards, tmp_path, model, today).level == check.OK
