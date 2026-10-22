"""Keyboard control: one command per line on stdin (works in a terminal and with tmux send-keys)."""

import logging
import sys
import threading

log = logging.getLogger("node.control")

HELP = """Keys (type, then Enter):
  r  model biosignals = replay REST (restart from the beginning)
  x  model biosignals = replay EXERTION (restart from the beginning)
  l  model biosignals = live sensor (if available and the baseline is done)
  g  synthetic vision only: toggle the gesture on/off
  s  print one status line
  q  clean quit (publishes offline)
  h  this help"""


class Control:
    def __init__(self, handlers: dict, stream=None):
        self.handlers = handlers
        self.stream = stream or sys.stdin
        self._thread = threading.Thread(target=self._run, name="control", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def handle(self, line: str) -> None:
        key = line.strip().lower()
        if not key:
            return
        fn = self.handlers.get(key)
        if fn is None:
            print(HELP, flush=True)
            return
        try:
            fn()
        except Exception as e:
            log.warning("command %r failed: %s", key, e)

    def _run(self) -> None:
        try:
            for line in self.stream:
                self.handle(line)
        except (OSError, ValueError):
            pass
        # EOF: keep running without keyboard control (e.g. started in the background)
