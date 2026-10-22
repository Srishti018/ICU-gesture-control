"""Camera + MediaPipe speed test: frames, hand frames, fps, inference ms, CPU temperature.

Usage: .venv/bin/python -m node.tools.fps_test [--camera usb|picam] [--index N] [--seconds 30]
"""

import argparse
import sys
import time

from node.tools._common import cpu_temp, run_locked, setup_logging


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--camera", choices=["usb", "picam"], default="usb")
    p.add_argument("--index", type=int, default=0)
    p.add_argument("--seconds", type=float, default=30)
    args = p.parse_args(argv)
    setup_logging()

    def run():
        from node.settings import Settings
        from node.vision.camera import Camera, CameraError
        from node.vision.hands import HandTracker, TrackerError
        s = Settings.load()
        try:
            cam = Camera(args.camera, args.index, s.camera_width, s.camera_height).open()
        except CameraError as e:
            print(f"CAMERA: {e}", file=sys.stderr)
            return 4
        try:
            tracker = HandTracker(s.hand_model_path)
        except TrackerError as e:
            cam.close()
            print(f"HAND TRACKER: {e}", file=sys.stderr)
            return 4
        frames = hands = 0
        infer = 0.0
        print(f"running {args.seconds:.0f} s; hold a hand in view and move it slowly ...", flush=True)
        start = time.monotonic()
        try:
            while time.monotonic() - start < args.seconds:
                ok, frame = cam.read()
                if not ok:
                    continue
                a = time.perf_counter()
                pts, _, _ = tracker.process(frame)
                infer += time.perf_counter() - a
                frames += 1
                hands += pts is not None
        except CameraError as e:
            print(f"CAMERA: {e}", file=sys.stderr)
            return 4
        finally:
            elapsed = time.monotonic() - start
            cam.close()
            tracker.close()
        fps = frames / elapsed if elapsed else 0
        print(f"frames {frames} · with a hand {hands} ({(hands / frames * 100) if frames else 0:.0f}%) · "
              f"{fps:.1f} fps · inference {1000 * infer / max(frames, 1):.1f} ms · {tracker.api} API · "
              f"CPU {cpu_temp()}")
        verdict = "good (>= 5 fps)" if fps >= 5 else "acceptable on the 3B+ (3-5 fps)" if fps >= 3 else \
            "too slow (< 3 fps): see the Role A plan section 7.6"
        print(f"verdict: {verdict}")
        return 0

    return run_locked("fps_test", run)


if __name__ == "__main__":
    sys.exit(main())
