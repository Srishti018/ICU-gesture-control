"""Print per-frame gesture scores (every 0.5 s) and window features (every 3 s), or run the
guided calibration poses P1-P9 and save the results.

Usage:
  .venv/bin/python -m node.tools.vision_probe                 # live readout
  .venv/bin/python -m node.tools.vision_probe --calibrate     # guided poses P1-P9 (interactive)
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

from node.tools._common import run_locked, setup_logging

POSES = [
    ("P1", "Open palm facing the camera, fingers up, thumb out", "min", 0.85),
    ("P2", "Same, but fingers together (no gaps)", "min", 0.75),
    ("P3", "Relaxed hand resting, fingers slightly curled", "max", 0.30),
    ("P4", "Fist", "max", 0.15),
    ("P5", "Open palm lying flat / pointing sideways", "max", 0.20),
    ("P6", "Scratching the face / adjusting a blanket", "max", 0.35),
    ("P7", "Half-open palm, fingers bent about 45 degrees", "range", (0.30, 0.70)),
    ("P8", "P1 in dimmer light (lights partly off)", "record", None),
    ("P9", "No hand in view", "max", 0.0),
]
HOLD_S = 6.0


def target_text(kind, value) -> str:
    return {"min": f">= {value:.2f}", "max": f"<= {value:.2f}", "record": "record only"}.get(
        kind, f"{value[0]:.2f}-{value[1]:.2f}" if kind == "range" else "")


def meets(kind, value, g) -> bool | None:
    if kind == "min":
        return g >= value
    if kind == "max":
        return g <= value
    if kind == "range":
        return value[0] <= g <= value[1]
    return None


def frame_line(pts, g, d) -> str:
    if pts is None or not d or d.get("too_small"):
        return "hand no"
    a = d["angles"]
    return (f"hand yes s={d['s']:.0f}px angles i{a['index']:.0f} m{a['middle']:.0f} r{a['ring']:.0f} "
            f"p{a['pinky']:.0f} t={d['t']:.2f} u={d['u']:.2f} open={d['open']:.2f} up={d['up']:.2f} g={g:.2f}")


def live(vision) -> int:
    print("Ctrl+C to stop.", flush=True)
    vision.window()
    next_w = time.monotonic() + 3
    try:
        while True:
            time.sleep(0.5)
            print("  " + frame_line(*vision.latest()), flush=True)
            if time.monotonic() >= next_w:
                next_w += 3
                print(f"WINDOW {vision.window()}", flush=True)
    except KeyboardInterrupt:
        return 0


def calibrate(vision, who: str) -> int:
    results = []
    print(f"Calibration for hand '{who}'. For each pose: get into position, press Enter, and hold it "
          f"steady for {HOLD_S:.0f} seconds until it says 'done'.", flush=True)
    for code, text, kind, value in POSES:
        while True:
            input(f"\n{code}: {text}  (target {target_text(kind, value)})\n    Press Enter when in position... ")
            print("    go - hold still", flush=True)
            vision.window()                       # discard frames from before "go"
            time.sleep(HOLD_S / 2)
            w1 = vision.window()
            time.sleep(HOLD_S / 2)
            w2 = vision.window()
            g = round((w1["gesture_conf"] + w2["gesture_conf"]) / 2, 3)
            ok = meets(kind, value, g)
            print(f"    done: windows {w1['gesture_conf']:.3f} / {w2['gesture_conf']:.3f} (mean {g:.3f}), "
                  f"tremor {w1['tremor']:.3f} / {w2['tremor']:.3f}, hand {w1['n_hand_frames']}/{w1['n_frames']} "
                  f"frames, {w1['fps']:.1f} fps -> {'PASS' if ok else 'record' if ok is None else 'MISS'}")
            again = input("    Enter = keep, r = redo this pose: ").strip().lower()
            if again != "r":
                break
        results.append({"pose": code, "description": text, "target": target_text(kind, value),
                        "window1": w1, "window2": w2, "gesture_conf_mean": g, "pass": ok})
    out_dir = Path.home() / "icu-data" / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"calibration_{who}_{datetime.now():%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps({"who": who, "params": vision.params, "results": results}, indent=2) + "\n")
    print("\n| Pose | Target | gesture_conf (2 windows) | tremor | Result |\n| --- | --- | --- | --- | --- |")
    for r in results:
        print(f"| {r['pose']} | {r['target']} | {r['window1']['gesture_conf']:.3f} / {r['window2']['gesture_conf']:.3f} "
              f"| {r['window1']['tremor']:.3f} | {'PASS' if r['pass'] else 'record' if r['pass'] is None else 'MISS'} |")
    print(f"\nSaved {path}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--calibrate", action="store_true", help="guided poses P1-P9")
    p.add_argument("--who", default="A", help="label for whose hand is calibrated (no names), e.g. A or B")
    p.add_argument("--camera", choices=["usb", "picam"], default="usb")
    p.add_argument("--index", type=int, default=0)
    p.add_argument("--params", default=None, help="gesture params JSON to try")
    args = p.parse_args(argv)
    setup_logging()

    def run():
        from node.settings import Settings
        from node.vision.camera import CameraError
        from node.vision.features import VisionFeatureExtractor
        from node.vision.hands import TrackerError
        overrides = {"camera_kind": args.camera, "camera_index": args.index}
        if args.params:
            overrides["params_path"] = Path(args.params)
        vision = VisionFeatureExtractor(Settings.load(**overrides))
        try:
            vision.start()
        except (CameraError, TrackerError) as e:
            print(f"VISION: {e}", file=sys.stderr)
            return 4
        try:
            return calibrate(vision, args.who) if args.calibrate else live(vision)
        except (KeyboardInterrupt, EOFError):
            print("\nstopped")
            return 1
        finally:
            vision.stop()

    return run_locked("vision_probe", run)


if __name__ == "__main__":
    sys.exit(main())
