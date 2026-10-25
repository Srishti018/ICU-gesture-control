import json

import pytest

from node.bio import BioUnavailable, make_bio_source
from node.bio.manual import ManualBio
from node.bio.replay import ReplayBio


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def write_replay(folder, name="rest", hrs=(70, 71, 72, 73, 74, 75), spo2=98, baseline=70):
    with (folder / f"{name}.csv").open("w") as fh:
        fh.write("t_s,hr,spo2\n")
        for i, hr in enumerate(hrs):
            fh.write(f"{i},{hr},{spo2}\n")
    (folder / f"{name}.json").write_text(json.dumps({
        "kind": name, "person": "PX", "baseline_hr": baseline, "source": "manual",
        "recorded_at": "2026-10-23T09:00:00", "seconds": len(hrs)}))


def test_replay_window_and_loop(tmp_path):
    write_replay(tmp_path)
    clock = Clock()
    bio = ReplayBio("rest", replay_dir=tmp_path, clock=clock)
    bio.start()
    clock.t += 3.5                       # position 3 -> rows 1,2,3 = 71,72,73
    w = bio.window()
    assert w == {"hr": 72, "spo2": 98, "hr_delta": 2, "finger": True, "source": "replay", "quality": 1.0}
    clock.t += 3.0                       # position 6 % 6 = 0 -> rows 4,5,0 = 74,75,70 (wraps)
    assert bio.position() == 0
    assert bio.window()["hr"] == 73


def test_replay_baseline_from_json(tmp_path):
    write_replay(tmp_path, baseline=60)
    bio = ReplayBio("rest", replay_dir=tmp_path, clock=Clock())
    assert bio.baseline_hr() == 60
    assert bio.window()["hr_delta"] == bio.window()["hr"] - 60


def test_replay_restart_and_new_instance_start_at_row_0(tmp_path):
    write_replay(tmp_path)
    clock = Clock()
    bio = ReplayBio("rest", replay_dir=tmp_path, clock=clock)
    bio.start()
    clock.t += 4.2
    assert bio.position() == 4
    bio.restart()
    assert bio.position() == 0
    other = ReplayBio("rest", replay_dir=tmp_path, clock=clock)
    other.start()
    assert other.position() == 0


def test_replay_missing_file(tmp_path):
    with pytest.raises(BioUnavailable, match="ml/replay/nope.csv not found"):
        ReplayBio("nope", replay_dir=tmp_path)


def test_replay_rejects_gaps(tmp_path):
    (tmp_path / "rest.csv").write_text("t_s,hr,spo2\n0,70,98\n2,71,98\n")
    (tmp_path / "rest.json").write_text(json.dumps({"baseline_hr": 70}))
    with pytest.raises(BioUnavailable, match="without gaps"):
        ReplayBio("rest", replay_dir=tmp_path)


def test_replay_files_load_and_behave():
    clock = Clock()
    rest = ReplayBio("rest", clock=clock)
    ex = ReplayBio("exertion", clock=clock)
    assert rest.meta["source"] == ex.meta["source"] == "BIDMC (PhysioNet)"
    assert rest.baseline_hr() == ex.baseline_hr() == 75
    assert len(rest.rows) == 60 and len(ex.rows) == 90
    assert all(spo2 >= 96 and 51 <= hr <= 90 for hr, spo2 in rest.rows)    # NEWS2-normal every second
    assert all(spo2 <= 93 or hr >= 111 for hr, spo2 in ex.rows)            # NEWS2-abnormal every second
    rest.start()
    ex.start()
    for _ in range(30):
        clock.t += 1
        assert abs(rest.window()["hr_delta"]) <= 5
        assert ex.window()["hr_delta"] >= 15


def test_manual_interpolation_midpoint_and_delta():
    m = ManualBio()
    m.set_baseline(70)
    m.set_start(70, 98, seconds=30)
    m.set_end(100, 96)
    w = m.window_for(0, 30)
    assert w["hr"] == 85 and w["spo2"] == 97 and w["hr_delta"] == 15
    assert w["source"] == "manual" and w["quality"] == 1.0
    assert m.window_for(0, 3)["hr"] == 72          # midpoint t=1.5 -> 71.5 -> 72
    assert m.value_at(30) == (100.0, 96.0)
    assert len(m.per_second()) == 30 and m.per_second()[0]["hr"] == 70


def test_manual_without_readings_is_empty():
    m = ManualBio()
    assert m.window()["hr"] is None
    with pytest.raises(RuntimeError):
        m.window_for(0, 3)


def test_make_bio_source_types(tmp_path):
    assert isinstance(make_bio_source("replay:rest", None), ReplayBio)
    assert isinstance(make_bio_source("replay:exertion", None), ReplayBio)
    assert isinstance(make_bio_source("manual", None), ManualBio)
    from node.bio.live import LiveBio
    assert isinstance(make_bio_source("live", None, params={"red_code": 8, "ir_code": 15, "finger_ir_min": 1}),
                      LiveBio)
    with pytest.raises(ValueError):
        make_bio_source("replay:other", None)
    with pytest.raises(ValueError):
        make_bio_source("bogus", None)


def test_live_start_without_sensor_raises_bio_unavailable():
    bio = make_bio_source("live", None)
    with pytest.raises(BioUnavailable):
        bio.start()   # laptop: no smbus2 / no I2C device
