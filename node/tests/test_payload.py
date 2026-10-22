import json
import random
import re

import pytest

from node.payload import heartbeat_payload, level_of, now_ts, round_probs, status_payload

TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


def test_status_payload_matches_contract():
    p = status_payload("bed1", "critical", {"routine": 0.041, "urgent": 0.112, "critical": 0.847},
                       {"gesture_conf": 0.91234, "tremor": 0.0104, "hr_delta": 24.4, "spo2": 98.2}, 99.3, "replay")
    assert list(p) == ["node", "ts", "level", "p", "features", "hr", "bio_source"]
    assert p["node"] == "bed1" and p["level"] == "critical" and p["bio_source"] == "replay"
    assert TS.match(p["ts"])
    assert list(p["p"]) == ["routine", "urgent", "critical"]
    assert list(p["features"]) == ["gesture_conf", "tremor", "hr_delta", "spo2"]
    f = p["features"]
    assert f == {"gesture_conf": 0.912, "tremor": 0.01, "hr_delta": 24, "spo2": 98}
    assert type(f["hr_delta"]) is int and type(f["spo2"]) is int and type(p["hr"]) is int
    assert isinstance(f["gesture_conf"], float) and isinstance(f["tremor"], float)
    assert p["hr"] == 99
    json.dumps(p)


def test_status_payload_rejects_bad_values():
    feats = {"gesture_conf": 0.1, "tremor": 0.01, "hr_delta": 0, "spo2": 98}
    with pytest.raises(ValueError):
        status_payload("bed1", "panic", {"routine": 1, "urgent": 0, "critical": 0}, feats, 75, "live")
    with pytest.raises(ValueError):
        status_payload("bed1", "routine", {"routine": 1, "urgent": 0, "critical": 0}, feats, 75, "manual")


def test_round_probs_sums_to_exactly_one():
    rng = random.Random(0)
    for _ in range(1000):
        raw = [rng.random() for _ in range(3)]
        total = sum(raw)
        p = round_probs(dict(zip(["routine", "urgent", "critical"], [v / total for v in raw])))
        assert list(p) == ["routine", "urgent", "critical"]
        assert round(sum(p.values()), 10) == 1.0
        assert all(round(v, 2) == v and 0 <= v <= 1 for v in p.values())


def test_round_probs_keeps_the_winner():
    p = round_probs({"routine": 0.334, "urgent": 0.333, "critical": 0.333})
    assert level_of(p) == "routine" and sum(p.values()) == pytest.approx(1.0)


def test_heartbeat_payload():
    hb = heartbeat_payload("bed1", 312.7)
    assert list(hb) == ["node", "ts", "uptime_s"] and hb["uptime_s"] == 312 and TS.match(hb["ts"])
    assert TS.match(now_ts())
