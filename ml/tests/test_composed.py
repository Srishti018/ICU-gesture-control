"""Composed-dataset pipeline (ml.train_composed) on SYNTHETIC gesture files + the real BIDMC windows."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml import train_composed as tc
from ml.fusion_runtime import FusionModel
from ml.schema import CLASSES, FEATURES
from ml.synth import generate_gestures

REPO_ROOT = Path(__file__).resolve().parents[2]
VITALS = REPO_ROOT / "ml" / "data" / "public" / "bidmc_news2_windows.csv"


@pytest.fixture(scope="module")
def gestures_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("gestures")
    generate_gestures(d, seed=3)
    return d


@pytest.fixture(scope="module")
def run_out(tmp_path_factory, gestures_dir):
    out = tmp_path_factory.mktemp("composed")
    metrics = tc.run(gestures_dir, VITALS, out / "results", out / "models")
    return out, metrics


def test_load_gestures_drops_first_window_and_flags_synthetic(gestures_dir):
    g = tc.load_gestures(gestures_dir)
    assert g.attrs["synthetic"]
    assert g.attrs["exclusions"]["first_window"] == 72          # one per trial: 3 people x 24 trials
    assert len(g) == 72 * 9


def test_unflagged_duplicate_attempt_keeps_latest(gestures_dir, tmp_path):
    import shutil
    for f in gestures_dir.glob("*_windows.csv"):
        shutil.copy(f, tmp_path / f.name)
    first = sorted(tmp_path.glob("P1_N_REST_T1_*_windows.csv"))[0]
    shutil.copy(first, tmp_path / first.name.replace("20261025-", "20261024-"))  # older, not flagged
    g = tc.load_gestures(tmp_path)
    dropped = g.attrs["exclusions"]["attempts_dropped"]
    assert dropped["unflagged_duplicates"] == [first.name.replace("20261025-", "20261024-")[:-len("_windows.csv")]]
    assert dropped["total"] == 1
    assert len(g) == 72 * 9


def test_compose_pairing_rule_and_balance(gestures_dir):
    gest, vit = tc.load_gestures(gestures_dir), tc.load_vitals(VITALS)
    pairs = tc.compose(gest, vit, np.random.default_rng(0))
    counts = pairs["label"].value_counts()
    assert counts["routine"] == counts["urgent"] == counts["critical"]
    by_source = pairs.groupby(["gesture", "vitals_label"])["label"].unique()
    assert list(by_source[("gesture", "normal")]) == ["urgent"]
    assert list(by_source[("gesture", "abnormal")]) == ["critical"]
    assert list(by_source[("no_gesture", "normal")]) == ["routine"]
    assert list(by_source[("no_gesture", "abnormal")]) == ["routine"]
    routine = pairs[pairs["label"] == "routine"]["vitals_label"].value_counts()
    assert abs(routine["normal"] - routine["abnormal"]) <= 1
    # urgent and critical use the same gesture windows; only the vitals differ
    u = pairs[pairs["label"] == "urgent"][["trial_id", "gesture_conf", "tremor"]].reset_index(drop=True)
    c = pairs[pairs["label"] == "critical"][["trial_id", "gesture_conf", "tremor"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(u, c)


def test_compose_exclude_mode(gestures_dir):
    gest, vit = tc.load_gestures(gestures_dir), tc.load_vitals(VITALS)
    pairs = tc.compose(gest, vit, np.random.default_rng(0), "exclude")
    assert set(pairs.loc[pairs["label"] == "routine", "vitals_label"]) == {"normal"}
    assert pairs["label"].value_counts().nunique() == 1


def test_patient_groups_have_both_classes_and_are_deterministic():
    vit = tc.load_vitals(VITALS)
    g1, g2 = tc.patient_groups(vit, 3, 42), tc.patient_groups(vit, 3, 42)
    assert g1 == g2 and set(g1.values()) == {0, 1, 2}
    for g in range(3):
        assert set(vit.loc[vit["patient"].map(g1) == g, "label"]) == {"normal", "abnormal"}


def test_folds_never_share_person_or_patient_group(run_out):
    _, m = run_out
    assert len(m["folds"]) == 9
    assert {(f["test_person"], f["test_group"]) for f in m["folds"]} == {(p, g) for p in ("P1", "P2", "P3")
                                                                      for g in range(3)}
    groups = m["split"]["patient_groups"]
    assert not set(groups["0"]) & set(groups["1"]) and not set(groups["1"]) & set(groups["2"])


def test_outputs_and_runtime_parity(run_out):
    out, m = run_out
    for name in ("metrics.json", "metrics.md", "per_fold.csv", "confusion.png", "coefficients.png",
                 "coefficients.csv", "final_pairs.csv"):
        assert (out / "results" / name).exists(), name
    assert m["synthetic"] and "SYNTHETIC" in (out / "results" / "metrics.md").read_text()
    assert set(m["mean"]) == {"model", "rule", "gesture_only"}
    assert m["final"]["parity_max_abs_diff"] < 1e-9
    runtime = FusionModel.load(out / "models" / "model.json")
    pairs = pd.read_csv(out / "results" / "final_pairs.csv")
    import joblib
    pipe = joblib.load(out / "models" / "model.joblib")
    sk = pipe.predict_proba(pairs[FEATURES].to_numpy())[:, [list(pipe.classes_).index(c) for c in CLASSES]]
    for i, row in enumerate(pairs[FEATURES].head(200).to_dict("records")):
        p = runtime.predict_proba({k: float(v) for k, v in row.items()})
        assert np.max(np.abs(np.array([p[c] for c in CLASSES]) - sk[i])) < 1e-9


def test_same_seed_same_result(run_out, gestures_dir, tmp_path):
    _, m = run_out
    again = tc.run(gestures_dir, VITALS, tmp_path / "r", tmp_path / "m")
    assert json.dumps(again["folds"]) == json.dumps(m["folds"])
    assert again["coefficients"] == m["coefficients"]


def test_refuses_synthetic_into_protected_folders(gestures_dir):
    with pytest.raises(SystemExit, match="refusing"):
        tc.run(gestures_dir, VITALS, REPO_ROOT / "ml" / "results", REPO_ROOT / "ml" / "models")


def test_rejects_fusion_protocol_files(tmp_path):
    from ml.synth import generate
    generate(tmp_path / "d", seed=1)
    with pytest.raises(SystemExit, match="not gesture-only"):
        tc.load_gestures(tmp_path / "d")


def test_report_generated_from_outputs(run_out, tmp_path):
    from ml import report
    out, m = run_out
    doc_path = tmp_path / "ML_RESULTS.md"
    assert report.main(["--results", str(out / "results"), "--models", str(out / "models"),
                        "--out", str(doc_path)]) == 0
    doc = doc_path.read_text()
    assert "SYNTHETIC" in doc
    assert f"{m['mean']['model']['accuracy']['mean']:.3f} ± {m['mean']['model']['accuracy']['sd']:.3f}" in doc
    assert f"{m['random_split']['accuracy']:.3f}" in doc
    assert "bidmc_39" in doc and "bidmc_52" in doc               # replay inputs listed
    assert doc.count("replay |") == 4                             # four-case check rows
    assert "## 5. Discussion" in doc and "more accurate in" in doc


def test_report_refuses_synthetic_into_docs(run_out):
    from ml import report
    out, _ = run_out
    doc = REPO_ROOT / "docs" / "ML_RESULTS.md"
    before = doc.read_bytes() if doc.exists() else None
    with pytest.raises(SystemExit, match="refusing"):
        report.main(["--results", str(out / "results"), "--models", str(out / "models")])
    assert (doc.read_bytes() if doc.exists() else None) == before
