"""Market as base, skill as residual:

    p = sigmoid(a * logit(p_market) + b * logit(p_skill))

Odds as one GBM feature among many dilutes them (most rows are unpriced)
and scored worse than the market alone. No intercept, so corner swap is
exact. Do not report this as beating the odds — when lines exist they vote.
"""

import math

import numpy as np
from scipy.special import expit, logit
from sklearn.linear_model import LogisticRegression

_EPS = 1e-6
# UFC fights on the thinner side of the cage at which research_weight is
# applied in full. Linear from 0 (a debut) to 1 (this many).
_HISTORY_FULL = 8.0
# Dual-debut fallback: regional career depth, capped well below a veteran
# UFC fight so a Contender Series record cannot outvote eight octagon bouts.
_CAREER_FULL = 8.0
_CAREER_CAP = 0.45
# Tapology-style rank numbers (lower is better). Frozen product constant —
# not tuned on valid/test. The cap keeps a #1 vs #500 gap from overwriting
# the skill model (~20pp from a coin flip).
_RANKING_WEIGHT = 0.25
_RANKING_LOGODDS_CAP = 0.80


def history_confidence(n1: float, n2: float,
                       career1: float = 0.0, career2: float = 0.0) -> float:
    """0-1: how much history we have to actually research this fight.

    Symmetric in the two corners — uses the greener man, because a veteran
    vs. a debutant is still a debut fight. UFC depth saturates at
    `_HISTORY_FULL`. When *both* men are UFC debuts, a capped fraction of
    their regional careers is used instead — otherwise DWCS-shaped cards
    would keep the skill model silent.
    """
    ufc = min(float(n1 or 0.0), float(n2 or 0.0))
    if ufc > 0:
        return float(min(1.0, ufc / _HISTORY_FULL))
    career = min(float(career1 or 0.0), float(career2 or 0.0))
    if career <= 0:
        return 0.0
    return float(min(_CAREER_CAP, (career / _CAREER_FULL) * _CAREER_CAP))


def ranking_logodds(rank1: float | None, rank2: float | None) -> float:
    """Log-odds for fighter1 from Tapology-style ranks (lower number = better)."""
    try:
        r1, r2 = float(rank1), float(rank2)
    except (TypeError, ValueError):
        return 0.0
    if r1 <= 0 or r2 <= 0 or not math.isfinite(r1) or not math.isfinite(r2):
        return 0.0
    return math.log(r2 / r1)


def apply_ranking_nudge(
    p_skill: float,
    rank1: float | None,
    rank2: float | None,
    n1: float,
    n2: float,
) -> tuple[float, str | None]:
    """Move a dual-debut skill probability with ranking. Veterans are untouched.

    Returns (possibly adjusted p, note-or-None). The note is for the report;
    the number is clipped so a huge rank gap cannot dominate the model.
    """
    if float(n1 or 0.0) > 0 or float(n2 or 0.0) > 0:
        return float(p_skill), None
    delta = _RANKING_WEIGHT * ranking_logodds(rank1, rank2)
    if abs(delta) < 1e-9:
        return float(p_skill), None
    delta = max(-_RANKING_LOGODDS_CAP, min(_RANKING_LOGODDS_CAP, delta))
    new_p = float(expit(logit(np.clip(p_skill, _EPS, 1 - _EPS)) + delta))
    note = (f"ranking nudge: #{int(rank1)} vs #{int(rank2)} "
            f"moved p by {new_p - float(p_skill):+.3f}")
    return new_p, note


def fit_stack(y: np.ndarray, p_market: np.ndarray, p_skill: np.ndarray
              ) -> tuple[float, float]:
    """Fit (a, b) on held-out (train-era OOS) priced predictions."""
    X = np.column_stack([logit(np.clip(p_market, _EPS, 1 - _EPS)),
                         logit(np.clip(p_skill, _EPS, 1 - _EPS))])
    model = LogisticRegression(fit_intercept=False)
    model.fit(X, y)
    return float(model.coef_[0][0]), float(model.coef_[0][1])


def predict_stack(a: float, b: float, p_market: np.ndarray, p_skill: np.ndarray
                  ) -> np.ndarray:
    return expit(a * logit(np.clip(p_market, _EPS, 1 - _EPS))
                 + b * logit(np.clip(p_skill, _EPS, 1 - _EPS)))


# Belgrade postmortem: refuse a market-led debut pick when skill is a coin
# flip. Thresholds are frozen — they are a product guard, not a valid/test
# hyperparameter. See tests/test_market_trap.py.
_MARKET_TRAP_SKILL_BAND = 0.03
_MARKET_TRAP_GAP = 0.20


def debut_follows_market(skill: float, market: float,
                         f1_n_fights: float, f2_n_fights: float) -> bool:
    """True when a debut pick should be the market's side, not skill's.

    One fighter has no UFC fights, the two numbers choose different winners,
    and they are more than 20 points apart. On the 2022–2023 priced fights
    in that spot the market won 11 of 13 and skill won 2. A smaller gap, the
    same side, or two fighters who have both been in the UFC are left alone.
    """
    try:
        skill_p, market_p = float(skill), float(market)
    except (TypeError, ValueError):
        return False
    if skill_p != skill_p or market_p != market_p:  # NaN
        return False
    debut = float(f1_n_fights or 0) == 0 or float(f2_n_fights or 0) == 0
    opposite = (skill_p - 0.5) * (market_p - 0.5) < 0
    return debut and opposite and abs(market_p - skill_p) > _MARKET_TRAP_GAP


def market_trap_abstain(skill: float, market: float,
                        f1_n_fights: float, f2_n_fights: float) -> bool:
    """True when we should ship 0.5 instead of following the market.

    Debut bout + skill near 0.5 + market disagreeing hard. Veterans and
    fights where skill already has a side are left alone.
    """
    debut = float(f1_n_fights or 0) == 0 or float(f2_n_fights or 0) == 0
    return (debut
            and abs(float(skill) - 0.5) <= _MARKET_TRAP_SKILL_BAND
            and abs(float(market) - float(skill)) > _MARKET_TRAP_GAP)


def resolve_research_weight(artifact: dict | None, cfg: dict | None) -> float:
    """Frozen on the artifact at train time; config is the fallback for
    older joblibs that predate the key — so a card can pick up the new
    product setting without a full retrain."""
    if artifact and artifact.get("research_weight") is not None:
        return float(artifact["research_weight"])
    return float((cfg or {}).get("model", {}).get("research_weight") or 0.0)


def apply_market_layer(
    p_skill: np.ndarray,
    p_market: np.ndarray,
    f1_n_fights: np.ndarray,
    f2_n_fights: np.ndarray,
    stack: tuple[float, float] | None = None,
    research_weight: float = 0.0,
    career1: np.ndarray | None = None,
    career2: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """The predict.py market layer, shared with offline eval.

    Unpriced rows stay on skill. Priced rows take the market-aware stack
    when `stack` is given. When `research_weight` > 0, fights where both
    men have UFC history mix that stack with skill in log-odds — so a
    researched veteran fight can actually leave the board. Dual UFC
    debuts with regional careers get a capped mix of the same kind.
    The debut market-trap may then snap the shipped number to 0.5.
    YouTube/news nudges are predict-time only and are NOT applied here.

    Returns (shipped probability, boolean trap mask).
    """
    skill = np.asarray(p_skill, dtype=float)
    market = np.asarray(p_market, dtype=float)
    n1 = np.nan_to_num(np.asarray(f1_n_fights, dtype=float), nan=0.0)
    n2 = np.nan_to_num(np.asarray(f2_n_fights, dtype=float), nan=0.0)
    c1 = np.zeros(len(skill)) if career1 is None else np.nan_to_num(
        np.asarray(career1, dtype=float), nan=0.0)
    c2 = np.zeros(len(skill)) if career2 is None else np.nan_to_num(
        np.asarray(career2, dtype=float), nan=0.0)
    shipped = skill.copy()
    priced = np.isfinite(market) & np.isfinite(skill)
    if stack is not None and priced.any():
        a, b = stack
        shipped[priced] = predict_stack(a, b, market[priced], skill[priced])
        if research_weight:
            weights = np.array([
                float(research_weight) * history_confidence(
                    n1[i], n2[i], c1[i], c2[i])
                for i in range(len(skill))
            ])
            mix = priced & (weights > 0)
            if mix.any():
                w = weights[mix]
                shipped[mix] = expit(
                    (1.0 - w) * logit(np.clip(shipped[mix], _EPS, 1 - _EPS))
                    + w * logit(np.clip(skill[mix], _EPS, 1 - _EPS)))
    trapped = np.zeros(len(skill), dtype=bool)
    for i in np.flatnonzero(priced):
        if market_trap_abstain(float(skill[i]), float(market[i]),
                               float(n1[i]), float(n2[i])):
            shipped[i] = 0.5
            trapped[i] = True
    return shipped, trapped
