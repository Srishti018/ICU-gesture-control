"""Collector output format: run_trial with the stand-in vision and ManualBio, then load it back."""

import json

from ml import validate_data
from ml.collect import recorder
from ml.collect.synthetic_vision import SyntheticVision
from ml.collect.trial import run_trial
from ml.dataset import apply_exclusions, is_synthetic, load_windows
from ml.schema import WINDOW_COLUMNS
from node.bio.manual import ManualBio


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def record(tmp_path, scenario, trial, readings):
    clock = FakeClock()
    vision = SyntheticVision(seed=trial)
    vision.set_scenario(scenario)
    bio = ManualBio()
    bio.set_baseline(70)
    it = iter(readings)
    return run_trial(vision, bio, "PTEST", scenario, trial, tmp_path, seconds=9, bio_mode="manual",
                     baseline_hr=70, ask_reading=lambda text: next(it), sleep=clock.sleep, clock=clock,
                     say=lambda *_: None)


def test_trial_files_match_schema(tmp_path):
    res = record(tmp_path, "S5", 1, [(100, 97), (94, 98)])
    base = tmp_path / res["base"]
    header = (tmp_path / f"{res['base']}_windows.csv").read_text().splitlines()[0].split(",")
    assert header == WINDOW_COLUMNS
    meta = json.loads((tmp_path / f"{res['base']}_meta.json").read_text())
    assert meta["label"] == "critical" and meta["discarded"] is False and meta["vision"] == "synthetic"
    bio_lines = (tmp_path / f"{res['base']}_bio.csv").read_text().splitlines()
    assert bio_lines[0] == "t_s,hr,spo2,finger,quality" and len(bio_lines) == 10
    data = load_windows(tmp_path)
    assert list(data["window_idx"]) == [0, 1, 2]
    assert list(data["hr"]) == [99, 97, 95]        # interpolated 100 -> 94 at window midpoints
    assert list(data["hr_delta"]) == [29, 27, 25]
    assert is_synthetic(data)
    assert base.parent == tmp_path


def test_discard_marks_windows_and_meta(tmp_path):
    res = record(tmp_path, "S1", 1, [(70, 98), (71, 98)])
    recorder.mark_discarded(tmp_path, res["base"])
    data = load_windows(tmp_path)
    assert set(data["discarded"]) == {1}
    kept, excl = apply_exclusions(data)
    assert len(kept) == 0 and excl["discarded_trials"] == 1
    assert recorder.completed_trials(tmp_path, "PTEST") == set()


def test_collector_output_passes_validate_format(tmp_path):
    for n in (1, 2):
        record(tmp_path, "S1", n, [(70, 98), (71, 98)])
        record(tmp_path, "S3", n, [(70, 98), (71, 98)])
    assert recorder.completed_trials(tmp_path, "PTEST") == {("S1", 1), ("S1", 2), ("S3", 1), ("S3", 2)}
    # 1 = not enough data (expected for a tiny dry run); 2 would mean a format error
    assert validate_data.main([str(tmp_path), "--out", str(tmp_path / "r")]) == 1
    assert "SYNTHETIC" in (tmp_path / "r" / "data_report.md").read_text()
