"""Per-window CSV run log: ~/icu-data/logs/run_YYYYMMDD.csv. Numbers only; no images."""

import csv
from datetime import datetime
import logging
from pathlib import Path

log = logging.getLogger("node.runlog")

COLUMNS = ["ts", "level", "p_routine", "p_urgent", "p_critical", "gesture_conf", "tremor", "hr", "hr_delta",
           "spo2", "bio_mode", "bio_source", "hand_present", "n_frames", "fps", "fusion_mode", "alert_published"]


class RunLog:
    def __init__(self, log_dir):
        self.log_dir = Path(log_dir).expanduser()
        self._warned = False

    def path(self) -> Path:
        return self.log_dir / f"run_{datetime.now():%Y%m%d}.csv"

    def write(self, row: dict) -> None:
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.path()
            new = not path.exists()
            with path.open("a", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
                if new:
                    w.writeheader()
                w.writerow({k: (int(v) if isinstance(v, bool) else v) for k, v in row.items()})
        except OSError as e:
            if not self._warned:
                log.warning("run log not writable (%s); continuing without it", e)
                self._warned = True
