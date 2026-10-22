"""Single-user lock for the camera and I2C devices (docs/NODE_INTERFACES.md §B.5).

    with HardwareLock("node.main"):
        ...

Takes an exclusive non-blocking flock on /tmp/icu-hw.lock and writes the holder's
name and PID into it. If another program holds it, raises HardwareBusy.
Programs exit with EXIT_BUSY (3) after printing the message.
"""

import fcntl
import os

LOCK_PATH = "/tmp/icu-hw.lock"
EXIT_BUSY = 3


class HardwareBusy(Exception):
    def __init__(self, holder: str, pid: int | None):
        self.holder = holder
        self.pid = pid
        pid_text = f" (pid {pid})" if pid else ""
        super().__init__(f"HARDWARE BUSY: {holder}{pid_text} is using the camera/sensors")


def _parse_holder(text: str) -> tuple[str, int | None]:
    parts = text.strip().rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0], int(parts[1])
    return text.strip() or "another program", None


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
            holder, pid = _parse_holder(fh.read())
            fh.close()
            raise HardwareBusy(holder, pid) from None
        fh.seek(0)
        fh.truncate()
        fh.write(f"{self.name} {os.getpid()}\n")
        fh.flush()
        self._fh = fh
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            self._fh.seek(0)
            self._fh.truncate()
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None
        return False
