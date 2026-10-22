"""Flask API for alert history, node state and stats.

Run from the repo root:  .venv/bin/python -m server.app
"""

import json
import logging

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from server import config, db
from server.mqtt_worker import MqttWorker
from server.timeutil import now_local_iso, seconds_between

log = logging.getLogger("server")

FLATTENED_FIELDS = ("hr", "spo2", "hr_delta", "gesture_conf", "tremor", "bio_source", "p")


def _limit_arg(default: int = 50, maximum: int = 500) -> int:
    raw = request.args.get("limit", default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer")
    if value < 1:
        raise ValueError("limit must be at least 1")
    return min(value, maximum)


def _loads(text: str | None) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def alert_to_dict(row) -> dict:
    payload = _loads(row["payload_json"])
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    out = {
        "id": row["id"],
        "node": row["node"],
        "level": row["level"],
        "alert_ts": row["alert_ts"],
        "received_at": row["received_at"],
        "ack_ts": row["ack_ts"],
        "ack_received_at": row["ack_received_at"],
        "response_s": row["response_s"],
    }
    for field in FLATTENED_FIELDS:
        out[field] = payload.get(field, features.get(field))
    return out


def node_to_dict(row, now: str) -> dict:
    hb = row["last_heartbeat_at"]
    return {
        "node": row["node"],
        "online": None if row["online"] is None else bool(row["online"]),
        "online_changed_at": row["online_changed_at"],
        "last_heartbeat_at": hb,
        "heartbeat_age_s": round(seconds_between(hb, now), 1) if hb else None,
        "last_status": _loads(row["last_status_json"]) or None,
        "last_status_at": row["last_status_at"],
    }


def create_app(start_mqtt: bool = True, db_path: str | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app, origins=config.CORS_ORIGINS)
    db.init_db(db_path)

    worker = None
    if start_mqtt:
        worker = MqttWorker()
        worker.start()
    app.extensions["mqtt_worker"] = worker

    @app.errorhandler(ValueError)
    def bad_request(e):
        return jsonify({"error": str(e)}), 400

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify({"error": e.description}), e.code

    @app.errorhandler(Exception)
    def server_error(e):
        log.exception("unhandled error")
        return jsonify({"error": "internal server error"}), 500

    @app.get("/api/health")
    def health():
        db_ok = db.check()
        return jsonify({
            "ok": db_ok,
            "mqtt_connected": bool(worker and worker.connected),
            "db": "ok" if db_ok else "error",
            "server_time": now_local_iso(),
        })

    @app.get("/api/alerts")
    def alerts():
        limit = _limit_arg()
        node = request.args.get("node") or None
        return jsonify({"alerts": [alert_to_dict(r) for r in db.list_alerts(limit, node)]})

    @app.get("/api/nodes")
    def nodes():
        now = now_local_iso()
        return jsonify({"nodes": [node_to_dict(r, now) for r in db.list_nodes()]})

    @app.get("/api/stats")
    def stats():
        return jsonify(db.stats())

    @app.get("/api/events")
    def events():
        limit = _limit_arg()
        return jsonify({"events": [dict(r) for r in db.list_events(limit)]})

    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    log.info("database: %s", config.DB_PATH)
    app = create_app(start_mqtt=True)
    log.info("API on http://0.0.0.0:%d", config.API_PORT)
    # use_reloader=False is required: the reloader would start a second MQTT
    # client with the same client ID and the two would kick each other off.
    app.run(host="0.0.0.0", port=config.API_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
