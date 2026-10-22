"""Hardware lock: Role A's node.hwlock when it exists, otherwise a local stand-in.

The stand-in behaves the same way (exclusive non-blocking flock on /tmp/icu-hw.lock,
HardwareBusy naming the holder and PID). Remove it once node/hwlock.py is in the repo.
"""

import os

try:
    from node.hwlock import HardwareBusy, HardwareLock  # noqa: F401  (Role A's module)
    USING_ROLE_A_LOCK = True
except ModuleNotFoundError as e:
    if e.name not in ("node.hwlock", "node"):
        raise
    USING_ROLE_A_LOCK = False

    import fcntl

    LOCK_PATH = "/tmp/icu-hw.lock"

    class HardwareBusy(Exception):
        """The camera/I2C hardware is held by another program."""

    class HardwareLock:
        def __init__(self, name: str, path: str = LOCK_PATH):
            self.name = name
            self.path = path
            self._fh = None

        def __enter__(self):
            fh = open(self.path, "a+")
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fh.seek(0)
                holder = fh.read().strip() or "unknown program"
                fh.close()
                raise HardwareBusy(f"hardware is busy: held by {holder}") from None
            fh.seek(0)
            fh.truncate()
            fh.write(f"{self.name} (pid {os.getpid()})\n")
            fh.flush()
            self._fh = fh
            return self

        def __exit__(self, *exc):
            if self._fh:
                self._fh.seek(0)
                self._fh.truncate()
                fcntl.flock(self._fh, fcntl.LOCK_UN)
                self._fh.close()
                self._fh = None
            return False
