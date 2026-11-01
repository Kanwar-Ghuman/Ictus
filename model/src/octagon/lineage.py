"""Deterministic lineage checks for tuned artifacts and replayed features."""

import hashlib
from datetime import date

import numpy as np
import pandas as pd


_OUTCOME_COLUMNS = (
    "fight_id", "date", "label", "method", "end_round", "duration_s",
)


def feature_fingerprint(df: pd.DataFrame, through: str,
                        include_raw: bool) -> str:
    """Hash the exact historical feature snapshot used for tuning.

    Card prediction intentionally refits estimators on newly appended fights,
    but its calibrator and mixture weights were learned on history through
    ``through``.  Hashing only that fixed prefix permits new fights while
    catching revisions, parser drift, or feature-code changes in the data on
    which those frozen parameters depend.
    """
    from octagon.models.gbm import feature_frame

    snapshot = df[df["date"] <= through].copy()
    sort_columns = [c for c in ("date", "fight_id") if c in snapshot]
    if sort_columns:
        snapshot = snapshot.sort_values(sort_columns, kind="stable")
    snapshot = snapshot.reset_index(drop=True)

    features = feature_frame(snapshot, include_raw=include_raw)
    metadata = snapshot[[c for c in _OUTCOME_COLUMNS if c in snapshot]].copy()
    frame = pd.concat([metadata.reset_index(drop=True),
                       features.reset_index(drop=True)], axis=1)

    digest = hashlib.sha256()
    digest.update(f"octagon-feature-snapshot-v1\n{len(frame)}\n".encode())
    for column in frame.columns:
        digest.update(f"{column}\n".encode())
        series = frame[column]
        if pd.api.types.is_numeric_dtype(series.dtype):
            canonical = pd.Series(
                np.asarray(pd.to_numeric(series, errors="coerce"), dtype="float64"),
                name=column,
            )
        else:
            canonical = series.astype("string").fillna("<NA>").rename(column)
        hashes = pd.util.hash_pandas_object(canonical, index=False,
                                            categorize=True).to_numpy()
        digest.update(hashes.tobytes())
    return digest.hexdigest()


def verify_artifact_snapshot(df: pd.DataFrame, artifact: dict) -> None:
    """Reject a tuned artifact when its historical feature prefix has moved."""
    expected = artifact.get("feature_fingerprint")
    if not expected:  # compatibility for artifacts produced before v2.8
        return
    actual = feature_fingerprint(
        df, str(artifact["through"]), bool(artifact.get("include_raw", False)))
    if actual != expected:
        raise SystemExit(
            "The feature history no longer matches the data used to tune this "
            "artifact. Run `octagon build-features`, then `octagon train` before "
            "predicting a card."
        )


def _artifact_date(value: object, label: str) -> str:
    """Read a verifiable ISO date without inventing provenance for old artifacts."""
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise SystemExit(
            f"The artifact has no valid {label}. Run `octagon train` without "
            "--reuse-params at the intended training cutoff to record provenance."
        ) from None
    return value


def verify_reused_parameter_cutoff(artifact: dict, through: str) -> str:
    """Prevent later-tuned hyperparameters from being relabeled as an earlier fit."""
    tuned_through = _artifact_date(
        artifact.get("params_tuned_through"), "hyperparameter tuning cutoff")
    if tuned_through > through:
        raise SystemExit(
            f"Reused hyperparameters were tuned through {tuned_through}, later than "
            f"the requested training cutoff {through}. Run `octagon train` without "
            "--reuse-params to tune using only the requested history."
        )
    return tuned_through


def verify_evaluation_artifact(df: pd.DataFrame, artifact: dict,
                               train_end: str) -> None:
    """Require frozen research tuning and matching data before scoring any holdout.

    Walk-forward estimators alone do not make an evaluation out of sample:
    calibration, blend weights, and hyperparameters must also precede the
    research split. Legacy card prediction remains compatible, but an
    untracked artifact cannot support a new research performance claim.
    """
    through = _artifact_date(artifact.get("through"), "training cutoff")
    if artifact.get("params_reused") and not artifact.get("params_tuned_through"):
        raise SystemExit(
            "The artifact's reused hyperparameters have no recorded tuning cutoff. "
            "Run `octagon train` without --reuse-params before research evaluation."
        )
    tuned_through = _artifact_date(
        artifact.get("params_tuned_through"), "hyperparameter tuning cutoff")
    for label, cutoff in (("Calibration and blend", through),
                          ("Hyperparameter tuning", tuned_through)):
        if cutoff > train_end:
            raise SystemExit(
                f"{label} extends through {cutoff}, after the research training cutoff "
                f"{train_end}. This artifact cannot produce a holdout report. Run "
                f"`octagon train --through {train_end}` without --reuse-params first."
            )
    if (artifact.get("feature_fingerprint_version") != 1
            or not artifact.get("feature_fingerprint")):
        raise SystemExit(
            "The artifact has no supported feature fingerprint for research evaluation. "
            "Run `octagon build-features`, then `octagon train` without --reuse-params "
            "at the research training cutoff."
        )
    verify_artifact_snapshot(df, artifact)
