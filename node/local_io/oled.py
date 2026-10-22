"""128x64 I2C OLED (luma.oled, SSD1306 or SH1106) and a mock that writes the screen to the log.

The real driver is imported lazily; any I2C error is logged at most once per minute and
never stops the node.
"""

import logging
import time

log = logging.getLogger("node.oled")

MAX_CHARS = 21   # default font on a 128-px-wide screen
MAX_LINES = 5


def format_lines(node: str, mqtt_ok: bool, sensor: dict | None, bio_mode: str, gesture: float | None,
                 tremor: float | None, level: str | None, fusion_mode: str = "model") -> tuple[list[str], int | None]:
    """The five OLED lines and which one to invert (the level line for urgent/critical)."""
    head = f"{node}  MQTT {'OK' if mqtt_ok else '--'}" + ("  RULE" if fusion_mode == "rule" else "")
    if sensor is None:
        sensor_line = "Sensor: n/a"
    elif not sensor.get("finger"):
        sensor_line = "Sensor: no finger"
    elif sensor.get("hr") is None:
        sensor_line = "Sensor: reading..."
    else:
        spo2 = sensor.get("spo2")
        sensor_line = f"Sensor HR {sensor['hr']} SpO2 {spo2 if spo2 is not None else '--'}"
    # "Bio:" (not "Model bio:") so "Bio: REPLAY exertion" fits the 21-character line.
    if bio_mode.startswith("replay:"):
        bio_line = f"Bio: REPLAY {bio_mode.split(':', 1)[1]}"
    else:
        bio_line = f"Bio: {bio_mode.upper()}"
    feat_line = ("Gesture --  Tr --" if gesture is None
                 else f"Gesture {gesture:.2f} Tr {tremor:.3f}")
    level_line = f"LEVEL: {(level or 'starting').upper()}"
    lines = [line[:MAX_CHARS] for line in (head, sensor_line, bio_line, feat_line, level_line)]
    invert = 4 if level in ("urgent", "critical") else None
    return lines, invert


class _ErrorThrottle:
    def __init__(self, every_s: float = 60.0):
        self.every_s = every_s
        self._last = -1e9

    def log(self, msg: str, *args) -> None:
        now = time.monotonic()
        if now - self._last >= self.every_s:
            self._last = now
            log.warning(msg, *args)


class MockOled:
    """Prints the screen to the log whenever its content changes (laptop / --mock-io)."""

    kind = "mock"

    def __init__(self):
        self._last = None

    def show(self, lines: list[str], invert_line: int | None = None) -> None:
        key = (tuple(lines), invert_line)
        if key == self._last:
            return
        self._last = key
        rendered = " | ".join(f"[{t}]" if i == invert_line else t for i, t in enumerate(lines))
        log.info("OLED  %s", rendered)

    def clear(self) -> None:
        self._last = None

    def close(self) -> None:
        pass


class Oled:
    kind = "oled"

    def __init__(self, driver: str = "ssd1306", address: int = 0x3C, port: int = 1):
        from luma.core.interface.serial import i2c
        from luma.core.render import canvas
        from luma.oled import device as devices
        if driver not in ("ssd1306", "sh1106"):
            raise ValueError(f"OLED driver must be ssd1306 or sh1106, got {driver!r}")
        self._canvas = canvas
        self._device = getattr(devices, driver)(i2c(port=port, address=address), width=128, height=64)
        self._errors = _ErrorThrottle()
        self._last = None

    def show(self, lines: list[str], invert_line: int | None = None) -> None:
        key = (tuple(lines), invert_line)
        if key == self._last:
            return
        try:
            with self._canvas(self._device) as draw:
                for i, text in enumerate(lines[:MAX_LINES]):
                    y = i * 12 + 2
                    if i == invert_line:
                        draw.rectangle((0, y - 1, 127, y + 10), outline="white", fill="white")
                        draw.text((2, y), text, fill="black")
                    else:
                        draw.text((2, y), text, fill="white")
            self._last = key
        except Exception as e:
            self._errors.log("OLED write failed (I2C): %s", e)

    def clear(self) -> None:
        try:
            self._device.clear()
        except Exception as e:
            self._errors.log("OLED clear failed: %s", e)

    def close(self) -> None:
        self.clear()


def make_oled(enabled: bool, mock: bool, driver: str = "ssd1306"):
    """Real OLED, mock, or None. Never raises: failures are logged and the OLED is disabled."""
    if mock:
        return MockOled()
    if not enabled:
        return None
    try:
        return Oled(driver)
    except Exception as e:
        log.warning("OLED disabled: %s", e)
        return None
