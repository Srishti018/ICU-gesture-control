"""SQLite storage for alerts, node state and connection events.

Every call opens its own connection, so the MQTT thread and Flask request
threads never share one. Writes are serialised with a module-level lock.
"""

from contextlib import contextmanager
import sqlite3
import threading

from server import config
from server.timeutil import seconds_between

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  node             TEXT NOT NULL,
  level            TEXT NOT NULL CHECK (level IN ('urgent','critical')),
  alert_ts         TEXT NOT NULL,
  received_at      TEXT NOT NULL,
  payload_json     TEXT NOT NULL,
  ack_ts           TEXT,
  ack_received_at  TEXT,
  response_s       REAL,
  UNIQUE (node, level, alert_ts)
);

CREATE TABLE IF NOT EXISTS node_state (
  node              TEXT PRIMARY KEY,
  online            INTEGER,
  online_changed_at TEXT,
  last_heartbeat_at TEXT,
  last_status_json  TEXT,
  last_status_at    TEXT,
  updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS connection_events (
  id     INTEGER PRIMARY KEY AUTOINCREMENT,
  node   TEXT NOT NULL,
  state  TEXT NOT NULL CHECK (state IN ('online','offline')),
  at     TEXT NOT NULL
);
"""

lock = threading.Lock()
_db_path = config.DB_PATH


def init_db(path: str | None = None) -> None:
    """Set the database file (default config.DB_PATH) and create the tables."""
    global _db_path
    if path is not None:
        _db_path = str(path)
    with lock, session() as conn:
        conn.executescript(SCHEMA)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def session():
    """A connection that commits on success, rolls back on error, and always closes."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def check() -> bool:
    try:
        with session() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


# --- writes (called from the MQTT worker) -----------------------------------

def upsert_status(node: str, status_json: str, now: str) -> None:
    with lock, session() as conn:
        conn.execute(
            """INSERT INTO node_state (node, last_status_json, last_status_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(node) DO UPDATE SET
                 last_status_json = excluded.last_status_json,
                 last_status_at = excluded.last_status_at,
                 updated_at = excluded.updated_at""",
            (node, status_json, now, now),
        )


def upsert_heartbeat(node: str, now: str) -> None:
    with lock, session() as conn:
        conn.execute(
            """INSERT INTO node_state (node, last_heartbeat_at, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(node) DO UPDATE SET
                 last_heartbeat_at = excluded.last_heartbeat_at,
                 updated_at = excluded.updated_at""",
            (node, now, now),
        )


def set_online(node: str, online: bool, now: str) -> bool:
    """Store the online flag. Returns True (and logs an event) if it changed."""
    value = 1 if online else 0
    with lock, session() as conn:
        row = conn.execute("SELECT online FROM node_state WHERE node = ?", (node,)).fetchone()
        changed = row is None or row["online"] != value
        if changed:
            conn.execute(
                """INSERT INTO node_state (node, online, online_changed_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(node) DO UPDATE SET
                     online = excluded.online,
                     online_changed_at = excluded.online_changed_at,
                     updated_at = excluded.updated_at""",
                (node, value, now, now),
            )
            conn.execute(
                "INSERT INTO connection_events (node, state, at) VALUES (?, ?, ?)",
                (node, "online" if online else "offline", now),
            )
        else:
            conn.execute("UPDATE node_state SET updated_at = ? WHERE node = ?", (now, node))
        return changed


def insert_alert(node: str, level: str, alert_ts: str, received_at: str, payload_json: str) -> bool:
    """Insert an alert once. Returns True only if a new row was created."""
    with lock, session() as conn:
        cur = conn.execute(
            """INSERT OR IGNORE INTO alerts (node, level, alert_ts, received_at, payload_json)
               VALUES (?, ?, ?, ?, ?)""",
            (node, level, alert_ts, received_at, payload_json),
        )
        return cur.rowcount == 1


def ack_open_alerts(node: str, ack_ts: str, ack_received_at: str) -> int:
    """Acknowledge every open alert for a node. Returns the number acknowledged."""
    with lock, session() as conn:
        rows = conn.execute(
            "SELECT id, received_at FROM alerts WHERE node = ? AND ack_ts IS NULL", (node,)
        ).fetchall()
        for row in rows:
            response_s = round(max(0.0, seconds_between(row["received_at"], ack_received_at)), 1)
            conn.execute(
                "UPDATE alerts SET ack_ts = ?, ack_received_at = ?, response_s = ? WHERE id = ?",
                (ack_ts, ack_received_at, response_s, row["id"]),
            )
        return len(rows)


# --- reads (called from Flask routes) ---------------------------------------

def list_alerts(limit: int, node: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM alerts"
    params: list = []
    if node:
        sql += " WHERE node = ?"
        params.append(node)
    sql += " ORDER BY received_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with session() as conn:
        return conn.execute(sql, params).fetchall()


def list_nodes() -> list[sqlite3.Row]:
    with session() as conn:
        return conn.execute("SELECT * FROM node_state ORDER BY node").fetchall()


def list_events(limit: int) -> list[sqlite3.Row]:
    with session() as conn:
        return conn.execute(
            "SELECT node, state, at FROM connection_events ORDER BY at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()


def stats() -> dict:
    with session() as conn:
        total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        open_ = conn.execute("SELECT COUNT(*) FROM alerts WHERE ack_ts IS NULL").fetchone()[0]
        by_level = {}
        for level in ("urgent", "critical"):
            row = conn.execute(
                """SELECT COUNT(*) AS count,
                          COUNT(ack_ts) AS acknowledged,
                          AVG(response_s) AS mean_response_s,
                          MAX(response_s) AS max_response_s
                   FROM alerts WHERE level = ?""",
                (level,),
            ).fetchone()
            mean = row["mean_response_s"]
            by_level[level] = {
                "count": row["count"],
                "acknowledged": row["acknowledged"],
                "mean_response_s": round(mean, 1) if mean is not None else None,
                "max_response_s": row["max_response_s"],
            }
        offline = conn.execute(
            "SELECT COUNT(*) FROM connection_events WHERE state = 'offline'"
        ).fetchone()[0]
    return {"total_alerts": total, "open_alerts": open_, "by_level": by_level, "offline_events": offline}
