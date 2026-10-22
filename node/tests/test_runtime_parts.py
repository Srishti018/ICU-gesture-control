"""Settings, hardware lock, fusion fallback, control keys, run log and the node's window step."""

import csv
import io
import json

import pytest

from node import hwlock
from node.control import Control
from node.fusion_adapter import RuleFusion, load_fusion
from node.runlog import COLUMNS, RunLog
from node.settings import Settings, SettingsError


def write_env(tmp_path, text):
    p = tmp_path / ".env"
    p.write_text(text)
    return p


def test_settings_from_env_and_overrides(tmp_path, monkeypatch):
    for k in ("BROKER_HOST", "BROKER_PORT", "NODE_ID", "NODE_USER", "NODE_PASS", "BED2_PASS"):
        monkeypatch.delenv(k, raising=False)
    env = write_env(tmp_path, "BROKER_HOST=10.0.0.5\nBROKER_PORT=1884\nNODE_USER=bed1\nNODE_PASS=p1\nBED2_PASS=p2\n")
    s = Settings.load(env)
    assert (s.broker_host, s.broker_port, s.node_id, s.node_user, s.node_pass) == ("10.0.0.5", 1884, "bed1", "bed1", "p1")
    s2 = Settings.load(env, node_id="bed2", broker_host="localhost")
    assert (s2.node_id, s2.node_user, s2.node_pass, s2.broker_host) == ("bed2", "bed2", "p2", "localhost")
    assert "p1" not in repr(s) and "p2" not in repr(s2)


def test_settings_check_broker(tmp_path, monkeypatch):
    for k in ("BROKER_HOST", "NODE_PASS"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SettingsError, match="BROKER_HOST"):
        Settings.load(write_env(tmp_path, "BROKER_HOST=CHANGE_ME\nNODE_PASS=x\n")).check_broker()
    with pytest.raises(SettingsError, match="password"):
        Settings.load(write_env(tmp_path, "BROKER_HOST=1.2.3.4\nNODE_PASS=\n")).check_broker()


def test_hardware_lock_busy_message(tmp_path):
    path = str(tmp_path / "lock")
    with hwlock.HardwareLock("node.main", path=path):
        with pytest.raises(hwlock.HardwareBusy) as e:
            with hwlock.HardwareLock("fps_test", path=path):
                pass
    assert str(e.value).startswith("HARDWARE BUSY: node.main (pid ") and "camera/sensors" in str(e.value)
    with hwlock.HardwareLock("again", path=path):
        pass
    assert hwlock.EXIT_BUSY == 3


def test_bio_tools_use_role_a_lock():
    from node.bio import hwlock_compat
    assert hwlock_compat.USING_ROLE_A_LOCK and hwlock_compat.HardwareLock is hwlock.HardwareLock


def test_rule_fusion_matches_baseline():
    r = RuleFusion()
    f = lambda g, d: {"gesture_conf": g, "tremor": 0.01, "hr_delta": d, "spo2": 98}  # noqa: E731
    assert r.predict_proba(f(0.79, 30)) == {"routine": 0.90, "urgent": 0.05, "critical": 0.05}
    assert max(r.predict_proba(f(0.80, 14)).items(), key=lambda kv: kv[1])[0] == "urgent"
    assert max(r.predict_proba(f(0.80, 15)).items(), key=lambda kv: kv[1])[0] == "critical"


def test_model_missing_falls_back_to_rule(tmp_path, caplog):
    s = Settings(model_path=tmp_path / "missing.json")
    assert load_fusion(s, "model").mode == "rule"
    assert "MODEL NOT FOUND" in caplog.text
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"features": ["x"], "classes": []}))
    assert load_fusion(Settings(model_path=bad), "model").mode == "rule"


def test_control_dispatch_and_help(capsys):
    seen = []
    c = Control({"r": lambda: seen.append("r"), "q": lambda: seen.append("q")}, stream=io.StringIO("r\n\nzz\nQ\n"))
    c._run()
    assert seen == ["r", "q"]
    assert "Keys" in capsys.readouterr().out


def test_runlog_writes_header_once(tmp_path):
    rl = RunLog(tmp_path)
    rl.write({"ts": "t1", "level": "routine", "alert_published": False})
    rl.write({"ts": "t2", "level": "urgent", "alert_published": True})
    with rl.path().open() as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == COLUMNS and [r["alert_published"] for r in rows] == ["0", "1"]


# --- the node's window step, with fakes --------------------------------------------------------------

class FakePub:
    connected = True

    def __init__(self):
        self.status, self.alerts = [], []

    def publish_status(self, p):
        self.status.append(p)

    def publish_alert(self, level, p):
        self.alerts.append((level, p))


class FakeBio:
    kind = "replay"

    def __init__(self, windows, baseline=74):
        self.windows, self.baseline = list(windows), baseline

    def window(self):
        return self.windows.pop(0) if len(self.windows) > 1 else self.windows[0]

    def baseline_hr(self):
        return self.baseline


def make_node(tmp_path, bio):
    from node.main import Node, parse_args
    from node.vision.synthetic import SyntheticVision
    args = parse_args(["--vision", "synthetic", "--fusion", "rule", "--no-oled", "--no-buzzer"])
    node = Node(args, Settings(log_dir=tmp_path))
    node.pub, node.vision, node.bio, node.fusion = FakePub(), SyntheticVision(seed=1), bio, RuleFusion()
    return node


def bio_w(hr, delta, spo2=98):
    return {"hr": hr, "spo2": spo2, "hr_delta": delta, "finger": True, "source": "replay", "quality": 1.0}


def test_step_publishes_alert_once_per_rise(tmp_path):
    node = make_node(tmp_path, FakeBio([bio_w(75, 1)]))
    node.step()
    node.vision.set_gesture(True)
    node.step()
    node.step()
    node.bio = FakeBio([bio_w(100, 26)])
    node.bio_mode = "replay:exertion"
    node.step()
    node.step()
    assert [p["level"] for p in node.pub.status] == ["routine", "urgent", "urgent", "critical", "critical"]
    assert [lv for lv, _ in node.pub.alerts] == ["urgent", "critical"]
    assert all(p["bio_source"] == "replay" for p in node.pub.status)
    assert sum(node.pub.status[-1]["p"].values()) == pytest.approx(1.0)
    with RunLog(tmp_path).path().open() as fh:
        assert [r["alert_published"] for r in csv.DictReader(fh)] == ["0", "1", "0", "1", "0"]


def test_bio_missing_reuses_then_falls_back(tmp_path, caplog):
    missing = {"hr": None, "spo2": None, "hr_delta": None, "finger": False, "source": "live", "quality": 0.0}
    node = make_node(tmp_path, FakeBio([bio_w(80, 6, 97), missing], baseline=70))
    node.bio_mode = "live"
    node.step()
    node.step()                                  # within 10 s: reuses the last valid window
    assert node.pub.status[-1]["hr"] == 80 and node.pub.status[-1]["bio_source"] == "live"
    node.last_bio = (node.last_bio[0] - 11, node.last_bio[1])
    node.step()                                  # older than 10 s: baseline, delta 0, last SpO2
    last = node.pub.status[-1]
    assert last["hr"] == 70 and last["features"]["hr_delta"] == 0 and last["features"]["spo2"] == 97
    assert "BIO MISSING" in caplog.text
