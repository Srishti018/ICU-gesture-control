"""Guided comparison of the sensor's HR/SpO2 with a reference (oximeter or counted pulse).

Usage (Pi, interactive): .venv/bin/python -m node.bio.tools.validate_hr [--oximeter | --counted]
Runs 3 checks at rest and 1 after exercise, prints a Markdown table for ROLE_B_NOTES.md
and the suggested live/manual decision (the team confirms it).
"""

import argparse
import csv
from datetime import datetime
import statistics
import sys
import time

from node.bio import BioUnavailable
from node.bio.live import LiveBio
from node.bio.tools._common import data_dir, prompt

CHECK_SECONDS = 30
WARMUP_SECONDS = 10
REST_CHECKS = 3
REST_MAX_DIFF = 8
EXERCISE_RISE = 15


def ask_int(text: str) -> int | None:
    while True:
        raw = input(f"    {text}: ").strip()
        if raw == "":
            return None
        try:
            return int(raw)
        except ValueError:
            print("    please type a whole number (or leave empty if not available)")


def run_check(bio: LiveBio) -> tuple[int | None, int | None]:
    print(f"    measuring for {CHECK_SECONDS} s ...", flush=True)
    time.sleep(CHECK_SECONDS)
    recs = bio.records(CHECK_SECONDS)
    hrs = [r["hr"] for r in recs if r["hr"] is not None]
    spo2s = [r["spo2"] for r in recs if r["spo2"] is not None]
    hr = round(statistics.median(hrs)) if hrs else None
    spo2 = round(statistics.median(spo2s)) if spo2s else None
    print(f"    sensor: HR {hr}, SpO2 {spo2} ({len(hrs)}/{len(recs)} seconds valid)")
    return hr, spo2


def decide(rows) -> str:
    rest = [r for r in rows if r["check"].startswith("rest")]
    ok_rest = sum(1 for r in rest if r["sensor_hr"] is not None and r["ref_hr"] is not None
                  and abs(r["sensor_hr"] - r["ref_hr"]) <= REST_MAX_DIFF)
    ex = next(r for r in rows if r["check"] == "after_exercise")
    sensor_base = statistics.median([r["sensor_hr"] for r in rest if r["sensor_hr"] is not None] or [0])
    ref_base = statistics.median([r["ref_hr"] for r in rest if r["ref_hr"] is not None] or [0])
    ref_rose = ex["ref_hr"] is not None and ex["ref_hr"] >= ref_base + EXERCISE_RISE
    sensor_rose = ex["sensor_hr"] is not None and ex["sensor_hr"] >= sensor_base + EXERCISE_RISE
    live = ok_rest >= 2 and (sensor_rose or not ref_rose)
    return (f"{'LIVE' if live else 'MANUAL'} (rest checks within {REST_MAX_DIFF} bpm: {ok_rest}/3; "
            f"after exercise reference rose by >= {EXERCISE_RISE}: {ref_rose}, sensor rose: {sensor_rose})")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ref = parser.add_mutually_exclusive_group()
    ref.add_argument("--oximeter", action="store_true", help="reference is a commercial fingertip oximeter (default)")
    ref.add_argument("--counted", action="store_true", help="reference is a pulse counted at the wrist")
    args = parser.parse_args(argv)

    bio = LiveBio(take_lock=True)
    try:
        bio.start()
    except BioUnavailable as e:
        print(e, file=sys.stderr)
        return 1
    rows = []
    try:
        if args.counted:
            setup = ("Finger on the MAX30100. Sit still. Another person will count your pulse at the wrist "
                     "for 30 seconds when I say go, and multiply by 2.")
        else:
            setup = ("Finger on the MAX30100. Put the commercial oximeter on a finger of the OTHER hand. Sit still.")
        prompt(setup)
        print(f"    warming up {WARMUP_SECONDS} s ...", flush=True)
        time.sleep(WARMUP_SECONDS)
        checks = [f"rest_{i}" for i in range(1, REST_CHECKS + 1)] + ["after_exercise"]
        for name in checks:
            if name == "after_exercise":
                prompt("Do 60 seconds of spot jogging (stop at once if you feel dizzy or unwell), "
                       "then sit and put the finger back.")
                time.sleep(3)
            else:
                prompt(f"Check {name}: stay still." + (" Start counting now." if args.counted else ""))
            hr, spo2 = run_check(bio)
            ref_hr = ask_int("Type the reference heart rate (bpm)")
            ref_spo2 = None if args.counted else ask_int("Type the reference SpO2 (%) (empty if none)")
            rows.append({"check": name, "sensor_hr": hr, "ref_hr": ref_hr,
                         "diff": None if hr is None or ref_hr is None else hr - ref_hr,
                         "sensor_spo2": spo2, "ref_spo2": ref_spo2})
    except KeyboardInterrupt:
        print("\nstopped")
        return 1
    finally:
        bio.stop()

    path = data_dir() / f"validate_hr_{datetime.now():%Y%m%d-%H%M%S}.csv"
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    fmt = lambda v: "—" if v is None else str(v)  # noqa: E731
    print("\n| Check | Sensor HR | Reference HR | Difference | Sensor SpO₂ | Reference SpO₂ |")
    print("| --- | --- | --- | --- | --- | --- |")
    for r in rows:
        print(f"| {r['check']} | {fmt(r['sensor_hr'])} | {fmt(r['ref_hr'])} | {fmt(r['diff'])} | "
              f"{fmt(r['sensor_spo2'])} | {fmt(r['ref_spo2'])} |")
    print(f"\nSuggested decision: {decide(rows)}")
    print("The team must confirm the decision. Saved", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
