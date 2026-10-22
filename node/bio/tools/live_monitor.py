"""Print HR, SpO2, finger and quality once per second from the live sensor.

Usage (Pi): .venv/bin/python -m node.bio.tools.live_monitor [--seconds 60] [--log file.csv]
"""

import argparse
import sys
import time

from node.bio import BioUnavailable
from node.bio.live import LiveBio


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=0, help="0 = until Ctrl+C")
    parser.add_argument("--log", default=None, help="also write per-second records to this CSV")
    args = parser.parse_args(argv)
    bio = LiveBio(take_lock=True, log_path=args.log)
    try:
        bio.start()
    except BioUnavailable as e:
        print(e, file=sys.stderr)
        return 1
    start = time.monotonic()
    try:
        while not args.seconds or time.monotonic() - start < args.seconds:
            time.sleep(1)
            recs = bio.records(1.5)
            r = recs[-1] if recs else None
            if bio.failed:
                print("sensor failed (too many I2C errors)")
                return 1
            if r:
                print(f"{time.monotonic() - start:5.0f}s  hr={r['hr']}  spo2={r['spo2']}  "
                      f"finger={'yes' if r['finger'] else 'no'}  quality={r['quality']:.2f}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        bio.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
