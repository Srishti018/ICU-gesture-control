"""Unit tests for the MQTT handlers and HTTP API. No broker needed."""

import json
import sqlite3
from unittest.mock import MagicMock

import pytest

from server import db, mqtt_worker
from server.app import create_app


def status(level="routine", node="bed1", ts="2026-10-25T10:02:11", bio_source="live"):
    return json.dumps({
        "node": node, "ts": ts, "level": level,
        "p": {"routine": 0.04, "urgent": 0.11, "critical": 0.85},
        "features": {"gesture_conf": 0.91, "tremor": 0.01, "hr_delta": 24, "spo2": 98},
        "hr": 99, "bio_source": bio_source,
    }).encode()


def ack(node="bed1", level="critical"):
    return json.dumps({
        "node": node, "level": level, "alert_ts": "2026-10-25T10:02:11",
        "ack_ts": "2026-10-25T10:02:19", "by": "dashboard",
    }).encode()


@pytest.fixture
def tmp_db(tmp_path):
    path = tmp_path / "test.db"
    db.init_db(str(path))
    return path


def rows(path, sql):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def send(topic, payload, publish=None, retain=False):
    mqtt_worker.dispatch(topic, payload, retain, publish or MagicMock())


def test_routine_updates_node_state_and_inserts_no_alert(tmp_db):
    send("icu/bed1/status/routine", status("routine"))
    state = rows(tmp_db, "SELECT * FROM node_state")
    assert len(state) == 1
    assert state[0]["node"] == "bed1"
    assert json.loads(state[0]["last_status_json"])["level"] == "routine"
    assert state[0]["last_status_at"] is not None
    assert rows(tmp_db, "SELECT * FROM alerts") == []


def test_urgent_inserts_once(tmp_db):
    send("icu/bed1/status/urgent", status("urgent"))
    send("icu/bed1/status/urgent", status("urgent"), retain=True)
    alerts = rows(tmp_db, "SELECT * FROM alerts")
    assert len(alerts) == 1
    assert alerts[0]["level"] == "urgent"
    assert alerts[0]["alert_ts"] == "2026-10-25T10:02:11"
    assert alerts[0]["ack_ts"] is None


@pytest.mark.parametrize("suffix", ["status/routine", "status/urgent", "status/critical", "heartbeat", "online", "ack"])
def test_empty_payload_ignored(tmp_db, suffix):
    publish = MagicMock()
    send(f"icu/bed1/{suffix}", b"", publish=publish, retain=True)
    assert rows(tmp_db, "SELECT * FROM alerts") == []
    assert rows(tmp_db, "SELECT * FROM node_state") == []
    assert rows(tmp_db, "SELECT * FROM connection_events") == []
    publish.assert_not_called()


@pytest.mark.parametrize("suffix", ["status/routine", "status/urgent", "status/critical", "ack"])
def test_invalid_json_ignored(tmp_db, suffix):
    publish = MagicMock()
    send(f"icu/bed1/{suffix}", b"{not json", publish=publish)
    assert rows(tmp_db, "SELECT * FROM alerts") == []
    assert rows(tmp_db, "SELECT * FROM node_state") == []
    publish.assert_not_called()


def test_online_offline_offline_creates_two_events(tmp_db):
    send("icu/bed1/online", b"online")
    send("icu/bed1/online", b"offline")
    send("icu/bed1/online", b"offline")
    events = rows(tmp_db, "SELECT state FROM connection_events ORDER BY id")
    assert [e["state"] for e in events] == ["online", "offline"]
    assert rows(tmp_db, "SELECT online FROM node_state")[0]["online"] == 0


def test_payload_node_mismatch_uses_topic(tmp_db):
    send("icu/bed2/status/critical", status("critical", node="bed1"))
    alerts = rows(tmp_db, "SELECT * FROM alerts")
    assert alerts[0]["node"] == "bed2"


def test_ack_with_two_open_alerts(tmp_db):
    send("icu/bed1/status/urgent", status("urgent", ts="2026-10-25T10:02:00"))
    send("icu/bed1/status/critical", status("critical", ts="2026-10-25T10:02:03"))
    send("icu/bed2/status/urgent", status("urgent", node="bed2"))
    publish = MagicMock()
    send("icu/bed1/ack", ack(), publish=publish)

    bed1 = rows(tmp_db, "SELECT * FROM alerts WHERE node = 'bed1'")
    assert len(bed1) == 2
    for a in bed1:
        assert a["ack_ts"] == "2026-10-25T10:02:19"
        assert a["ack_received_at"] is not None
        assert a["response_s"] is not None and a["response_s"] >= 0
    bed2 = rows(tmp_db, "SELECT * FROM alerts WHERE node = 'bed2'")
    assert bed2[0]["ack_ts"] is None

    assert publish.call_count == 2
    topics = set()
    for call in publish.call_args_list:
        topic, payload = call.args
        assert payload == b""
        assert call.kwargs == {"qos": 1, "retain": True}
        topics.add(topic)
    assert topics == {"icu/bed1/status/urgent", "icu/bed1/status/critical"}


def test_ack_with_no_open_alerts_still_clears(tmp_db):
    publish = MagicMock()
    send("icu/bed1/ack", ack(), publish=publish)
    assert publish.call_count == 2
    assert {c.args[0] for c in publish.call_args_list} == {"icu/bed1/status/urgent", "icu/bed1/status/critical"}


def test_ack_without_ack_ts_falls_back_to_now(tmp_db):
    send("icu/bed1/status/critical", status("critical"))
    send("icu/bed1/ack", json.dumps({"node": "bed1", "level": "critical"}).encode())
    a = rows(tmp_db, "SELECT * FROM alerts")[0]
    assert a["ack_ts"] == a["ack_received_at"]


# --- HTTP API -----------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    app = create_app(start_mqtt=False, db_path=str(tmp_path / "api.db"))
    return app.test_client()


def test_api_alerts_shape(client):
    send("icu/bed1/status/critical", status("critical", bio_source="replay"))
    send("icu/bed1/ack", ack())
    body = client.get("/api/alerts?limit=50&node=bed1").get_json()
    assert len(body["alerts"]) == 1
    a = body["alerts"][0]
    assert set(a) == {
        "id", "node", "level", "alert_ts", "received_at", "ack_ts", "ack_received_at",
        "response_s", "hr", "spo2", "hr_delta", "gesture_conf", "tremor", "bio_source", "p",
    }
    assert a["node"] == "bed1" and a["level"] == "critical"
    assert a["hr"] == 99 and a["spo2"] == 98 and a["hr_delta"] == 24
    assert a["gesture_conf"] == 0.91 and a["tremor"] == 0.01
    assert a["bio_source"] == "replay"
    assert a["p"] == {"routine": 0.04, "urgent": 0.11, "critical": 0.85}
    assert a["response_s"] >= 0
    assert client.get("/api/alerts?node=bed2").get_json() == {"alerts": []}


def test_api_alerts_newest_first_and_limit(client):
    for i in range(3):
        send("icu/bed1/status/urgent", status("urgent", ts=f"2026-10-25T10:02:0{i}"))
    alerts = client.get("/api/alerts?limit=2").get_json()["alerts"]
    assert len(alerts) == 2
    assert alerts[0]["id"] > alerts[1]["id"]


def test_api_alerts_bad_limit(client):
    resp = client.get("/api/alerts?limit=abc")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_api_stats_shape(client):
    empty = client.get("/api/stats").get_json()
    assert empty == {
        "total_alerts": 0, "open_alerts": 0,
        "by_level": {
            "urgent": {"count": 0, "acknowledged": 0, "mean_response_s": None, "max_response_s": None},
            "critical": {"count": 0, "acknowledged": 0, "mean_response_s": None, "max_response_s": None},
        },
        "offline_events": 0,
    }
    send("icu/bed1/status/urgent", status("urgent"))
    send("icu/bed1/ack", ack())
    send("icu/bed1/status/critical", status("critical"))
    send("icu/bed1/online", b"online")
    send("icu/bed1/online", b"offline")
    s = client.get("/api/stats").get_json()
    assert s["total_alerts"] == 2
    assert s["open_alerts"] == 1
    assert s["by_level"]["urgent"]["count"] == 1
    assert s["by_level"]["urgent"]["acknowledged"] == 1
    assert s["by_level"]["urgent"]["mean_response_s"] is not None
    assert s["by_level"]["critical"]["acknowledged"] == 0
    assert s["by_level"]["critical"]["mean_response_s"] is None
    assert s["offline_events"] == 1


def test_api_health_nodes_events(client):
    h = client.get("/api/health").get_json()
    assert h["ok"] is True and h["db"] == "ok" and h["mqtt_connected"] is False
    send("icu/bed1/online", b"online")
    send("icu/bed1/heartbeat", json.dumps({"node": "bed1", "ts": "x", "uptime_s": 1}).encode())
    send("icu/bed1/status/routine", status("routine"))
    n = client.get("/api/nodes").get_json()["nodes"][0]
    assert n["node"] == "bed1" and n["online"] is True
    assert 0 <= n["heartbeat_age_s"] < 5
    assert n["last_status"]["level"] == "routine"
    ev = client.get("/api/events").get_json()["events"]
    assert ev == [{"node": "bed1", "state": "online", "at": ev[0]["at"]}]
