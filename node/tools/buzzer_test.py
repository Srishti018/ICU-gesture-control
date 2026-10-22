"""Play the urgent pattern (2 short beeps), then the critical pattern (3 long beeps).

Usage (Pi): .venv/bin/python -m node.tools.buzzer_test [--passive] [--mock]
"""

import argparse
import sys
import time

from node.tools._common import run_locked, setup_logging


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--passive", action="store_true", help="passive buzzer (2 kHz tone) instead of active")
    p.add_argument("--mock", action="store_true", help="print the patterns instead (laptop)")
    args = p.parse_args(argv)
    setup_logging()

    def run():
        from node.local_io.buzzer import Buzzer, MockBuzzer
        try:
            buzzer = MockBuzzer() if args.mock else Buzzer(passive=args.passive)
        except Exception as e:
            print(f"buzzer not available: {e}. Check the wiring on GPIO17 (pin 11).", file=sys.stderr)
            return 1
        print("urgent: 2 short beeps", flush=True)
        buzzer.play("urgent")
        time.sleep(1.5)
        print("critical: 3 long beeps", flush=True)
        buzzer.play("critical")
        time.sleep(2.5)
        buzzer.close()
        print("Did you hear 2 short beeps, then 3 long beeps?")
        return 0

    return run_locked("buzzer_test", run)


if __name__ == "__main__":
    sys.exit(main())
