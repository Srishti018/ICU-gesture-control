import json
from pathlib import Path

import numpy as np
import pytest

from ml.dataset import apply_exclusions, load_windows
from ml.export import export
from ml.fusion_runtime import FusionModel
from ml.schema import CLASSES, FEATURES
from ml.synth import generate
from ml.train import build_pipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_MODEL = REPO_ROOT / "ml" / "models" / "model.json"
REAL_DATA = REPO_ROOT / "ml" / "data" / "raw"


def _fit_synthetic(tmp_path):
    generate(tmp_path / "data", seed=1)
    kept, _ = apply_exclusions(load_windows(tmp_path / "data"))
    X = kept[FEATURES].astype(float).to_numpy()
    y = kept["label"].to_numpy()
    pipe = build_pipeline().fit(X, y)
    export(pipe, tmp_path / "model.json", n_train=len(y))
    return pipe, kept, X


def _assert_parity(pipe, model, kept, X):
    sk = pipe.predict_proba(X)
    order = [list(pipe.classes_).index(c) for c in CLASSES]
    sk = sk[:, order]
    for i, row in enumerate(kept[FEATURES].to_dict("records")):
        p = model.predict_proba(row)
        assert list(p) == CLASSES
        got = np.array([p[c] for c in CLASSES])
        assert np.max(np.abs(got - sk[i])) < 1e-9
        assert abs(got.sum() - 1.0) < 1e-9


def test_runtime_matches_sklearn(tmp_path):
    pipe, kept, X = _fit_synthetic(tmp_path)
    model = FusionModel.load(tmp_path / "model.json")
    _assert_parity(pipe, model, kept, X)


def test_exported_json_shape(tmp_path):
    _fit_synthetic(tmp_path)
    data = json.loads((tmp_path / "model.json").read_text())
    assert set(data) == {"version", "trained_at", "features", "classes", "mean", "scale", "coef",
                         "intercept", "n_train", "sklearn_version"}
    assert data["features"] == FEATURES and data["classes"] == CLASSES
    assert np.array(data["coef"]).shape == (3, 4) and len(data["intercept"]) == 3


def test_wrong_classes_raise(tmp_path):
    _fit_synthetic(tmp_path)
    data = json.loads((tmp_path / "model.json").read_text())
    data["classes"] = ["critical", "routine", "urgent"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        FusionModel.load(bad)


def test_missing_or_bad_feature_raises(tmp_path):
    _fit_synthetic(tmp_path)
    model = FusionModel.load(tmp_path / "model.json")
    good = {"gesture_conf": 0.9, "tremor": 0.02, "hr_delta": 25, "spo2": 98}
    for name, bad in [("hr_delta", None), ("spo2", "98"), ("tremor", float("nan"))]:
        with pytest.raises(ValueError, match=name):
            model.predict_proba({**good, name: bad})
    with pytest.raises(ValueError, match="gesture_conf"):
        model.predict_proba({k: v for k, v in good.items() if k != "gesture_conf"})


REAL_PAIRS = REPO_ROOT / "ml" / "results" / "final_pairs.csv"  # composed dataset (ml.train_composed)


@pytest.mark.skipif(not (REAL_MODEL.exists() and (REAL_PAIRS.exists() or any(REAL_DATA.glob("*_windows.csv")))),
                    reason="real model and data not available yet")
def test_real_model_parity():
    import joblib
    import pandas as pd
    pipe = joblib.load(REAL_MODEL.with_suffix(".joblib"))
    if REAL_PAIRS.exists():
        kept = pd.read_csv(REAL_PAIRS)
    else:
        kept, _ = apply_exclusions(load_windows(REAL_DATA))
    kept = kept.copy()
    kept[FEATURES] = kept[FEATURES].astype(float)
    _assert_parity(pipe, FusionModel.load(REAL_MODEL), kept, kept[FEATURES].to_numpy())
