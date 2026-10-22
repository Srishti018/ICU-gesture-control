"""Write "ICU node OLED OK" and the time to the OLED.

Usage (Pi): .venv/bin/python -m node.tools.oled_test [--driver ssd1306|sh1106] [--mock]
"""

import argparse
from datetime import datetime
import sys
import time

from node.tools._common import run_locked, setup_logging


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--driver", choices=["ssd1306", "sh1106"], default="ssd1306")
    p.add_argument("--mock", action="store_true", help="print the screen instead (laptop)")
    p.add_argument("--seconds", type=float, default=10)
    args = p.parse_args(argv)
    setup_logging()

    def run():
        from node.local_io.oled import MockOled, Oled
        try:
            oled = MockOled() if args.mock else Oled(args.driver)
        except Exception as e:
            print(f"OLED not available: {e}. Check i2cdetect -y 1 shows 3c; try --driver sh1106.", file=sys.stderr)
            return 1
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            oled.show(["ICU node OLED OK", datetime.now().strftime("%H:%M:%S"), "", f"driver {args.driver}", ""],
                      invert_line=0)
            time.sleep(1)
        oled.close()
        print("Did you see 'ICU node OLED OK' and the time on the OLED?")
        return 0

    return run_locked("oled_test", run)


if __name__ == "__main__":
    sys.exit(main())
