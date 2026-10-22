"""Measure IR DC with and without a finger and propose finger_ir_min.

Usage (Pi): .venv/bin/python -m node.bio.tools.finger_threshold [--save]
"""

import argparse
import sys

from node.bio.live import load_params
from node.bio.tools._common import collect, open_sensor, prompt, run_locked, save_params

SATURATION_LIMIT = 60000


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--save", action="store_true", help="write the result to node/bio/sensor_params.json")
    args = parser.parse_args(argv)

    def run():
        params = load_params()
        ir_code = int(params["ir_code"])
        while True:
            s = open_sensor({**params, "ir_code": ir_code})
            try:
                prompt("Keep your finger OFF the sensor (5 seconds).")
                off, _ = collect(s, 5)
                prompt("Rest your left index fingertip lightly on the sensor and keep still (10 seconds).")
                on, _ = collect(s, 10)
            finally:
                s.shutdown()
                s.close()
            print(f"ir_code {ir_code}: IR DC without finger {off.mean():.0f}, with finger {on.mean():.0f}")
            if on.mean() > SATURATION_LIMIT and ir_code > 2:
                ir_code -= 2
                print(f"Finger level is near saturation (> {SATURATION_LIMIT}); lowering ir_code to {ir_code} and repeating.")
                continue
            break
        threshold = int((off.mean() + on.mean()) / 2)
        print(f"proposed finger_ir_min = {threshold} (ir_code {ir_code})")
        if args.save:
            save_params({"finger_ir_min": threshold, "ir_code": ir_code})
            print("saved to node/bio/sensor_params.json")
        return 0

    return run_locked("bio.finger_threshold", run)


if __name__ == "__main__":
    sys.exit(main())
