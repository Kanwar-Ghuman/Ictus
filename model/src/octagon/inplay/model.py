"""Between-rounds winner model: pre-fight prior + cumulative fight stats.

logit P(f1 wins | end of round k) = w · x, with NO intercept and every
feature antisymmetric under a corner swap (prior logit, f1-minus-f2 stat
differences, and those times the elapsed fraction k / scheduled rounds).
Swapping corners therefore negates the logit exactly: the model cannot learn
ufcstats' winner-first listing order, and P(f1) + P(f2) = 1 by construction.

Trained on vig-free closing lines as the prior. Live, the prior is the Kalshi
price just before the bout started, or the skill model's p_skill fallback.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Cumulative stats used as f1-minus-f2 differences (ctrl in minutes).
DIFF_STATS = ["sig_l", "sig_a", "head_l", "body_l", "leg_l", "tot_l",
              "td_l", "td_a", "kd", "sub", "ctrl"]
FEATURES = (["prior", "prior_x_frac"] + DIFF_STATS + [f"{s}_x_frac" for s in DIFF_STATS])
PRIOR_CLIP = 1e-3


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), PRIOR_CLIP, 1 - PRIOR_CLIP)
    return np.log(p / (1 - p))


def feature_frame(f1: pd.DataFrame, f2: pd.DataFrame, prior, round_k, scheduled) -> pd.DataFrame:
    """f1/f2: cumulative stats with columns ``DIFF_STATS``; aligned rows."""
    frac = np.asarray(round_k, dtype=float) / np.asarray(scheduled, dtype=float)
    out = {"prior": logit(prior)}
    out["prior_x_frac"] = out["prior"] * frac
    for s in DIFF_STATS:
        diff = f1[s].to_numpy(dtype=float) - f2[s].to_numpy(dtype=float)
        if s == "ctrl":
            diff = diff / 60.0
        out[s] = diff
        out[f"{s}_x_frac"] = diff * frac
    return pd.DataFrame(out)[FEATURES]


def dataset_features(rows: pd.DataFrame, prior_column: str) -> pd.DataFrame:
    f1 = rows[[f"f1_{s}" for s in DIFF_STATS]].set_axis(DIFF_STATS, axis=1)
    f2 = rows[[f"f2_{s}" for s in DIFF_STATS]].set_axis(DIFF_STATS, axis=1)
    return feature_frame(f1.reset_index(drop=True), f2.reset_index(drop=True),
                         rows[prior_column].to_numpy(), rows["round"].to_numpy(),
                         rows["scheduled_rounds"].to_numpy())


@dataclass(frozen=True)
class InplayModel:
    scale: dict[str, float]
    coef: dict[str, float]
    meta: dict

    def logit_f1(self, x: pd.DataFrame) -> np.ndarray:
        z = np.zeros(len(x))
        for name in FEATURES:
            z += x[name].to_numpy(dtype=float) / self.scale[name] * self.coef[name]
        return z

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return 1 / (1 + np.exp(-self.logit_f1(x)))

    def predict_one(self, f1: dict, f2: dict, prior: float, round_k: int, scheduled: int) -> float:
        if isinstance(round_k, bool) or not isinstance(round_k, int):
            raise ValueError("In-play inputs out of the trained range")
        return self.predict_progress(f1, f2, prior, round_k, scheduled)

    def predict_progress(self, f1: dict, f2: dict, prior: float,
                         elapsed_rounds: float, scheduled: int) -> float:
        """P(f1 wins) after ``elapsed_rounds`` of a 3- or 5-round fight.

        End-of-round snapshots pass an integer. A live round passes a fraction
        (completed rounds plus how far the five-minute clock has run) so the
        same antisymmetric weights move as the fight does.
        """
        if isinstance(elapsed_rounds, bool) or not isinstance(elapsed_rounds, (int, float)):
            raise ValueError("In-play inputs out of the trained range")
        elapsed = float(elapsed_rounds)
        if (not 0 < prior < 1 or not math.isfinite(elapsed) or not 0 < elapsed < scheduled
                or scheduled not in (3, 5)):
            raise ValueError("In-play inputs out of the trained range")
        x = feature_frame(pd.DataFrame([f1]), pd.DataFrame([f2]), [prior], [elapsed], [scheduled])
        p = float(self.predict(x)[0])
        if not math.isfinite(p):
            raise ValueError("Non-finite in-play probability")
        return p

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"features": FEATURES, "scale": self.scale,
                                    "coef": self.coef, "meta": self.meta}, indent=2))

    @classmethod
    def load(cls, path: Path) -> InplayModel:
        raw = json.loads(path.read_text())
        if raw.get("features") != FEATURES:
            raise ValueError("In-play artifact features do not match this code")
        return cls(scale={k: float(v) for k, v in raw["scale"].items()},
                   coef={k: float(v) for k, v in raw["coef"].items()}, meta=raw.get("meta", {}))


def fit(rows: pd.DataFrame, prior_column: str, C: float) -> InplayModel:
    from sklearn.linear_model import LogisticRegression

    x = dataset_features(rows, prior_column)
    # Scale only (no centering): centering would break antisymmetry.
    scale = x.abs().mean().replace(0, 1.0)
    model = LogisticRegression(C=C, fit_intercept=False, max_iter=5000)
    model.fit(x / scale, rows["label"].to_numpy())
    return InplayModel(scale={k: float(v) for k, v in scale.items()},
                       coef=dict(zip(FEATURES, map(float, model.coef_[0]), strict=True)),
                       meta={"prior_column": prior_column, "C": C, "n_rows": int(len(rows)),
                             "n_fights": int(rows["fight_id"].nunique()),
                             "date_min": str(rows["date"].min()), "date_max": str(rows["date"].max())})
