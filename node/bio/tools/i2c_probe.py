"""Check the MAX30100: part ID, revision and a dump of registers 0x00-0x09.

Usage (Pi): .venv/bin/python -m node.bio.tools.i2c_probe
"""

import argparse
import sys

from node.bio.max30100 import MAX30100
from node.bio.tools._common import run_locked


def probe() -> int:
    s = MAX30100()
    s.open()  # raises SensorError if the part ID is not 0x11
    try:
        print("part ID: 0x11 (MAX30100)")
        print(f"revision: 0x{s.revision():02x}")
        for reg in range(0x00, 0x0A):
            print(f"  reg 0x{reg:02x} = 0x{s._read(reg):02x}")
    finally:
        s.close()
    return 0


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__.splitlines()[0]).parse_args(argv)
    return run_locked("bio.i2c_probe", probe)


if __name__ == "__main__":
    sys.exit(main())
