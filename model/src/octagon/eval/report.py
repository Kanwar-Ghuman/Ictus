"""Walk-forward evaluation report for a chronological split.

Default split is validation. Test is the holdout. Every run appends to
reports/experiments.csv.
"""

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from octagon.config import load_config
from octagon.eval import metrics
from octagon.models import baselines, logistic
from octagon.models.market import apply_market_layer, resolve_research_weight


def semiannual_windows(start_exclusive: str, end_inclusive: str) -> list[tuple[str, str]]:
    """Chop (start, end] into ~6-month walk-forward windows."""
    windows = []
    year, half = int(start_exclusive[:4]), 1 if start_exclusive[5:7] < "07" else 2
    # first window starts just after the boundary
    year, half = (year, 2) if half == 1 else (year + 1, 1)
    while True:
        lo = f"{year}-01-01" if half == 1 else f"{year}-07-01"
        hi = f"{year}-06-30" if half == 1 else f"{year}-12-31"
        if lo > end_inclusive:
            return windows
        windows.append((lo, min(hi, end_inclusive)))
        year, half = (year, 2) if half == 1 else (year + 1, 1)


def evaluate_split(df: pd.DataFrame, train_end: str, valid_end: str,
                   split: str, reports_dir: Path) -> str:
    if split == "valid":
        lo, hi = train_end, valid_end
    else:  # 'test'
        lo, hi = valid_end, "9999-12-31"
    eval_df = df[(df["date"] > lo) & (df["date"] <= hi)].copy()
    y = eval_df["label"].to_numpy(dtype=float)

    rows: list[dict] = []
    named_preds: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    def add(name: str, p: np.ndarray, mask: np.ndarray | None = None, note: str = ""):
        m = np.isfinite(p) if mask is None else (mask & np.isfinite(p))
        if m.sum() == 0:
            rows.append({"model": name, "note": "no fights to score" + (f" ({note})" if note else "")})
            return
        rows.append({"model": name, **metrics.summarize(y[m], p[m]), "note": note})
        named_preds[name] = (y[m], p[m])

    for name, fn in baselines.BASELINES.items():
        p = fn(eval_df)
        add(name, p, note="priced fights only" if name.startswith("market") else "")

    artifact_path = reports_dir.parent / "artifacts" / "gbm.joblib"
    artifact = None
    if artifact_path.exists():
        import joblib

        from octagon.lineage import verify_evaluation_artifact

        artifact = joblib.load(artifact_path)
        verify_evaluation_artifact(df, artifact, train_end)
    windows = semiannual_windows(lo, min(hi, str(eval_df["date"].max())))
    lr_pred = logistic.walk_forward_predict(
        df, windows,
        C=(artifact or {}).get("lr_C", 1.0),
        half_life_years=(artifact or {}).get("lr_half_life"),
    ).loc[eval_df.index].to_numpy()
    add("logistic regression (walk-forward)", lr_pred)

    gbm_cal_pred = blend_pred = shipped_pred = None
    if artifact is not None:
        from octagon.models import calibration, ensemble, gbm

        raw = gbm.walk_forward_predict(
            df, windows, artifact["params"], seed=artifact["seed"],
            include_raw=artifact.get("include_raw", False),
            n_seeds=artifact.get("n_seeds", 1)).loc[eval_df.index].to_numpy()
        add("GBM (walk-forward, tuned)", raw)
        gbm_cal_pred = np.full(len(raw), np.nan)
        finite = np.isfinite(raw)
        gbm_cal_pred[finite] = calibration.apply(artifact["iso"], raw[finite])
        add("GBM + isotonic (fit on train-era OOS)", gbm_cal_pred)
        blend_pred = ensemble.blend(lr_pred, gbm_cal_pred, artifact["weight_lr"])
        add(f"LR+GBM blend (w={artifact['weight_lr']:.2f}, tuned on train-era OOS)",
            blend_pred)

    priced = (eval_df["f1_odds"].notna() & eval_df["f2_odds"].notna()).to_numpy()
    if priced.any():
        add("logistic regression (priced subset)", lr_pred, mask=priced,
            note="same fights as market row")
        if gbm_cal_pred is not None:
            add("GBM + isotonic (priced subset)", gbm_cal_pred, mask=priced,
                note="same fights as market row")
        if blend_pred is not None:
            add("LR+GBM blend (priced subset)", blend_pred, mask=priced,
                note="same fights as market row")
        if blend_pred is not None and "market_stack" in artifact:
            from octagon.models import market as market_stack

            a, b = artifact["market_stack"]
            p_mkt = baselines.market(eval_df)
            stack = np.full(len(eval_df), np.nan)
            ok = priced & np.isfinite(blend_pred) & np.isfinite(p_mkt)
            stack[ok] = market_stack.predict_stack(a, b, p_mkt[ok], blend_pred[ok])
            add(f"market-aware stack (a={a:.2f}, b={b:.2f})", stack, mask=priced,
                note="IS the odds + residual skill — never 'beat the odds'")
            shipped, trapped = apply_market_layer(
                blend_pred, p_mkt,
                eval_df["f1_n_fights"].to_numpy(),
                eval_df["f2_n_fights"].to_numpy(),
                stack=(a, b),
                research_weight=resolve_research_weight(artifact, load_config()),
                career1=eval_df["f1_career_n_fights"].to_numpy()
                if "f1_career_n_fights" in eval_df.columns else None,
                career2=eval_df["f2_career_n_fights"].to_numpy()
                if "f2_career_n_fights" in eval_df.columns else None)
            n_trap = int(trapped.sum())
            add("shipped (stack + trap)", shipped,
                note="predict.py market layer; no YouTube/news. "
                     f"{n_trap} market-trap abstains")
            add("shipped (stack + trap, priced subset)", shipped, mask=priced,
                note="same fights as market row")
            shipped_pred = shipped

    finish_section = ""
    if artifact_path.exists():
        from octagon.eval import finish

        finish_section = finish.report(
            df, eval_df, windows, artifact["params"], seed=artifact["seed"],
            weight_round_base=artifact.get("weight_round_base", 0.5),
            weight_method_base=artifact.get("weight_method_base", 0.0),
            include_raw=artifact.get("include_raw", False),
            p_f1_wins=blend_pred)

    reports_dir.mkdir(parents=True, exist_ok=True)
    plot_path = reports_dir / f"reliability_{split}.png"
    metrics.reliability_diagram(
        {k: v for k, v in named_preds.items() if k != "coin flip"}, plot_path)

    pred_frame = eval_df[["fight_id", "date", "f1_name", "f2_name", "weight_class",
                          "title_fight", "label", "f1_odds", "f2_odds",
                          "f1_n_fights", "f2_n_fights", "f1_layoff_days",
                          "f2_layoff_days"]].copy()
    pred_frame["p_market"] = baselines.market(eval_df)
    pred_frame["p_lr"] = lr_pred
    if gbm_cal_pred is not None:
        pred_frame["p_gbm_cal"] = gbm_cal_pred
    if blend_pred is not None:
        pred_frame["p_blend"] = blend_pred
    if shipped_pred is not None:
        pred_frame["p_shipped"] = shipped_pred
    pred_frame.to_parquet(reports_dir / f"predictions_{split}.parquet", index=False)

    final_fit = logistic.fit(df[df["date"] <= lo])
    coefs = logistic.coefficients(final_fit, df).head(15)

    _append_experiment_log(reports_dir, split, rows)
    return _render_markdown(split, lo, hi, rows, coefs, plot_path, windows,
                            finish_section, artifact=artifact)


def _append_experiment_log(reports_dir: Path, split: str, rows: list[dict]) -> None:
    log_path = reports_dir / "experiments.csv"
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    frame = pd.DataFrame([{"ts": stamp, "split": split, **r} for r in rows if "n" in r])
    frame.to_csv(log_path, mode="a", header=not log_path.exists(), index=False)


def _render_markdown(split, lo, hi, rows, coefs, plot_path, windows,
                     finish_section: str = "", artifact: dict | None = None) -> str:
    lines = [
        f"# Evaluation report — {split} split",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
        f"Fights dated ({lo}, {hi}]. Walk-forward windows: "
        + ", ".join(f"{a}->{b}" for a, b in windows),
        "",
        *([
            f"Verified artifact: calibration/blend through {artifact['through']}; "
            f"reusable GBM hyperparameters tuned through {artifact['params_tuned_through']}; "
            f"historical feature fingerprint `{artifact['feature_fingerprint']}`.",
            "",
        ] if artifact is not None else []),
        "| model | n | accuracy | log loss | Brier | ROC AUC | ECE | note |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "n" not in r:
            lines.append(f"| {r['model']} | - | - | - | - | - | - | {r['note']} |")
            continue
        lines.append(
            f"| {r['model']} | {r['n']} | {r['accuracy']:.4f} | {r['log_loss']:.4f} "
            f"| {r['brier']:.4f} | {r['roc_auc']:.4f} | {r['ece']:.4f} | {r.get('note','')} |")
    lines += [
        "",
        "Better-record is a picking rule (0/0.5/1); its log loss is not meaningful. "
        "Compare probability metrics to the market row when it exists.",
        "",
        f"![reliability diagram]({plot_path.name})",
        "",
        "## Logistic regression — largest standardized coefficients",
        "",
        "Positive means: the bigger fighter1's edge in this differential, the "
        "likelier fighter1 wins (per the model).",
        "",
        "| feature | coefficient |",
        "|---|---|",
    ]
    lines += [f"| {name} | {value:+.3f} |" for name, value in coefs.items()]
    if finish_section:
        lines.append(finish_section)
    lines += [
        "",
        "---",
        "Favorite baseline is ~65% accuracy / ~0.62 log loss on priced fights.",
    ]
    return "\n".join(lines)
