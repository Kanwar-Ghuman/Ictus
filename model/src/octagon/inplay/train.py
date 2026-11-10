"""Select, evaluate, and save the between-rounds model.

Protocol (dates are whole-event splits; every round of a fight shares a fold):
* train:      fights before 2022 with a closing-line prior
* validation: 2022–2023 with a closing-line prior — selects C, then the
              confidence slope for three-round fights
* test:       2024+ with the saved out-of-sample skill prediction as prior
              (no closing lines exist there); reported once, never tuned on
* artifact:   refit on every closing-line row through 2023 with the chosen C
              and slope

None of this measures profit. Kalshi's live price also watches the fight; no
historical in-play Kalshi prices exist here to compare against.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from sklearn.metrics import brier_score_loss, log_loss

from octagon.inplay.data import build_round_dataset
from octagon.inplay.model import InplayModel, dataset_features, fit

C_GRID = (0.01, 0.03, 0.1, 0.3, 1.0)
VALID_START, TEST_START = "2022-01-01", "2024-01-01"
# Only three-round fights get a slope. Five-round fights have about 50
# validation rows per round and their fitted slope changes direction between
# eras, so it would be noise.
SLOPE_LENGTHS = (3,)
SLOPE_BOUNDS = (0.5, 2.5)


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    return float(sum(abs(p[idx == b].mean() - y[idx == b].mean()) * (idx == b).mean()
                     for b in range(bins) if (idx == b).any()))


def metrics(y, p) -> dict:
    y, p = np.asarray(y), np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return {"n": len(y), "log_loss": log_loss(y, p, labels=[0, 1]),
            "brier": brier_score_loss(y, p), "accuracy": float(((p > 0.5) == y).mean()),
            "ece": ece(y, p)}


def fit_slopes(model: InplayModel, frame: pd.DataFrame, prior: str) -> dict[int, float]:
    """Per fight length, the logit multiplier with the best log loss on ``frame``."""
    logits = model.logit_f1(dataset_features(frame, prior))
    labels = frame["label"].to_numpy()
    slopes = {}
    for length in SLOPE_LENGTHS:
        mask = frame["scheduled_rounds"].to_numpy() == length
        if mask.sum() < 200:
            continue
        best = minimize_scalar(
            lambda a, z=logits[mask], y=labels[mask]: log_loss(y, 1 / (1 + np.exp(-a * z)),
                                                              labels=[0, 1]),
            bounds=SLOPE_BOUNDS, method="bounded")
        slopes[length] = round(float(best.x), 3)
    return slopes


def splits(rows: pd.DataFrame) -> dict[str, tuple[pd.DataFrame, str]]:
    market = rows[rows["p_market"].notna()]
    skill = rows[rows["p_skill"].notna()]
    return {
        "train": (market[market["date"] < VALID_START], "p_market"),
        "valid": (market[(market["date"] >= VALID_START) & (market["date"] < TEST_START)], "p_market"),
        "test": (skill[skill["date"] >= TEST_START], "p_skill"),
    }


def run(db_path: Path, greco_dir: Path, reports_dir: Path, artifact: Path, report: Path) -> dict:
    rows = build_round_dataset(db_path, greco_dir, reports_dir)
    parts = splits(rows)
    train, _ = parts["train"]
    valid, valid_prior = parts["valid"]

    search = {}
    for C in C_GRID:
        model = fit(train, "p_market", C)
        search[C] = log_loss(valid["label"], model.predict(dataset_features(valid, valid_prior)))
    best_c = min(search, key=search.get)
    raw = fit(train, "p_market", best_c)
    slopes = fit_slopes(raw, valid, valid_prior)
    selected = InplayModel(raw.scale, raw.coef, raw.meta, slopes)

    test, test_prior = parts["test"]
    three = test["scheduled_rounds"].to_numpy() == 3
    features = dataset_features(test, test_prior)
    calibration = {
        label: metrics(test["label"].to_numpy()[three], model.predict(
            features, test["scheduled_rounds"].to_numpy())[three])
        for label, model in (("raw", raw), ("with slope", selected))}

    table = []
    for name in ("valid", "test"):
        frame, prior = parts[name]
        p_model = selected.predict(dataset_features(frame, prior),
                                   frame["scheduled_rounds"].to_numpy())
        p_prior = frame[prior].to_numpy()
        for k in ["all", *sorted(frame["round"].unique())]:
            mask = np.ones(len(frame), bool) if k == "all" else frame["round"].to_numpy() == k
            y = frame["label"].to_numpy()[mask]
            table.append({"split": name, "prior_source": prior, "after_round": k,
                          **{f"prior_{m}": v for m, v in metrics(y, p_prior[mask]).items() if m != "n"},
                          **metrics(y, p_model[mask])})

    final_rows = rows[rows["p_market"].notna() & (rows["date"] < TEST_START)]
    final = fit(final_rows, "p_market", best_c)
    final = InplayModel(final.scale, final.coef, {**final.meta, "selected_C": best_c,
                                                  "valid_log_loss_by_C": {str(k): v for k, v in search.items()},
                                                  "evaluated_with": "fit before 2022; see report"},
                        slopes)
    final.save(artifact)
    write_report(report, table, search, best_c, parts, final, calibration)
    return {"selected_C": best_c, "slopes": slopes, "table": table, "artifact": str(artifact)}


def write_report(path: Path, table, search, best_c, parts, final: InplayModel,
                 calibration: dict) -> None:
    lines = [
        "# Between-rounds model evaluation", "",
        "Predicts the winner during the break after round k from the pre-fight prior plus",
        "cumulative fight stats that ESPN also reports live. Accuracy here is NOT trading",
        "profit: Kalshi's in-play price also watches the fight, and no historical in-play",
        "Kalshi prices exist to compare against. Profitability needs forward paper trading.", "",
        "## Protocol", "",
        f"- Train: closing-line prior, before {VALID_START} ({len(parts['train'][0])} rows).",
        f"- Validation: closing-line prior, {VALID_START[:4]}–2023 ({len(parts['valid'][0])} rows); "
        "selects C, then the three-round slope.",
        f"- Test: skill-model prior, {TEST_START[:4]}+ ({len(parts['test'][0])} rows); reported once.",
        f"- Selected C = {best_c} (validation log loss by C: "
        + ", ".join(f"{k}: {v:.4f}" for k, v in search.items()) + ").",
        f"- Saved artifact refit on {final.meta['n_rows']} closing-line rows through 2023.", "",
        "## Results (prior only → with fight stats)", "",
        "| split | after round | n | log loss | Brier | accuracy | ECE |",
        "|---|---|---:|---|---|---|---|",
    ]
    for r in table:
        lines.append(
            f"| {r['split']} ({r['prior_source']}) | {r['after_round']} | {r['n']} | "
            f"{r['prior_log_loss']:.4f} → **{r['log_loss']:.4f}** | {r['prior_brier']:.4f} → {r['brier']:.4f} | "
            f"{r['prior_accuracy']:.1%} → {r['accuracy']:.1%} | {r['prior_ece']:.3f} → {r['ece']:.3f} |")
    lines += ["", "Rounds 3–4 exist only for five-round fights; their samples are small.",
              "The validation rows also chose the slope, so read calibration on the test rows.", "",
              "## Confidence slope", "",
              "The raw logit is too timid in three-round fights: the fighter it puts at 25% wins",
              "about 20% of the time. One multiplier on the logit, fit on validation, fixes that.",
              "Five-round fights are left at 1.0: too few rows, and their slope flips between eras.", "",
              "Slopes: " + (", ".join(f"{k} rounds × {v}" for k, v in final.slopes.items()) or "none")
              + ".", "",
              "| three-round test fights | n | log loss | Brier | ECE |", "|---|---:|---|---|---|"]
    lines += [f"| {label} | {m['n']} | {m['log_loss']:.4f} | {m['brier']:.4f} | {m['ece']:.3f} |"
              for label, m in calibration.items()]
    lines += ["", "## Coefficients (scaled features)", "", "| feature | weight |", "|---|---:|"]
    lines += [f"| {k} | {v:+.3f} |" for k, v in final.coef.items()]
    path.write_text("\n".join(lines) + "\n")
