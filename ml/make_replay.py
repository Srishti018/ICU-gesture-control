"""Build the demo replay files ml/replay/{rest,exertion}.{csv,json} from BIDMC ICU vitals.

Usage: python -I ml/make_replay.py <folder with bidmc_##_Numerics.csv> [--out ml/replay]

Segments are chosen by fixed rules, checked on EVERY second (not on window means):
  rest      60 s, NEWS2-normal throughout: SpO2 >= 96 and 51 <= HR <= 90.
            Among all such segments: mean HR closest to 75 (so hr_delta ~ 0), then lowest HR
            standard deviation, then lowest record number and earliest start.
  exertion  90 s, NEWS2-abnormal throughout: SpO2 <= 93 or HR >= 111 (and HR > 50).
            Preferred: segments where BOTH HR >= 111 and SpO2 <= 93 hold every second, so the
            fixed rule fallback (hr_delta >= 15) also sees them as raised; then lowest HR standard
            deviation, lowest record number, earliest start. If none exists, any abnormal segment.
baseline_hr = 75 (adult resting reference; hr_delta = HR - 75, as in the training data).
"""

import argparse
import csv
import json
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

BASELINE_HR = 75
CITATION = ("Pimentel, M. A. F., et al. (2016). Toward a robust estimation of respiratory rate from pulse "
            "oximeters. IEEE Transactions on Biomedical Engineering, 64(8), 1914-1923. doi:10.1109/TBME.2016.2613124")
SOURCE_URL = "https://physionet.org/content/bidmc/1.0.0/"


def load_records(folder) -> dict:
    records = {}
    for f in sorted(Path(folder).glob("bidmc_*_Numerics.csv")):
        d = pd.read_csv(f, skipinitialspace=True)
        d.columns = [c.strip() for c in d.columns]
        num = int(re.search(r"bidmc_(\d+)_Numerics", f.name).group(1))
        hr = pd.to_numeric(d["HR"], errors="coerce").to_numpy()
        spo2 = pd.to_numeric(d["SpO2"], errors="coerce").to_numpy()
        records[num] = (hr, spo2)
    if not records:
        raise SystemExit(f"no bidmc_##_Numerics.csv files in {folder}")
    return records


def _segments(records, seconds, ok_fn):
    for num, (hr, spo2) in records.items():
        ok = ok_fn(hr, spo2) & ~np.isnan(hr) & ~np.isnan(spo2)
        for s in range(len(hr) - seconds + 1):
            if ok[s:s + seconds].all():
                yield num, s, hr[s:s + seconds], spo2[s:s + seconds]


def pick_rest(records, seconds=60):
    cands = [(abs(h.mean() - BASELINE_HR), h.std(), num, s, h, o)
             for num, s, h, o in _segments(records, seconds, lambda h, o: (o >= 96) & (h >= 51) & (h <= 90))]
    if not cands:
        raise SystemExit("no 60-s NEWS2-normal segment found")
    _, _, num, s, h, o = min(cands, key=lambda c: c[:4])
    return num, s, h, o, "NEWS2-normal every second (SpO2 >= 96 and 51 <= HR <= 90); mean HR closest to 75"


def pick_exertion(records, seconds=90):
    both = [(h.std(), num, s, h, o) for num, s, h, o in
            _segments(records, seconds, lambda h, o: (h >= 111) & (o <= 93) & (o > 0))]
    if both:
        _, num, s, h, o = min(both, key=lambda c: c[:3])
        return num, s, h, o, "NEWS2-abnormal every second, with BOTH HR >= 111 and SpO2 <= 93"
    anyab = [(h.std(), num, s, h, o) for num, s, h, o in
             _segments(records, seconds, lambda h, o: ((o <= 93) | (h >= 111)) & (h > 50) & (o > 0))]
    if not anyab:
        raise SystemExit("no 90-s NEWS2-abnormal segment found")
    _, num, s, h, o = min(anyab, key=lambda c: c[:3])
    return num, s, h, o, "NEWS2-abnormal every second (SpO2 <= 93 or HR >= 111)"


def write_replay(out_dir: Path, kind: str, num: int, start: int, hr, spo2, selection: str) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / f"{kind}.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["t_s", "hr", "spo2"])
        for t, (a, b) in enumerate(zip(hr, spo2)):
            w.writerow([t, int(a), int(b)])
    meta = {
        "kind": kind,
        "source": "BIDMC (PhysioNet)",
        "source_url": SOURCE_URL,
        "record": f"bidmc_{num:02d}",
        "record_number": num,
        "file": f"bidmc_csv/bidmc_{num:02d}_Numerics.csv",
        "start_s": int(start),
        "end_s": int(start + len(hr)),
        "seconds": int(len(hr)),
        "baseline_hr": BASELINE_HR,
        "baseline_note": "adult resting reference; hr_delta = HR - 75 (same as the training data)",
        "selection": selection,
        "hr_mean": round(float(np.mean(hr)), 1), "hr_min": int(np.min(hr)), "hr_max": int(np.max(hr)),
        "spo2_mean": round(float(np.mean(spo2)), 1), "spo2_min": int(np.min(spo2)), "spo2_max": int(np.max(spo2)),
        "licence": "ODC-By 1.0",
        "citation": CITATION,
        "note": ("Real ICU vitals replayed in the demo (not recorded from the participant). "
                 "Built by ml/make_replay.py."),
    }
    (out_dir / f"{kind}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder")
    parser.add_argument("--out", default="ml/replay")
    args = parser.parse_args(argv)
    records = load_records(args.folder)
    out = Path(args.out)
    for kind, picker in (("rest", pick_rest), ("exertion", pick_exertion)):
        meta = write_replay(out, kind, *picker(records))
        print(f"{kind}: {meta['record']} s {meta['start_s']}-{meta['end_s']} ({meta['seconds']} s), "
              f"HR {meta['hr_min']}-{meta['hr_max']} (mean {meta['hr_mean']}), "
              f"SpO2 {meta['spo2_min']}-{meta['spo2_max']} (mean {meta['spo2_mean']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
