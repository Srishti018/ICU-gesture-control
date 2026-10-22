"""Balance the red LED against IR: try red_code 5..11 and pick red DC closest to IR DC.

Usage (Pi): .venv/bin/python -m node.bio.tools.led_tune [--save]
"""

import argparse
import sys

from node.bio.live import load_params
from node.bio.tools._common import collect, open_sensor, prompt, run_locked, save_params

RED_CODES = range(5, 12)
SETTLE_S = 0.5
MEASURE_S = 2.0
TOLERANCE = 0.25


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--save", action="store_true", help="write the result to node/bio/sensor_params.json")
    args = parser.parse_args(argv)

    def run():
        params = load_params()
        ir_code = int(params["ir_code"])
        s = open_sensor(params)
        results = []
        try:
            prompt("Finger on the sensor, keep still, about 15 seconds.")
            for red in RED_CODES:
                s.set_led(red, ir_code)
                collect(s, SETTLE_S)
                ir, rd = collect(s, MEASURE_S)
                results.append((red, ir.mean(), rd.mean()))
                print(f"red_code {red:2d}: IR DC {ir.mean():7.0f}  red DC {rd.mean():7.0f}")
        finally:
            s.shutdown()
            s.close()
        best = min(results, key=lambda r: abs(r[2] - r[1]))
        diff = abs(best[2] - best[1]) / best[1] if best[1] else float("inf")
        print(f"best red_code {best[0]} (red within {diff:.0%} of IR; aim within {TOLERANCE:.0%})")
        if diff > TOLERANCE:
            print("WARNING: no setting got red within 25% of IR; record this in ROLE_B_NOTES.md")
        if args.save:
            save_params({"red_code": best[0], "ir_code": ir_code})
            print("saved to node/bio/sensor_params.json")
        return 0

    return run_locked("bio.led_tune", run)


if __name__ == "__main__":
    sys.exit(main())
