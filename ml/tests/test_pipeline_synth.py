import json
from pathlib import Path

import pytest

from ml import train, validate_data
from ml.synth import generate

METRIC_KEYS = {"accuracy", "macro_f1", "per_class", "confusion", "alert", "critical", "per_person_accuracy"}
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def synth_dir(tmp_path):
    generate(tmp_path / "data", seed=0)
    return tmp_path


def test_validate_and_train_on_synthetic(synth_dir):
    out = synth_dir / "results"
    assert validate_data.main([str(synth_dir / "data"), "--out", str(out)]) == 0
    report = (out / "data_report.md").read_text()
    assert "SYNTHETIC" in report

    train.main(["--data", str(synth_dir / "data"), "--out", str(out), "--models", str(synth_dir / "models")])
    for name in ["metrics.json", "metrics.md", "confusion.png", "coefficients.png", "coefficients.csv"]:
        assert (out / name).exists(), name
    for name in ["model.joblib", "model.json"]:
        assert (synth_dir / "models" / name).exists(), name

    m = json.loads((out / "metrics.json").read_text())
    assert m["synthetic"] is True
    assert set(m["methods"]) == {"model", "rule", "gesture_only"}
    for method in m["methods"].values():
        assert METRIC_KEYS <= set(method)
        assert set(method["alert"]) == {"precision", "recall", "false_positive_rate"}
        assert set(method["critical"]) == {"precision", "recall"}
        assert len(method["confusion"]) == 3
    assert m["methods"]["gesture_only"]["per_class"]["critical"]["recall"] == 0
    assert "accuracy" in m["random_split"] and m["random_split"]["note"]
    assert set(m["methods"]["model"]["per_person_accuracy"]) == {"P1", "P2", "P3"}


def test_exclusions_drop_first_window(synth_dir):
    from ml.dataset import apply_exclusions, load_windows
    data = load_windows(synth_dir / "data")
    kept, excl = apply_exclusions(data)
    assert (kept["window_idx"] == 0).sum() == 0
    assert excl["first_window"] == data["trial_id"].nunique()


def test_validate_reports_not_enough_data(tmp_path):
    generate(tmp_path / "data", seed=0)
    for f in (tmp_path / "data").glob("P2_*"):
        f.unlink()
    for f in (tmp_path / "data").glob("P3_*"):
        f.unlink()
    assert validate_data.main([str(tmp_path / "data"), "--out", str(tmp_path / "r")]) == 1


def test_validate_format_error(tmp_path):
    (tmp_path / "x_windows.csv").write_text("person,trial\nP1,1\n")
    assert validate_data.main([str(tmp_path), "--out", str(tmp_path / "r")]) == 2


def test_synthetic_never_written_to_repo(tmp_path):
    with pytest.raises(ValueError):
        generate(REPO_ROOT / "ml" / "data" / "raw" / "x", seed=0)
    generate(tmp_path / "data", seed=0)
    with pytest.raises(SystemExit):
        train.train(tmp_path / "data", REPO_ROOT / "ml" / "results")
