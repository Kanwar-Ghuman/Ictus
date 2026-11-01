"""A production artifact must not silently contaminate research evaluation."""

from argparse import Namespace

import joblib
import pytest

from octagon.eval.report import evaluate_split
from octagon.lineage import (
    feature_fingerprint,
    verify_evaluation_artifact,
    verify_reused_parameter_cutoff,
)
from tests.test_models import synthetic_features


@pytest.fixture
def historical_artifact():
    frame = synthetic_features(n_days=60)
    through = "2020-01-28"
    artifact = {
        "through": through,
        "params_tuned_through": through,
        "include_raw": False,
        "feature_fingerprint": feature_fingerprint(frame, through, False),
        "feature_fingerprint_version": 1,
    }
    return frame, artifact


def test_frozen_artifact_accepts_later_walk_forward_rows(historical_artifact):
    frame, artifact = historical_artifact
    verify_evaluation_artifact(frame, artifact, "2020-01-28")


@pytest.mark.parametrize("key", ["through", "params_tuned_through"])
def test_calibration_and_hyperparameters_must_precede_research_split(
    historical_artifact, key,
):
    frame, artifact = historical_artifact
    artifact[key] = "2020-02-01"
    with pytest.raises(SystemExit, match="after the research training cutoff"):
        verify_evaluation_artifact(frame, artifact, "2020-01-28")


@pytest.mark.parametrize("value", [None, "", "unknown", "2020-02-31"])
def test_missing_or_invalid_training_cutoff_cannot_claim_holdout(
    historical_artifact, value,
):
    frame, artifact = historical_artifact
    artifact["through"] = value
    with pytest.raises(SystemExit, match="training cutoff"):
        verify_evaluation_artifact(frame, artifact, "2020-01-28")


def test_untracked_reused_hyperparameters_cannot_claim_holdout(historical_artifact):
    frame, artifact = historical_artifact
    artifact["params_reused"] = True
    del artifact["params_tuned_through"]
    with pytest.raises(SystemExit, match="reused hyperparameters"):
        verify_evaluation_artifact(frame, artifact, "2020-01-28")


def test_legacy_missing_tuning_provenance_requires_fresh_training(historical_artifact):
    frame, artifact = historical_artifact
    del artifact["params_tuned_through"]
    with pytest.raises(SystemExit, match="hyperparameter tuning cutoff"):
        verify_evaluation_artifact(frame, artifact, "2020-01-28")


def test_reuse_allows_known_earlier_parameter_tuning(historical_artifact):
    _, artifact = historical_artifact
    assert verify_reused_parameter_cutoff(artifact, "2020-02-28") == "2020-01-28"


def test_reuse_cannot_relabel_future_parameters_as_older_training(historical_artifact):
    _, artifact = historical_artifact
    with pytest.raises(SystemExit, match="later than the requested training cutoff"):
        verify_reused_parameter_cutoff(artifact, "2020-01-01")


def test_reuse_requires_known_original_parameter_tuning(historical_artifact):
    _, artifact = historical_artifact
    del artifact["params_tuned_through"]
    with pytest.raises(SystemExit, match="without --reuse-params"):
        verify_reused_parameter_cutoff(artifact, "2020-02-28")


def test_training_refuses_unsafe_reuse_before_fitting_or_overwriting(
    historical_artifact, tmp_path, monkeypatch,
):
    from octagon.cli import cmd_train

    frame, artifact = historical_artifact
    (tmp_path / "artifacts").mkdir()
    artifact_path = tmp_path / "artifacts" / "gbm.joblib"
    joblib.dump(artifact, artifact_path)
    original = artifact_path.read_bytes()
    monkeypatch.setattr("octagon.cli.resolve_path", lambda path: tmp_path / path)
    monkeypatch.setattr("pandas.read_parquet", lambda path: frame)

    def must_not_fit(*args, **kwargs):
        pytest.fail("training used parameters from beyond its requested cutoff")

    monkeypatch.setattr("octagon.models.gbm.walk_forward_predict", must_not_fit)
    cfg = {
        "data": {"processed_dir": "data/processed"},
        "splits": {"train_end": "2020-01-01"},
        "model": {"include_raw": False, "n_seeds": 1},
        "seed": 42,
    }
    with pytest.raises(SystemExit, match="later than the requested training cutoff"):
        cmd_train(Namespace(through="2020-01-01", reuse_params=True, trials=1), cfg)
    assert artifact_path.read_bytes() == original


@pytest.mark.parametrize("version", [None, 0, 2])
def test_unverifiable_feature_provenance_rejected(historical_artifact, version):
    frame, artifact = historical_artifact
    artifact["feature_fingerprint_version"] = version
    with pytest.raises(SystemExit, match="feature fingerprint"):
        verify_evaluation_artifact(frame, artifact, "2020-01-28")


def test_missing_feature_fingerprint_rejected(historical_artifact):
    frame, artifact = historical_artifact
    del artifact["feature_fingerprint"]
    with pytest.raises(SystemExit, match="feature fingerprint"):
        verify_evaluation_artifact(frame, artifact, "2020-01-28")


def test_historical_revision_rejected_before_research_metrics(historical_artifact):
    frame, artifact = historical_artifact
    frame.loc[0, "diff_elo"] += 1
    with pytest.raises(SystemExit, match="feature history no longer matches"):
        verify_evaluation_artifact(frame, artifact, "2020-01-28")


@pytest.mark.parametrize("split", ["valid", "test"])
def test_evaluation_rejects_production_artifact_without_overwriting_results(
    historical_artifact, tmp_path, monkeypatch, split,
):
    frame, artifact = historical_artifact
    artifact["through"] = "2020-02-28"
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    joblib.dump(artifact, artifacts_dir / "gbm.joblib")
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    old_predictions = reports_dir / f"predictions_{split}.parquet"
    old_predictions.write_bytes(b"previous research output")

    def must_not_fit(*args, **kwargs):
        pytest.fail("evaluation fitted a model before verifying provenance")

    monkeypatch.setattr("octagon.eval.report.logistic.walk_forward_predict", must_not_fit)
    with pytest.raises(SystemExit, match="after the research training cutoff"):
        evaluate_split(frame, "2020-01-28", "2020-02-10", split, reports_dir)
    assert old_predictions.read_bytes() == b"previous research output"
    assert not (reports_dir / "experiments.csv").exists()
