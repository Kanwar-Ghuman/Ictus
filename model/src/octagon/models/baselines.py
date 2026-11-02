"""Reference predictors used in evaluation reports."""

import numpy as np
import pandas as pd

from octagon.betting.odds import implied_probability, remove_vig
from octagon.features.elo import expected_score


def coin_flip(df: pd.DataFrame) -> np.ndarray:
    return np.full(len(df), 0.5)


def better_record(df: pd.DataFrame) -> np.ndarray:
    """Better win percentage, then more wins. Ties stay at 0.5."""
    diff = df["diff_win_pct"].to_numpy(dtype=float)
    tiebreak = df["diff_wins"].to_numpy(dtype=float)
    decided = np.where(np.isnan(diff) | (diff == 0), tiebreak, diff)
    return np.where(np.isnan(decided) | (decided == 0), 0.5,
                    (decided > 0).astype(float))


def higher_elo(df: pd.DataFrame) -> np.ndarray:
    """Elo's own win probability from the pre-fight rating difference."""
    p = np.array([
        expected_score(f1, f2)
        for f1, f2 in zip(df["f1_elo"].to_numpy(), df["f2_elo"].to_numpy())
    ])
    return p


def market(df: pd.DataFrame) -> np.ndarray:
    """Vig-free implied probability from closing odds — the bar to clear.

    NaN where a fight has no odds; callers must mask accordingly.
    """
    out = np.full(len(df), np.nan)
    priced = df["f1_odds"].notna() & df["f2_odds"].notna()
    for i in np.flatnonzero(priced.to_numpy()):
        p1 = implied_probability(df["f1_odds"].iat[i])
        p2 = implied_probability(df["f2_odds"].iat[i])
        out[i], _ = remove_vig(p1, p2)
    return out


BASELINES = {
    "coin flip": coin_flip,
    "better record": better_record,
    "higher Elo": higher_elo,
    "market (vig-free favorite)": market,
}
