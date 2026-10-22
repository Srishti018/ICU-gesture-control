"""Local-time ISO helpers. Format everywhere: YYYY-MM-DDTHH:MM:SS (no timezone)."""

from datetime import datetime

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def now_local_iso() -> str:
    return datetime.now().strftime(ISO_FORMAT)


def parse_local_iso(s: str) -> datetime:
    return datetime.strptime(s, ISO_FORMAT)


def seconds_between(a: str, b: str) -> float:
    """Seconds from timestamp a to timestamp b (positive when b is later)."""
    return (parse_local_iso(b) - parse_local_iso(a)).total_seconds()
