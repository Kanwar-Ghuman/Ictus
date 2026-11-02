"""LightGBM with walk-forward Optuna tuning.

Trees are not antisymmetric, so every training row is duplicated with
corners swapped, and prediction is `p = (f(x) + 1 - f(swap(x))) / 2`.
"""

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier, early_stopping

CONTEXT_NUMERIC = ["title_fight", "scheduled_rounds", "gender_num"]
CONTEXT_CATEGORICAL = ["weight_class"]

# Per-corner columns that are labels/identifiers, never features.
_NON_FEATURE = {"f1_name", "f2_name", "f1_odds", "f2_odds"}


def feature_frame(df: pd.DataFrame, market_aware: bool = False,
                  include_raw: bool = False) -> pd.DataFrame:
    """Feature matrix. include_raw adds f1_/f2_ levels (matchup interactions).
    market_aware adds vig-free market as a differential; unpriced rows stay NaN.
    """
    cols = sorted(c for c in df.columns if c.startswith("diff_"))
    if include_raw:
        cols += sorted(c for c in df.columns
                       if c.startswith(("f1_", "f2_")) and c not in _NON_FEATURE)
    parts = [df[cols].astype(float)]
    context = pd.DataFrame({
        "title_fight": df["title_fight"].astype(float),
        "scheduled_rounds": df["scheduled_rounds"].astype(float),
        "gender_num": (df["gender"] == "F").astype(float),
        "weight_class": df["weight_class"].astype("category"),
    }, index=df.index)
    parts.append(context)
    bout_cols = sorted(c for c in df.columns if c.startswith("bout_"))
    if bout_cols:
        parts.append(df[bout_cols].astype(float))
    if market_aware:
        p1 = 1.0 / df["f1_odds"].astype(float)
        p2 = 1.0 / df["f2_odds"].astype(float)
        parts.append(pd.DataFrame(
            {"diff_market": (p1 - p2) / (p1 + p2)},
            index=df.index))
    return pd.concat(parts, axis=1)


def _flip(X: pd.DataFrame) -> pd.DataFrame:
    """Corner swap: diffs negate, f1_* and f2_* exchange. Context and bout_* stay."""
    out = X.copy()
    for col in X.columns:
        if col.startswith("diff_"):
            out[col] = -X[col]
        elif col.startswith("f1_"):
            out[col] = X["f2_" + col[3:]]
        elif col.startswith("f2_"):
            out[col] = X["f1_" + col[3:]]
    return out


def _augmented(X: pd.DataFrame, y: np.ndarray) -> tuple[pd.DataFrame, np.ndarray]:
    """Append the corner-swapped copy of every row with the label flipped."""
    return pd.concat([X, _flip(X)], ignore_index=True), np.concatenate([y, 1 - y])


class SeedEnsemble:
    """Mean of the same model trained on different seeds.

    predict_proba matches LGBMClassifier so callers can ignore which they hold.
    """

    def __init__(self, members: list[LGBMClassifier]):
        self.members = members

    def predict_proba(self, X) -> np.ndarray:
        return np.mean([m.predict_proba(X) for m in self.members], axis=0)


def fit(train_df: pd.DataFrame, params: dict, eval_df: pd.DataFrame | None = None,
        seed: int = 42, market_aware: bool = False, include_raw: bool = False,
        n_seeds: int = 1) -> LGBMClassifier | SeedEnsemble:
    """Fit on augmented training data; optional early stopping on eval_df.

    Early stopping is only used during hyperparameter tuning (where the fold
    window doubles as the stopping set). Final fits use the tuned, FIXED
    n_estimators so evaluation windows are never peeked at.
    n_seeds > 1 returns a SeedEnsemble (no early stopping in that path).
    """
    X, y = _augmented(feature_frame(train_df, market_aware, include_raw),
                      train_df["label"].to_numpy())
    if n_seeds > 1:
        members = []
        for s in range(n_seeds):
            m = LGBMClassifier(objective="binary", random_state=seed + s,
                               verbose=-1, **params)
            m.fit(X, y)
            members.append(m)
        return SeedEnsemble(members)

    model = LGBMClassifier(objective="binary", random_state=seed, verbose=-1, **params)
    kwargs = {}
    if eval_df is not None:
        kwargs = {
            "eval_set": [(feature_frame(eval_df, market_aware, include_raw),
                          eval_df["label"].to_numpy())],
            "eval_metric": "binary_logloss",
            "callbacks": [early_stopping(stopping_rounds=50, verbose=False)],
        }
    model.fit(X, y, **kwargs)
    return model


def predict_sym(model, df: pd.DataFrame, market_aware: bool = False,
                include_raw: bool = False) -> np.ndarray:
    """Symmetrized P(fighter1 wins): exact corner invariance by construction."""
    X = feature_frame(df, market_aware, include_raw)
    p = model.predict_proba(X)[:, 1]
    p_flipped = model.predict_proba(_flip(X))[:, 1]
    return (p + (1.0 - p_flipped)) / 2.0


def walk_forward_predict(
    df: pd.DataFrame, windows: list[tuple[str, str]], params: dict, seed: int = 42,
    market_aware: bool = False, include_raw: bool = False, n_seeds: int = 1,
) -> pd.Series:
    """Same contract as logistic.walk_forward_predict: for each window,
    train on strictly earlier fights only. No early stopping here."""
    out = pd.Series(np.nan, index=df.index)
    for start, end in windows:
        train = df[df["date"] < start]
        window = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(train) == 0 or len(window) == 0:
            continue
        model = fit(train, params, seed=seed, market_aware=market_aware,
                    include_raw=include_raw, n_seeds=n_seeds)
        out.loc[window.index] = predict_sym(model, window, market_aware=market_aware,
                                            include_raw=include_raw)
    return out


def tune(df: pd.DataFrame, tuning_windows: list[tuple[str, str]],
         n_trials: int = 40, seed: int = 42,
         include_raw: bool = False) -> tuple[dict, float]:
    """Optuna search scored by mean walk-forward log loss over train-era folds.

    Each trial trains with early stopping (the fold window is the stopping
    set — mildly optimistic for iteration count, standard practice); the
    returned params fix n_estimators at the best trial's mean best-iteration
    so later fits never see their evaluation data.
    """
    import optuna

    from octagon.eval.metrics import log_loss

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": 2000,  # ceiling; early stopping picks the real one
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 4, 64, log=True),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 200, log=True),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.4, 1.0),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
            "bagging_freq": 1,
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        }
        losses, best_iters = [], []
        for start, end in tuning_windows:
            train = df[df["date"] < start]
            window = df[(df["date"] >= start) & (df["date"] <= end)]
            if len(train) < 500 or len(window) == 0:
                continue
            model = fit(train, params, eval_df=window, seed=seed, include_raw=include_raw)
            losses.append(log_loss(window["label"].to_numpy(),
                                   predict_sym(model, window, include_raw=include_raw)))
            best_iters.append(model.best_iteration_ or params["n_estimators"])
        trial.set_user_attr("mean_best_iter", float(np.mean(best_iters)))
        return float(np.mean(losses))

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=seed))

    def _log(study: optuna.Study, trial: optuna.trial.FrozenTrial) -> None:
        if trial.value is None:
            return
        print(f"  trial {trial.number + 1}/{n_trials} logloss={trial.value:.4f} "
              f"best={study.best_value:.4f}", flush=True)

    study.optimize(objective, n_trials=n_trials, show_progress_bar=False,
                   callbacks=[_log])

    best = dict(study.best_params)
    best["n_estimators"] = max(20, int(study.best_trial.user_attrs["mean_best_iter"]))
    best["bagging_freq"] = 1
    return best, study.best_value
