"""Save raw 100 Hz IR/red samples to ~/icu-data/raw/sensor_<tag>.csv.

Usage (Pi): .venv/bin/python -m node.bio.tools.capture_raw --seconds 30 --tag rest_P1
"""

import argparse
import csv
import sys

from node.bio.tools._common import collect, data_dir, open_sensor, run_locked


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=30)
    parser.add_argument("--tag", required=True, help="e.g. rest_P1 or move_P1")
    args = parser.parse_args(argv)

    def run():
        s = open_sensor()
        try:
            print(f"capturing {args.seconds:.0f} s ...")
            ir, red = collect(s, args.seconds)
        finally:
            s.shutdown()
            s.close()
        path = data_dir() / f"sensor_{args.tag}.csv"
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["t_s", "ir", "red"])
            for i, (a, b) in enumerate(zip(ir, red)):
                w.writerow([f"{i / 100:.2f}", int(a), int(b)])
        print(f"{len(ir)} samples ({len(ir) / 100:.1f} s), dropped {s.dropped}; "
              f"mean IR {ir.mean():.0f}, mean red {red.mean():.0f}")
        print(f"saved {path}")
        return 0

    return run_locked("bio.capture_raw", run)


if __name__ == "__main__":
    sys.exit(main())
