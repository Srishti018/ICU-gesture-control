"""Writes the collector's files: per-trial windows/bio CSV + meta JSON, baseline, session log.

Plain Python only (runs on the Pi).
"""

import csv
from datetime import datetime
import json
from pathlib import Path
import subprocess

from ml.schema import BIO_COLUMNS, WINDOW_COLUMNS

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = Path.home() / "icu-data" / "raw"


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def base_name(person: str, scenario: str, trial, when: datetime | None = None) -> str:
    when = when or datetime.now()
    t = f"T{trial}" if isinstance(trial, int) else str(trial)
    return f"{person}_{scenario}_{t}_{when:%Y%m%d-%H%M%S}"


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _cell(v):
    if isinstance(v, bool):
        return int(v)
    return "" if v is None else v


def write_windows(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=WINDOW_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: _cell(r.get(c)) for c in WINDOW_COLUMNS})


def write_bio(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=BIO_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: _cell(r.get(c)) for c in BIO_COLUMNS})


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def mark_discarded(out_dir: Path, base: str) -> None:
    """A redone trial: set discarded in its meta and in every row of its windows CSV."""
    meta_path = out_dir / f"{base}_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["discarded"] = True
    write_json(meta_path, meta)
    win_path = out_dir / f"{base}_windows.csv"
    with win_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        r["discarded"] = 1
    write_windows(win_path, rows)


def completed_trials(out_dir: Path, person: str) -> set[tuple[str, int]]:
    """(scenario, trial) pairs already recorded and not discarded (for --resume)."""
    done = set()
    for p in out_dir.glob(f"{person}_*_meta.json"):
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not meta.get("discarded") and isinstance(meta.get("trial"), int):
            done.add((meta["scenario"], meta["trial"]))
    return done


class SessionLog:
    """{person}_session_log.txt: every prompt and answer with a timestamp."""

    def __init__(self, path: Path):
        self.path = path

    def write(self, kind: str, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            for line in str(text).splitlines() or [""]:
                fh.write(f"{now_iso()} {kind}: {line}\n")
