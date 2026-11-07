"""Fight-research features: form, rematches, common opponents, style records.

These are the signals a matchup analyst actually uses — who beat whom, how
recent fights went, and whether this style pairing has historically worked
for either man. They must stay point-in-time: a rematch feature on fight 2
may only see fight 1.
"""

from datetime import date

import numpy as np
import pytest

from octagon.features.build import build_feature_rows, swap_corners
from octagon.features.research import (
    form_snapshot,
    pairing_research,
    research_brief,
)
from octagon.features.style import style_matchup, style_scores
from octagon.models.market import apply_market_layer, history_confidence
from tests.test_features import canonical, make_bout


def test_rematch_sees_only_the_previous_meeting():
    bouts = [
        make_bout(1, "2020-01-01", "Alice", "Bob", winner="fighter1",
                  method="KO/TKO", end_round=1, duration_s=90),
        make_bout(2, "2021-01-01", "Alice", "Bob"),
        make_bout(3, "2022-01-01", "Alice", "Bob"),
    ]
    rows = build_feature_rows(bouts, {})
    first = canonical(rows, 1)
    second = canonical(rows, 2)
    third = canonical(rows, 3)

    assert first["bout_h2h_meetings"] is None
    assert first["diff_h2h_edge"] is None

    assert second["bout_h2h_meetings"] == 1.0
    assert second["diff_h2h_edge"] == pytest.approx(1.0)   # Alice won the first
    assert second["diff_h2h_last"] == pytest.approx(1.0)
    assert second["bout_h2h_days"] == pytest.approx(
        (date(2021, 1, 1) - date(2020, 1, 1)).days)

    assert third["bout_h2h_meetings"] == 2.0
    assert third["diff_h2h_edge"] == pytest.approx(2.0)    # Alice 2-0 entering #3


def test_common_opponents_compare_records_against_the_shared_name():
    bouts = [
        make_bout(1, "2020-01-01", "Alice", "Dana", winner="fighter1"),
        make_bout(2, "2020-06-01", "Bob", "Dana", winner="fighter2"),
        make_bout(3, "2021-01-01", "Alice", "Bob"),
    ]
    rows = build_feature_rows(bouts, {})
    fight = canonical(rows, 3)
    assert fight["bout_common_n"] == 1.0
    # Alice beat Dana, Bob lost to Dana -> Alice's shared-opp record is better.
    assert fight["diff_common_record"] == pytest.approx(1.0)


def test_form_weights_recent_results_by_opponent_elo():
    """A win over a 1700 opponent is not the same as a win over a debutant."""
    from octagon.features.build import PastFight

    fights = [
        PastFight(date=date(2020, 1, 1), result="win", method="U-DEC",
                  end_round=3, duration_s=900, stats=None, opp_stats=None,
                  opp_elo_pre=1500.0, opponent="Can",
                  opp_style={"striker": 0.8, "wrestler": 0.1,
                             "grappler": 0.1, "pressure": 0.2}),
        PastFight(date=date(2020, 6, 1), result="loss", method="KO/TKO",
                  end_round=1, duration_s=60, stats=None, opp_stats=None,
                  opp_elo_pre=1700.0, opponent="Killer",
                  opp_style={"striker": 0.2, "wrestler": 0.8,
                             "grappler": 0.3, "pressure": 0.4}),
    ]
    snap = form_snapshot(fights, date(2021, 1, 1), elo_rating=1550.0)
    assert snap["last_result"] == pytest.approx(-1.0)
    assert snap["last_was_finish"] == 1.0
    assert snap["days_since_ko"] == pytest.approx(
        (date(2021, 1, 1) - date(2020, 6, 1)).days)
    expected_vs_elite = 1 / (1 + 10 ** (200 / 400))
    assert snap["form_l5"] == pytest.approx((1.0 - 2 * expected_vs_elite) / 2)
    assert snap["vs_striker_win_pct"] is None   # only one fight vs a striker
    assert snap["vs_wrestler_win_pct"] is None  # only one fight vs a wrestler


def test_quality_win_rate_is_against_elites_only():
    from octagon.features.build import PastFight

    def fight(opponent_elo, result="win"):
        return PastFight(date=date(2020, 1, 1), result=result, method="U-DEC",
                         end_round=3, duration_s=900, stats=None, opp_stats=None,
                         opp_elo_pre=opponent_elo, opponent="Opp")

    # Two elite wins and five wins over ordinary opponents. The rate is 1, not 2/7.
    mixed = form_snapshot([fight(1700), fight(1650)] + [fight(1400) for _ in range(5)],
                          date(2021, 1, 1), 1500)
    assert mixed["quality_n"] == 2
    assert mixed["quality_win_rate"] == pytest.approx(1.0)
    # One elite fight is a count, not a rate. Zero elite fights stay a zero count.
    lone = form_snapshot([fight(1700)] + [fight(1400) for _ in range(5)],
                         date(2021, 1, 1), 1500)
    assert lone["quality_n"] == 1 and lone["quality_win_rate"] is None
    untested = form_snapshot([fight(1400) for _ in range(4)], date(2021, 1, 1), 1500)
    assert untested["quality_n"] == 0 and untested["quality_win_rate"] is None
    split = form_snapshot([fight(1700, "win"), fight(1700, "loss")], date(2021, 1, 1), 1500)
    assert split["quality_win_rate"] == pytest.approx(0.5)


def test_loss_to_stronger_opponent_hurts_form_less():
    from dataclasses import replace
    from octagon.features.build import PastFight

    loss = PastFight(date(2020, 1, 1), "loss", "U-DEC", 3, 900, None, None)
    weak = form_snapshot([replace(loss, opp_elo_pre=1300)], date(2021, 1, 1), 1500)
    strong = form_snapshot([replace(loss, opp_elo_pre=1700)], date(2021, 1, 1), 1500)
    assert weak["form_l3"] < strong["form_l3"] < 0
    # Today's rating must not rewrite expectations for an old fight.
    assert strong["form_l3"] == form_snapshot(
        [replace(loss, opp_elo_pre=1700)], date(2021, 1, 1), 1900)["form_l3"]


def test_zero_defense_is_observed_and_not_imputed():
    wrestler = {"td15_l5": 3.0, "ground_share_l5": 0.7, "sub15_l5": 1.0}
    zero = {"td_def_l5": 0.0, "ground_absorbed_share_l5": 0.0}
    missing = {}
    z = style_matchup(wrestler, zero)
    m = style_matchup(wrestler, missing)
    assert z["style_wrestle_strike"] > m["style_wrestle_strike"]
    assert z["style_grapple_strike"] == 0.0
    assert m["style_grapple_strike"] > 0.0


def test_saturated_style_scores_do_not_label_a_wrestler_as_only_a_striker():
    row = {"f1_style_striker": 1., "f1_style_wrestler": 1.,
           "f2_style_striker": 1., "f2_style_wrestler": 0.,
           "f1_td15_l5": 10., "f2_td_def_l5": 0.7}
    notes = research_brief(row, "Wrestler", "Striker")
    assert not any("both profile as strikers" in note for note in notes)
    assert any("Wrestler lands 10.0 takedowns/15" in note for note in notes)


def test_style_record_uses_the_opponents_archetype_not_a_generic_win_rate():
    from octagon.features.build import PastFight

    striker_opps = [
        PastFight(date=date(2020, 1, 1), result="win", method="U-DEC",
                  end_round=3, duration_s=900, stats=None, opp_stats=None,
                  opponent=f"S{i}", opp_elo_pre=1500.0,
                  opp_style={"striker": 0.9, "wrestler": 0.1,
                             "grappler": 0.1, "pressure": 0.2})
        for i in range(3)
    ]
    wrestler_opps = [
        PastFight(date=date(2020, 6, 1), result="loss", method="U-DEC",
                  end_round=3, duration_s=900, stats=None, opp_stats=None,
                  opponent=f"W{i}", opp_elo_pre=1500.0,
                  opp_style={"striker": 0.1, "wrestler": 0.9,
                             "grappler": 0.2, "pressure": 0.3})
        for i in range(3)
    ]
    snap = form_snapshot(striker_opps + wrestler_opps, date(2021, 1, 1), 1500.0)
    assert snap["vs_striker_win_pct"] == pytest.approx(1.0)
    assert snap["vs_wrestler_win_pct"] == pytest.approx(0.0)


def test_style_clash_is_antisymmetric_and_rewards_wrestling_into_bad_tdd():
    striker = {
        "slpm_l5": 6.0, "head_share_l5": 0.7, "kd15_l5": 0.5,
        "td15_l5": 0.2, "td_acc_l5": 0.2, "ctrl_pct_l5": 0.1,
        "ground_share_l5": 0.1, "sub15_l5": 0.0, "sub_win_rate": 0.0,
        "clinch_share_l5": 0.1, "td_def_l5": 0.8,
        "ground_absorbed_share_l5": 0.2,
        "reach_cm": 180.0, "age": 28.0, "southpaw": 0.0,
        "avg_fight_min": 12.0, "finish_involvement": 0.2,
        "vs_wrestler_win_pct": 0.3, "vs_striker_win_pct": 0.7,
        "ko_win_rate": 0.4, "times_koed": 0.0, "n_fights": 10.0,
    }
    wrestler = {
        "slpm_l5": 2.0, "head_share_l5": 0.4, "kd15_l5": 0.05,
        "td15_l5": 4.0, "td_acc_l5": 0.6, "ctrl_pct_l5": 0.5,
        "ground_share_l5": 0.5, "sub15_l5": 0.3, "sub_win_rate": 0.2,
        "clinch_share_l5": 0.3, "td_def_l5": 0.4,
        "ground_absorbed_share_l5": 0.4,
        "reach_cm": 170.0, "age": 34.0, "southpaw": 1.0,
        "avg_fight_min": 8.0, "finish_involvement": 0.6,
        "vs_wrestler_win_pct": 0.6, "vs_striker_win_pct": 0.4,
        "ko_win_rate": 0.1, "times_koed": 2.0, "n_fights": 12.0,
    }
    assert style_scores(striker)["striker"] > style_scores(wrestler)["striker"]
    fwd = style_matchup(striker, wrestler)
    rev = style_matchup(wrestler, striker)
    for key, value in fwd.items():
        if value is None:
            assert rev[key] is None
        else:
            assert abs(value + rev[key]) < 1e-9, key
    # Reach helps the striker more than the wrestler.
    assert fwd["style_reach_striker"] > 0
    # Wrestling into a striker who has been KO'd / goes the distance.
    assert "style_record" in fwd
    assert "style_cardio_fade" in fwd


def test_pairing_research_negates_under_a_name_swap():
    from octagon.features.build import FighterHistory, PastFight

    h1 = FighterHistory(fights=[
        PastFight(date=date(2020, 1, 1), result="win", method="U-DEC",
                  end_round=3, duration_s=900, stats=None, opp_stats=None,
                  opponent="Bob", opp_elo_pre=1500.0),
        PastFight(date=date(2020, 3, 1), result="win", method="U-DEC",
                  end_round=3, duration_s=900, stats=None, opp_stats=None,
                  opponent="Dana", opp_elo_pre=1500.0),
    ])
    h2 = FighterHistory(fights=[
        PastFight(date=date(2020, 1, 1), result="loss", method="U-DEC",
                  end_round=3, duration_s=900, stats=None, opp_stats=None,
                  opponent="Alice", opp_elo_pre=1500.0),
        PastFight(date=date(2020, 4, 1), result="loss", method="U-DEC",
                  end_round=3, duration_s=900, stats=None, opp_stats=None,
                  opponent="Dana", opp_elo_pre=1500.0),
    ])
    anti, sym = pairing_research(h1, h2, "Alice", "Bob", date(2021, 1, 1))
    flipped, flipped_sym = pairing_research(
        h2, h1, "Bob", "Alice", date(2021, 1, 1))
    for key in anti:
        if anti[key] is None:
            assert flipped[key] is None
        else:
            assert flipped[key] == pytest.approx(-anti[key])
    assert flipped_sym == sym


def test_research_features_survive_truncation():
    """Deleting a later rematch must not change the first meeting's features."""
    bouts = [
        make_bout(1, "2020-01-01", "Alice", "Bob"),
        make_bout(2, "2021-01-01", "Alice", "Bob"),
        make_bout(3, "2022-01-01", "Alice", "Carol"),
    ]
    full = build_feature_rows(bouts, {})
    truncated = build_feature_rows(bouts[:1], {})
    assert canonical(full, 1) == canonical(truncated, 1)


def test_corner_swap_negates_research_diffs():
    bouts = [
        make_bout(1, "2020-01-01", "Alice", "Dana"),
        make_bout(2, "2020-06-01", "Bob", "Dana", winner="fighter2"),
        make_bout(3, "2021-01-01", "Alice", "Bob"),
    ]
    row = canonical(build_feature_rows(bouts, {}), 3)
    flipped = swap_corners(row)
    assert flipped["diff_h2h_edge"] == (
        None if row["diff_h2h_edge"] is None else pytest.approx(-row["diff_h2h_edge"]))
    assert flipped["diff_common_record"] == pytest.approx(-row["diff_common_record"])
    assert flipped["bout_common_n"] == row["bout_common_n"]
    assert swap_corners(flipped) == row


def test_history_confidence_is_symmetric_and_saturates():
    assert history_confidence(0, 20) == 0.0
    assert history_confidence(8, 8) == 1.0
    assert history_confidence(4, 10) == pytest.approx(0.5)
    assert history_confidence(12, 9) == history_confidence(9, 12)
    # Dual debut with no regional career stays at zero (legacy contract).
    assert history_confidence(0, 0, career1=0, career2=8) == 0.0


def test_history_confidence_uses_regional_careers_on_dual_debuts():
    """DWCS-shaped fights: 0 UFC bouts, but both men have pro records."""
    thin = history_confidence(0, 0, career1=3, career2=8)
    thick = history_confidence(0, 0, career1=10, career2=12)
    assert 0.0 < thin < thick
    assert thick <= 0.45
    assert history_confidence(0, 0, career1=10, career2=12) == (
        history_confidence(0, 0, career1=12, career2=10))
    # A veteran UFC fight still uses UFC depth, not the regional fallback.
    assert history_confidence(8, 8, career1=2, career2=2) == 1.0


def test_research_blend_moves_veterans_off_the_market_toward_skill():
    """Debuts stay on the fitted stack; deep histories mix skill in."""
    skill = np.array([0.70, 0.70])
    market = np.array([0.55, 0.55])
    shipped, trapped = apply_market_layer(
        skill, market, [0.0, 12.0], [8.0, 10.0],
        stack=(1.0, 0.0), research_weight=0.55)
    assert not trapped.any()
    # Debut (min fights = 0): research weight is zero, stack with b=0 is market.
    assert shipped[0] == pytest.approx(0.55)
    # Veterans: pulled off the market toward skill.
    assert shipped[1] > 0.55
    assert shipped[1] < 0.70


def test_research_brief_mentions_style_form_and_h2h():
    row = {
        "f1_style_striker": 0.8, "f2_style_striker": 0.2,
        "f1_style_wrestler": 0.2, "f2_style_wrestler": 0.7,
        "f1_form_l5": 0.4, "f2_form_l5": -0.3,
        "f1_last_result": 1.0, "f2_last_result": -1.0,
        "f1_slpm_l5": 5.5, "f2_slpm_l5": 2.1,
        "f1_td15_l5": 0.4, "f2_td15_l5": 3.8,
        "f1_td_def_l5": 0.85, "f2_td_def_l5": 0.45,
        "bout_h2h_meetings": 1.0, "diff_h2h_last": 1.0, "bout_h2h_days": 400.0,
        "bout_common_n": 2.0, "diff_common_record": 0.5,
        "f1_vs_wrestler_win_pct": 0.3, "f2_vs_striker_win_pct": 0.6,
    }
    lines = research_brief(row, "Alice", "Bob")
    blob = " ".join(lines).lower()
    assert "striker" in blob and "wrestler" in blob
    assert "alice" in blob and "bob" in blob
    assert any("rematch" in line.lower() or "previously" in line.lower()
               for line in lines)
    assert any("common" in line.lower() for line in lines)
