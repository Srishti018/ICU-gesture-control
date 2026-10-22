"""Contract payloads (docs/contracts.md), level ranks and probability rounding."""

from datetime import datetime

LEVELS = ("routine", "urgent", "critical")
RANK = {"routine": 0, "urgent": 1, "critical": 2}
BIO_SOURCES = ("live", "replay")


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def round_probs(p: dict) -> dict:
    """Round to 2 decimals and give the rounding error to the largest, so the sum is exactly 1.00."""
    rounded = {lv: round(float(p[lv]), 2) for lv in LEVELS}
    top = max(LEVELS, key=lambda lv: rounded[lv])
    rounded[top] = round(rounded[top] + (1.0 - sum(rounded.values())), 2)
    return {lv: rounded[lv] for lv in LEVELS}


def level_of(p: dict) -> str:
    return max(LEVELS, key=lambda lv: p[lv])


def should_publish_alert(prev_level: str, level: str) -> bool:
    """Alerts go out only when the level rises (the first window's prev_level is routine)."""
    return RANK[level] > RANK[prev_level]


def status_payload(node: str, level: str, p: dict, features: dict, hr, bio_source: str) -> dict:
    if level not in RANK:
        raise ValueError(f"unknown level {level!r}")
    if bio_source not in BIO_SOURCES:
        raise ValueError(f"bio_source must be live or replay, got {bio_source!r}")
    return {
        "node": node,
        "ts": now_ts(),
        "level": level,
        "p": round_probs(p),
        "features": {
            "gesture_conf": round(float(features["gesture_conf"]), 3),
            "tremor": round(float(features["tremor"]), 3),
            "hr_delta": int(round(features["hr_delta"])),
            "spo2": int(round(features["spo2"])),
        },
        "hr": int(round(hr)),
        "bio_source": bio_source,
    }


def heartbeat_payload(node: str, uptime_s: float) -> dict:
    return {"node": node, "ts": now_ts(), "uptime_s": int(uptime_s)}
