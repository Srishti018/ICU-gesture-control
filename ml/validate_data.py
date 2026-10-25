"""Check a folder of *_windows.csv files and write data_report.md. Never changes the data.

Usage: python -m ml.validate_data <folder> [--out ml/results]
Exit codes: 0 ok · 1 not enough data (see the report) · 2 files unreadable or wrong format.
"""

import argparse
from pathlib import Path
import sys

from ml.dataset import DataFormatError, apply_exclusions, is_gesture_only, is_synthetic, load_windows
from ml.schema import CLASSES, CORE_SCENARIOS, GESTURE_CLASSES, GESTURE_SCENARIOS, SCENARIOS, is_gesture

MIN_WINDOWS_PER_LABEL = 60
MIN_PEOPLE = 2


def _md_table(headers, rows) -> list[str]:
    lines = ["| " + " | ".join(str(h) for h in headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return lines


def _fmt(v, digits=3):
    if v is None or v != v:  # None or NaN
        return "—"
    return f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def validate(folder, out_dir) -> tuple[int, str]:
    data = load_windows(folder)
    kept, excl = apply_exclusions(data)
    gesture_only = is_gesture_only(data)
    classes, core = (GESTURE_CLASSES, list(GESTURE_SCENARIOS)) if gesture_only else (CLASSES, CORE_SCENARIOS)
    label_col = "gesture" if gesture_only else "label"
    people = sorted(data["person"].unique())
    live = data[data["discarded"] == 0]

    trials = (live.groupby("trial_id")
                  .agg(person=("person", "first"), scenario=("scenario", "first"), trial=("trial", "first"),
                       label=("label", "first"), bio_mode=("bio_mode", "first"),
                       gesture=("gesture_conf", "mean"), hand=("hand_present", "mean"),
                       hr_delta=("hr_delta", "mean"), finger=("finger", "mean"),
                       hr_missing=("hr", lambda s: float(s.isna().mean())), windows=("window_idx", "size"))
                  .reset_index().sort_values(["person", "scenario", "trial"]))

    flags = []
    for t in trials.itertuples():
        if (t.scenario in SCENARIOS or t.scenario in GESTURE_SCENARIOS) and is_gesture(t.scenario) and t.hand < 0.8:
            flags.append(f"{t.trial_id}: gesture scenario with mean hand_present {t.hand:.2f} < 0.8")
        if t.scenario in ("S5", "H3") and not (t.hr_delta >= 15):
            flags.append(f"{t.trial_id}: {t.scenario} with mean hr_delta {_fmt(t.hr_delta, 1)} < 15")
        if t.scenario in ("S3", "H1") and t.gesture < 0.6:
            flags.append(f"{t.trial_id}: {t.scenario} with mean gesture_conf {t.gesture:.2f} < 0.6")
        if t.scenario in ("G_PALM", "G_PALM_DIM") and t.gesture < 0.6:
            flags.append(f"{t.trial_id}: {t.scenario} with mean gesture_conf {t.gesture:.2f} < 0.6")
        if t.scenario == "N_NOHAND" and t.hand > 0.2:
            flags.append(f"{t.trial_id}: N_NOHAND with mean hand_present {t.hand:.2f} > 0.2")
        if not gesture_only and t.hr_missing > 0.2:
            flags.append(f"{t.trial_id}: hr missing in {t.hr_missing:.0%} of windows")

    per_label = {c: int((kept[label_col] == c).sum()) for c in classes}
    problems = []
    for c, n in per_label.items():
        if n < MIN_WINDOWS_PER_LABEL:
            problems.append(f"label {c}: {n} windows after exclusions (< {MIN_WINDOWS_PER_LABEL})")
    if len(people) < MIN_PEOPLE:
        problems.append(f"{len(people)} person(s) (< {MIN_PEOPLE})")
    for p in people:
        have = set(trials.loc[trials["person"] == p, "scenario"])
        missing = [s for s in core if s not in have]
        if missing:
            problems.append(f"{p} is missing scenarios {', '.join(missing)}")

    known = list(GESTURE_SCENARIOS) if gesture_only else list(SCENARIOS)
    scen_codes = [s for s in known if s in set(trials["scenario"])] + \
                 sorted(set(trials["scenario"]) - set(known))
    counts = trials.groupby(["person", "scenario"]).size()
    discarded_trials = sorted(data.loc[data["discarded"] == 1, "trial_id"].unique())

    lines = ["# Data report", ""]
    if is_synthetic(data):
        lines += ["> **SYNTHETIC DATA — pipeline test only. Not a result; never use in the report.**", ""]
    lines += [f"- Folder: `{folder}`",
              f"- Files read: {data['trial_id'].nunique()}",
              f"- Rows: {len(data)}",
              f"- People: {', '.join(people)}",
              f"- Bio mode(s): {', '.join(sorted(data['bio_mode'].astype(str).unique()))}",
              f"- Protocol: {'gesture-only (label column: gesture)' if gesture_only else 'fusion'}", ""]
    lines += ["## Trials per person × scenario (not discarded)", ""]
    lines += _md_table(["person"] + scen_codes,
                       [[p] + [int(counts.get((p, s), 0)) for s in scen_codes] for p in people])
    lines += ["", "## Discarded trials", ""]
    lines += [f"- {t}" for t in discarded_trials] or ["None."]
    lines += ["", "## Windows per label after exclusions (§12.1)", ""]
    lines += _md_table([label_col, "windows"], [[c, per_label[c]] for c in classes])
    lines += ["", f"Excluded: {excl['first_window']} first windows, {excl['discarded_windows']} windows from "
                  f"{excl['discarded_trials']} discarded trial(s), {excl['missing_bio']} windows with missing "
                  f"hr_delta/spo2 {excl['missing_bio_by_scenario'] or ''}".rstrip(), ""]
    lines += ["## Per trial", ""]
    lines += _md_table(["trial", "label", "windows", "gesture_conf", "hand_present", "hr_delta", "finger", "bio_mode"],
                       [[t.trial_id, t.label, t.windows, _fmt(t.gesture), _fmt(t.hand, 2), _fmt(t.hr_delta, 1),
                         _fmt(t.finger, 2), t.bio_mode] for t in trials.itertuples()])
    lines += ["", "## Flags (for review with the team; nothing was changed)", ""]
    lines += [f"- {f}" for f in flags] or ["None."]
    lines += ["", "## Result", ""]
    lines += [f"- NOT ENOUGH DATA: {p}" for p in problems] or ["OK: enough data to train."]
    report = "\n".join(lines) + "\n"

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data_report.md").write_text(report, encoding="utf-8")

    summary = [f"{data['trial_id'].nunique()} files, {len(data)} rows, people: {', '.join(people)}",
               f"windows per {label_col}: " + ", ".join(f"{c}={per_label[c]}" for c in classes),
               f"{len(flags)} flag(s)"] + [f"  FLAG {f}" for f in flags] + \
              [f"  NOT ENOUGH DATA: {p}" for p in problems] + [f"report: {out_dir / 'data_report.md'}"]
    return (1 if problems else 0), "\n".join(summary)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate a folder of windows CSV files")
    parser.add_argument("folder")
    parser.add_argument("--out", default="ml/results")
    args = parser.parse_args(argv)
    try:
        code, summary = validate(args.folder, args.out)
    except DataFormatError as e:
        print(f"FORMAT ERROR: {e}", file=sys.stderr)
        return 2
    print(summary)
    return code


if __name__ == "__main__":
    sys.exit(main())
