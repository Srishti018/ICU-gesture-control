"""Buzzer on GPIO17: urgent = 2 x 150 ms beeps, critical = 3 x 400 ms. Once per alert, never looping."""

import logging
import queue
import threading
import time

log = logging.getLogger("node.buzzer")

PATTERNS = {"urgent": (2, 0.150), "critical": (3, 0.400)}
GAP_S = 0.150
GPIO_PIN = 17


def pattern_schedule(level: str) -> list[tuple[float, float]]:
    """[(on_seconds, off_seconds), ...] for one alert; empty for routine or unknown levels."""
    if level not in PATTERNS:
        return []
    count, on = PATTERNS[level]
    return [(on, GAP_S if i < count - 1 else 0.0) for i in range(count)]


class _Player:
    """Plays patterns one after another on a worker thread (alerts never overlap or loop)."""

    def __init__(self, on, off, sleep=time.sleep):
        self._on, self._off, self._sleep = on, off, sleep
        self._q = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="buzzer", daemon=True)
        self._thread.start()

    def play(self, level: str) -> None:
        if pattern_schedule(level):
            self._q.put(level)

    def _run(self) -> None:
        while True:
            level = self._q.get()
            if level is None:
                return
            for on_s, off_s in pattern_schedule(level):
                self._on()
                self._sleep(on_s)
                self._off()
                if off_s:
                    self._sleep(off_s)

    def close(self) -> None:
        self._q.put(None)
        self._thread.join(timeout=3)


class MockBuzzer:
    kind = "mock"

    def play(self, level: str) -> None:
        sched = pattern_schedule(level)
        if sched:
            log.info("BUZZER %s: %d x %d ms beep", level, len(sched), round(sched[0][0] * 1000))

    def close(self) -> None:
        pass


class Buzzer:
    kind = "gpio"

    def __init__(self, pin: int = GPIO_PIN, passive: bool = False):
        import gpiozero
        if passive:
            dev = gpiozero.TonalBuzzer(pin)
            self._dev, on, off = dev, lambda: dev.play(2000), dev.stop
        else:
            dev = gpiozero.Buzzer(pin)
            self._dev, on, off = dev, dev.on, dev.off
        self._player = _Player(on, off)

    def play(self, level: str) -> None:
        try:
            self._player.play(level)
        except Exception as e:
            log.warning("buzzer failed: %s", e)

    def close(self) -> None:
        self._player.close()
        try:
            self._dev.close()
        except Exception:
            pass


def make_buzzer(enabled: bool, mock: bool, passive: bool = False):
    """Real buzzer, mock, or None. Never raises: GPIO errors disable the buzzer with a log line."""
    if mock:
        return MockBuzzer()
    if not enabled:
        return None
    try:
        return Buzzer(passive=passive)
    except Exception as e:
        log.warning("buzzer disabled: %s", e)
        return None
