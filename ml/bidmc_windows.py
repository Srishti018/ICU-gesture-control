"""Build 3-s HR/SpO2 windows from the BIDMC dataset and label them with NEWS2-based rules.

Usage: python -I ml/bidmc_windows.py <folder with bidmc_##_Numerics.csv> [--out ml/data/public/bidmc_news2_windows.csv]

Rules (applied to the 3-s window means; see ml/data/public/README.md):
  HR <= 50                                  -> excluded
  SpO2 <= 93 or HR >= 111                   -> abnormal
  SpO2 >= 96 and 51 <= HR <= 90             -> normal
  anything else                             -> excluded
A window is only used when all 3 seconds have HR > 0 and SpO2 > 0 (no missing samples or sensor dropouts).
"""

import argparse
from pathlib import Path
import re
import sys

import pandas as pd

WINDOW_SECONDS = 3
HR_REFERENCE = 75  # adult resting reference: hr_delta = HR - 75


def label(hr: float, spo2: float):
    if hr <= 50:
        return None
    if spo2 <= 93 or hr >= 111:
        return "abnormal"
    if spo2 >= 96 and 51 <= hr <= 90:
        return "normal"
    return None


def patient_windows(path: Path) -> list[dict]:
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    patient = re.search(r"bidmc_(\d+)_Numerics", path.name).group(1)
    df = df[["Time [s]", "HR", "SpO2"]].apply(pd.to_numeric, errors="coerce")
    rows = []
    for i in range(len(df) // WINDOW_SECONDS):
        w = df.iloc[i * WINDOW_SECONDS:(i + 1) * WINDOW_SECONDS]
        if w[["HR", "SpO2"]].isna().any().any() or (w[["HR", "SpO2"]] <= 0).any().any():
            continue
        hr, spo2 = w["HR"].mean(), w["SpO2"].mean()
        lab = label(hr, spo2)
        if lab is None:
            continue
        rows.append({"patient": f"bidmc_{patient}", "window_idx": i, "t_start_s": int(w["Time [s]"].iloc[0]),
                     "hr": round(hr, 2), "spo2": round(spo2, 2), "hr_delta": round(hr - HR_REFERENCE, 2),
                     "label": lab})
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder")
    parser.add_argument("--out", default="ml/data/public/bidmc_news2_windows.csv")
    args = parser.parse_args(argv)
    files = sorted(Path(args.folder).glob("bidmc_*_Numerics.csv"))
    if not files:
        print(f"no bidmc_##_Numerics.csv files in {args.folder}", file=sys.stderr)
        return 2
    data = pd.DataFrame([r for f in files for r in patient_windows(f)])
    counts = data.groupby(["patient", "label"]).size().unstack(fill_value=0).reindex(
        columns=["normal", "abnormal"], fill_value=0)
    all_patients = [f"bidmc_{re.search(r'bidmc_(\d+)_', f.name).group(1)}" for f in files]
    counts = counts.reindex(all_patients, fill_value=0)
    print(counts.to_string())
    print(f"TOTAL normal={int(counts['normal'].sum())} abnormal={int(counts['abnormal'].sum())} "
          f"patients={len(files)} (with any window: {int((counts.sum(axis=1) > 0).sum())})")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(args.out, index=False)
    print(f"saved {args.out} ({len(data)} windows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
