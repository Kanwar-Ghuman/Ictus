"""Logistic regression on `diff_*` columns.

No intercept, zero-impute, uncentered scaling: swapping corners negates
the input, so `predict(A,B) = 1 - predict(B,A)` to machine precision.
"""

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def diff_columns(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df.columns if c.startswith("diff_"))


def _matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Feature matrix as floats. An all-missing column arrives from pandas
    as object dtype (None values), which the imputer would silently pass
    through; astype(float) turns every None into a real NaN first."""
    return df[diff_columns(df)].astype(float)


def make_pipeline(C: float = 1.0) -> Pipeline:
    """Impute -> scale -> logistic regression, one object.

    A Pipeline exists so that imputer and scaler statistics are fit ONLY on
    whatever .fit() sees (training data) — the leakage checklist's last box.
    """
    return Pipeline([
        # keep_empty_features: an era with (say) no control-time data must
        # still produce that column, or train/predict shapes drift apart.
        ("impute", SimpleImputer(strategy="constant", fill_value=0.0,
                                 keep_empty_features=True)),
        ("scale", StandardScaler(with_mean=False)),  # centering would break antisymmetry
        ("model", LogisticRegression(fit_intercept=False, C=C, max_iter=1000)),
    ])


def recency_weights(dates: pd.Series, as_of: str,
                    half_life_years: float | None) -> np.ndarray | None:
    """Exponential sample weights. None means every fight counts equally."""
    if not half_life_years:
        return None
    age_days = (pd.Timestamp(as_of) - pd.to_datetime(dates)).dt.days.to_numpy(dtype=float)
    return np.power(0.5, np.clip(age_days, 0.0, None) / (365.25 * float(half_life_years)))


def fit(train: pd.DataFrame, C: float = 1.0,
        half_life_years: float | None = None, as_of: str | None = None) -> Pipeline:
    pipeline = make_pipeline(C=C)
    weights = recency_weights(train["date"], as_of or str(train["date"].max()),
                              half_life_years)
    fit_params = {} if weights is None else {"model__sample_weight": weights}
    pipeline.fit(_matrix(train), train["label"], **fit_params)
    return pipeline


def predict(pipeline: Pipeline, df: pd.DataFrame) -> np.ndarray:
    """P(fighter1 wins) for each row."""
    return pipeline.predict_proba(_matrix(df))[:, 1]


def coefficients(pipeline: Pipeline, df: pd.DataFrame) -> pd.Series:
    """Standardized coefficients, largest effect first — the 'why'."""
    coefs = pipeline.named_steps["model"].coef_[0]
    return (pd.Series(coefs, index=diff_columns(df))
            .sort_values(key=abs, ascending=False))


def walk_forward_predict(
    df: pd.DataFrame, windows: list[tuple[str, str]], C: float = 1.0,
    half_life_years: float | None = None,
) -> pd.Series:
    """Expanding-window evaluation: for each window, train on strictly
    earlier fights, predict the window. No fight is ever predicted by a
    model that saw it — or saw anything after it.

    Returns predictions indexed like df, NaN outside the windows.
    """
    out = pd.Series(np.nan, index=df.index)
    for start, end in windows:
        train = df[df["date"] < start]
        window = df[(df["date"] >= start) & (df["date"] <= end)]
        if len(train) == 0 or len(window) == 0:
            continue
        model = fit(train, C=C, half_life_years=half_life_years, as_of=start)
        out.loc[window.index] = predict(model, window)
    return out


# Searched by `octagon train` on train-era walk-forward folds only.
C_GRID = (0.03, 0.1, 0.3, 1.0)
HALF_LIFE_GRID = (None, 6.0, 10.0)


def tune(df: pd.DataFrame, windows: list[tuple[str, str]],
         c_grid=C_GRID, half_life_grid=HALF_LIFE_GRID) -> tuple[float, float | None, float]:
    """Pick (C, half-life) by mean walk-forward log loss on the given folds.

    Small grid on purpose: the reference model should stay the simple
    thing it is, and both knobs move log loss by thousandths.
    """
    from octagon.eval.metrics import log_loss

    best: tuple[float, float | None, float] | None = None
    for C in c_grid:
        for half_life in half_life_grid:
            pred = walk_forward_predict(df, windows, C=C, half_life_years=half_life)
            mask = pred.notna()
            loss = log_loss(df.loc[mask, "label"].to_numpy(dtype=float),
                            pred[mask].to_numpy())
            if best is None or loss < best[2]:
                best = (float(C), half_life, float(loss))
    assert best is not None
    return best
