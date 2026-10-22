"""ReplayBio: plays ml/replay/{name}.csv (t_s,hr,spo2; one row per second) in real time, looping."""

import csv
import json
from pathlib import Path
import time

from node.bio import BioSource, BioUnavailable

REPO_ROOT = Path(__file__).resolve().parents[2]
REPLAY_DIR = REPO_ROOT / "ml" / "replay"
WINDOW_SECONDS = 3


def load_replay(name: str, replay_dir=None) -> tuple[list[tuple[int, int]], dict]:
    replay_dir = Path(replay_dir) if replay_dir else REPLAY_DIR
    csv_path, json_path = replay_dir / f"{name}.csv", replay_dir / f"{name}.json"
    for path in (csv_path, json_path):
        if not path.exists():
            raise BioUnavailable(f"replay file ml/replay/{path.name} not found")
    with json_path.open(encoding="utf-8") as fh:
        meta = json.load(fh)
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for i, r in enumerate(csv.DictReader(fh)):
            try:
                t, hr, spo2 = int(r["t_s"]), int(r["hr"]), int(r["spo2"])
            except (KeyError, TypeError, ValueError) as e:
                raise BioUnavailable(f"{csv_path.name} row {i + 1}: needs integer t_s,hr,spo2 ({e})") from e
            if t != i:
                raise BioUnavailable(f"{csv_path.name}: t_s must be 0,1,2,... without gaps (row {i + 1} has {t})")
            rows.append((hr, spo2))
    if not rows:
        raise BioUnavailable(f"{csv_path.name} has no rows")
    if not isinstance(meta.get("baseline_hr"), int):
        raise BioUnavailable(f"{json_path.name}: baseline_hr must be an integer")
    return rows, meta


class ReplayBio(BioSource):
    kind = "replay"

    def __init__(self, name: str, replay_dir=None, clock=time.monotonic):
        self.name = name
        self.rows, self.meta = load_replay(name, replay_dir)
        self._clock = clock
        self._t0 = None

    def start(self) -> None:
        self._t0 = self._clock()

    def restart(self) -> None:
        self.start()

    def position(self) -> int:
        if self._t0 is None:
            self.start()
        return int(self._clock() - self._t0) % len(self.rows)

    def window(self) -> dict:
        pos, n = self.position(), len(self.rows)
        rows = [self.rows[(pos - k) % n] for k in range(WINDOW_SECONDS - 1, -1, -1)]
        hr = int(round(sum(r[0] for r in rows) / len(rows)))
        spo2 = int(round(sum(r[1] for r in rows) / len(rows)))
        return {"hr": hr, "spo2": spo2, "hr_delta": hr - self.baseline_hr(), "finger": True,
                "source": "replay", "quality": 1.0}

    def baseline_hr(self) -> int:
        return int(self.meta["baseline_hr"])

    def stop(self) -> None:
        self._t0 = None
