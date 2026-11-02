"""Feature builder: truncation is the leakage guard."""

from datetime import date

import pytest

from octagon.db.parsing import normalize_name
from octagon.features.build import Bout, build_feature_rows, swap_corners


def make_stats(sig_landed=30, sig_attempted=60, td_landed=2, td_attempted=4,
               knockdowns=0, sub_attempts=1, ctrl_seconds=120,
               head=20, body=6, leg=4, distance=24, clinch=4, ground=2):
    return {
        "knockdowns": knockdowns, "sig_landed": sig_landed,
        "sig_attempted": sig_attempted, "total_landed": sig_landed + 10,
        "total_attempted": sig_attempted + 10, "td_landed": td_landed,
        "td_attempted": td_attempted, "sub_attempts": sub_attempts,
        "reversals": 0, "ctrl_seconds": ctrl_seconds,
        "head_landed": head, "body_landed": body, "leg_landed": leg,
        "distance_landed": distance, "clinch_landed": clinch, "ground_landed": ground,
    }


def make_bout(fight_id, day, fighter1, fighter2, winner="fighter1",
              method="U-DEC", end_round=3, duration_s=900,
              stats1=None, stats2=None):
    return Bout(
        fight_id=fight_id, date=day, fighter1=fighter1, fighter2=fighter2,
        winner=winner, method=method, end_round=end_round, duration_s=duration_s,
        weight_class="Lightweight", title_fight=0, scheduled_rounds=3,
        stats1=stats1 or make_stats(), stats2=stats2 or make_stats(sig_landed=15, sig_attempted=45),
        odds1=None, odds2=None,
    )


def canonical(rows, fight_id):
    """Fetch a row un-swapped, so tests can reason in source orientation."""
    row = next(r for r in rows if r["fight_id"] == fight_id)
    return swap_corners(row) if row["swapped"] else row


BOUTS = [
    make_bout(1, "2020-01-01", "Alice", "Bob"),
    make_bout(2, "2020-06-01", "Alice", "Carol", method="KO/TKO", end_round=1, duration_s=60,
              stats1=make_stats(sig_landed=10, sig_attempted=20),
              stats2=make_stats(sig_landed=5, sig_attempted=10)),
    make_bout(3, "2021-01-01", "Alice", "Dana"),
]


def test_debut_fighter_has_no_history():
    rows = build_feature_rows(BOUTS, {})
    first = canonical(rows, 1)
    # Nothing may be known about a debuting fighter's past — that's the rule.
    assert first["f1_n_fights"] == 0.0
    assert first["f1_win_pct"] is None
    assert first["f1_layoff_days"] is None
    assert first["f1_slpm_l3"] is None
    assert first["f1_elo"] == 1500.0
    assert first["diff_elo"] == 0.0


def test_history_arithmetic_by_hand():
    rows = build_feature_rows(BOUTS, {})
    third = canonical(rows, 3)
    # Alice enters fight 3 with two wins (fights 1 and 2).
    assert third["f1_n_fights"] == 2.0
    assert third["f1_wins"] == 2.0
    assert third["f1_win_pct"] == 1.0
    assert third["f1_streak"] == 2.0
    assert third["f1_ko_win_rate"] == pytest.approx(0.5)
    assert third["f1_ko_share"] == pytest.approx(0.5)
    assert third["f1_layoff_days"] == (date(2021, 1, 1) - date(2020, 6, 1)).days
    # Rolling striking: (30 + 10) landed over (900 + 60) seconds -> 2.5/min,
    # accuracy (30+10)/(60+20) = 0.5, absorbed (15+5)/16min = 1.25/min.
    assert third["f1_slpm_l3"] == pytest.approx(2.5)
    assert third["f1_sig_acc_l3"] == pytest.approx(0.5)
    assert third["f1_sapm_l3"] == pytest.approx(1.25)
    # Two wins moved Alice's Elo up; debutant Dana sits at 1500.
    assert third["f1_elo"] > 1500.0
    assert third["f2_elo"] == 1500.0
    assert third["diff_elo"] == pytest.approx(third["f1_elo"] - 1500.0)
    # Strength of schedule: Alice fought Bob (1500 pre) and Carol (1500 pre).
    assert third["f1_opp_elo_l5"] == pytest.approx(1500.0)
    assert third["f2_opp_elo_l5"] is None  # Dana has fought nobody


def test_ko_share_is_how_they_finish_when_they_win_not_how_often_they_win():
    """ko_win_rate mixes 'do they win' with 'how'; the method model needs the
    second one on its own, plus how often their fights end by KO at all."""
    bouts = BOUTS + [
        make_bout(4, "2021-06-01", "Alice", "Eve", winner="fighter2",
                  method="KO/TKO", end_round=1, duration_s=90),
        make_bout(5, "2022-01-01", "Alice", "Frank"),
    ]
    row = canonical(build_feature_rows(bouts, {}), 5)
    # Three wins (DEC, KO, DEC) and one KO loss: P(win by KO)=1/4,
    # P(KO | win)=1/3, P(fight ends KO)=2/4.
    assert row["f1_wins"] == 3.0
    assert row["f1_losses"] == 1.0
    assert row["f1_ko_win_rate"] == pytest.approx(1 / 4)
    assert row["f1_ko_share"] == pytest.approx(1 / 3)
    assert row["f1_ko_end_rate_l5"] == pytest.approx(0.5)
    assert row["bout_elo_gap"] == pytest.approx(abs(row["f1_elo"] - row["f2_elo"]))


def test_point_in_time_by_truncation():
    """THE leakage test: deleting future fights must not change past features."""
    full = build_feature_rows(BOUTS, {})
    truncated = build_feature_rows(BOUTS[:2], {})
    assert canonical(full, 2) == canonical(truncated, 2)


def test_point_in_time_truncation_includes_regional():
    """Regional rows after the bout date must not leak into earlier snapshots."""
    regional = {
        normalize_name("Alice"): [
            {"date": "2019-01-01", "result": "win", "method": "KO/TKO",
             "org": "Bellator", "is_amateur": 0},
            {"date": "2020-12-01", "result": "win", "method": "DEC",
             "org": "Bellator", "is_amateur": 0},
        ]
    }
    full = build_feature_rows(BOUTS, {}, regional_by_name=regional)
    truncated = build_feature_rows(BOUTS[:2], {}, regional_by_name=regional)
    assert canonical(full, 2) == canonical(truncated, 2)
    first = canonical(full, 1)
    second = canonical(full, 2)
    third = canonical(full, 3)
    assert first["f1_pre_ufc_wins"] == 1
    assert second["f1_pre_ufc_wins"] == 1
    assert third["f1_pre_ufc_wins"] == 2


def test_swap_corners_is_an_involution_and_antisymmetric():
    rows = build_feature_rows(BOUTS, {})
    row = canonical(rows, 3)
    flipped = swap_corners(row)
    assert flipped["label"] == 1 - row["label"]
    assert flipped["f1_wins"] == row["f2_wins"]
    assert flipped["f2_slpm_l3"] == row["f1_slpm_l3"]
    assert flipped["diff_elo"] == -row["diff_elo"]
    assert swap_corners(flipped) == row  # double swap restores everything


def test_swapping_is_deterministic_per_seed_and_balanced_enough():
    many = [make_bout(i, f"2020-01-{i:02d}", f"A{i}", f"B{i}") for i in range(1, 29)]
    once = build_feature_rows(many, {}, seed=7)
    again = build_feature_rows(many, {}, seed=7)
    assert once == again  # reproducible datasets or nothing
    swapped = sum(r["swapped"] for r in once)
    assert 0 < swapped < len(once)  # the coin actually flips both ways


def test_draw_updates_history_but_emits_no_row():
    bouts = [
        make_bout(1, "2020-01-01", "Alice", "Bob", winner="draw"),
        make_bout(2, "2020-06-01", "Alice", "Carol"),
    ]
    rows = build_feature_rows(bouts, {})
    assert [r["fight_id"] for r in rows] == [2]  # no label -> no modeling row
    second = canonical(rows, 2)
    assert second["f1_n_fights"] == 1.0    # the draw still counts as cage time
    assert second["f1_wins"] == 0.0
    assert second["f1_win_pct"] is None    # no decisive fights yet
    assert second["f1_elo"] == 1500.0      # equal-rating draw moves nothing


def test_no_contest_freezes_elo_and_record():
    bouts = [
        make_bout(1, "2020-01-01", "Alice", "Bob", winner="nc"),
        make_bout(2, "2020-06-01", "Alice", "Bob"),
    ]
    rows = build_feature_rows(bouts, {})
    second = canonical(rows, 2)
    assert second["f1_elo"] == 1500.0
    assert second["f1_wins"] == 0.0
    assert second["f1_n_fights"] == 1.0


def test_domain_elos_move_with_stats_not_results():
    """The point of domain ratings: a LOSER who dominated the striking
    still gains striking Elo, because the stats say so."""
    bouts = [
        # Alice loses the decision but out-lands Bob 90 to 30.
        make_bout(1, "2020-01-01", "Alice", "Bob", winner="fighter2",
                  stats1=make_stats(sig_landed=90, td_landed=0, ctrl_seconds=0),
                  stats2=make_stats(sig_landed=30, td_landed=4, ctrl_seconds=400)),
        make_bout(2, "2020-06-01", "Alice", "Bob"),
    ]
    rows = build_feature_rows(bouts, {})
    second = canonical(rows, 2)
    assert second["f1_elo"] < 1500.0          # result Elo: Alice lost
    assert second["f1_strike_elo"] > 1500.0   # striking Elo: Alice dominated
    assert second["f1_grapple_elo"] < 1500.0  # grappling Elo: Bob dominated
    assert second["diff_strike_elo"] == pytest.approx(
        second["f1_strike_elo"] - second["f2_strike_elo"])


def test_short_fight_moves_domain_elo_less_and_keeps_the_sign():
    edge = dict(
        stats1=make_stats(sig_landed=40, td_landed=3, ctrl_seconds=180),
        stats2=make_stats(sig_landed=10, td_landed=0, ctrl_seconds=0),
    )
    flash = [
        make_bout(1, "2020-01-01", "Alice", "Bob", duration_s=20, **edge),
        make_bout(2, "2020-06-01", "Alice", "Carol"),
    ]
    sustained = [
        make_bout(1, "2020-01-01", "Alice", "Bob", duration_s=900, **edge),
        make_bout(2, "2020-06-01", "Alice", "Carol"),
    ]
    flash_elo = canonical(build_feature_rows(flash, {}, elo_k=80), 2)["f1_strike_elo"]
    sustained_elo = canonical(build_feature_rows(sustained, {}, elo_k=80), 2)["f1_strike_elo"]
    assert sustained_elo > flash_elo > 1500.0

    # A short win must not pull a favorite back toward 1500.
    established = []
    for i in range(8):
        established.append(make_bout(
            i, f"2019-{(i % 12) + 1:02d}-01", "Alice", f"Foe{i}", duration_s=900, **edge))
    established.append(make_bout(20, "2020-01-01", "Alice", "Bob", duration_s=20, **edge))
    established.append(make_bout(21, "2020-06-01", "Alice", "Carol"))
    rated = build_feature_rows(established, {}, elo_k=80)
    before = canonical(rated, 20)["f1_strike_elo"]
    after = canonical(rated, 21)["f1_strike_elo"]
    assert before > 1550.0
    assert after > before


def test_domain_elos_skip_fights_without_stats():
    no_stats = make_bout(1, "2020-01-01", "Alice", "Bob")
    no_stats.stats1 = no_stats.stats2 = None
    rows = build_feature_rows([no_stats, make_bout(2, "2020-06-01", "Alice", "Carol")], {})
    second = canonical(rows, 2)
    assert second["f1_strike_elo"] == 1500.0  # nothing measurable happened
    assert second["f1_elo"] > 1500.0          # but the win still counts


def test_style_shares_by_hand():
    """Where strikes land (head/body/leg) and from where (distance/clinch/
    ground), over the last-5 window — checked against hand arithmetic."""
    bouts = [
        make_bout(1, "2020-01-01", "Alice", "Bob",
                  stats1=make_stats(head=10, body=5, leg=5, distance=15, clinch=3, ground=2),
                  stats2=make_stats(ground=8, distance=2, clinch=0)),
        make_bout(2, "2020-06-01", "Alice", "Carol"),
    ]
    rows = build_feature_rows(bouts, {})
    second = canonical(rows, 2)
    assert second["f1_leg_share_l5"] == pytest.approx(5 / 20)
    assert second["f1_head_share_l5"] == pytest.approx(10 / 20)
    assert second["f1_ground_share_l5"] == pytest.approx(2 / 20)
    # What Alice absorbed: Bob landed 8 of his 10 positioned strikes on the ground.
    assert second["f1_ground_absorbed_share_l5"] == pytest.approx(8 / 10)
    # Style features exist only for the l5 window — l3 stays lean.
    assert "f1_leg_share_l3" not in second


def test_upcoming_bout_gets_features_but_changes_nothing():
    """A future card must see history as of its date, and must not exist as
    far as histories/Elo are concerned — it hasn't happened."""
    upcoming = make_bout(99, "2022-01-01", "Alice", "Newcomer", winner="upcoming")
    upcoming.stats1 = upcoming.stats2 = None
    rows = build_feature_rows(BOUTS + [upcoming], {})

    future = next(r for r in rows if r["fight_id"] == 99)
    assert future["label"] is None
    assert future["swapped"] == 0            # predictions keep the given order
    assert future["f1_wins"] == 3.0          # Alice won bouts 1-3
    assert future["f1_elo"] > 1500.0
    assert future["f2_n_fights"] == 0.0

    # And the rows for past fights are byte-identical with or without it.
    without = build_feature_rows(BOUTS, {})
    assert [r for r in rows if r["fight_id"] != 99] == without


def test_tale_of_the_tape_and_age():
    tott = {"Alice": {"height_cm": 170.0, "reach_cm": 175.0, "stance": "Southpaw",
                      "dob": "1994-01-01"}}
    rows = build_feature_rows(BOUTS, tott)
    first = canonical(rows, 1)
    assert first["f1_height_cm"] == 170.0
    assert first["f1_southpaw"] == 1.0
    assert first["f1_age"] == pytest.approx(26.0, abs=0.02)  # 1994 -> 2020
    assert first["f2_age"] is None                            # unknown fighter
    assert first["diff_age"] is None                          # no guessing
