"""ManualBio: reference values typed by the operator, interpolated over a trial.

Used only by the data collector, when the live sensor is not reliable.
"""

from node.bio import BioSource, empty_window


class ManualBio(BioSource):
    kind = "manual"

    def __init__(self, seconds: float = 30):
        self.seconds = float(seconds)
        self._baseline = None
        self._start = None
        self._end = None

    def start(self) -> None:
        pass

    def set_baseline(self, hr) -> None:
        self._baseline = int(round(hr))

    def baseline_hr(self) -> int | None:
        return self._baseline

    def set_start(self, hr, spo2, seconds: float | None = None) -> None:
        """Reference reading at the start of a trial; clears the previous end reading."""
        if seconds is not None:
            self.seconds = float(seconds)
        self._start = (float(hr), float(spo2))
        self._end = None

    def set_end(self, hr, spo2) -> None:
        self._end = (float(hr), float(spo2))

    def ready(self) -> bool:
        return self._start is not None and self._end is not None

    def value_at(self, t: float) -> tuple[float, float]:
        """Linearly interpolated (hr, spo2) at t seconds after the trial start."""
        if not self.ready():
            raise RuntimeError("set_start() and set_end() must be called first")
        frac = min(1.0, max(0.0, t / self.seconds)) if self.seconds > 0 else 1.0
        (h0, s0), (h1, s1) = self._start, self._end
        return h0 + (h1 - h0) * frac, s0 + (s1 - s0) * frac

    def window_for(self, t_start: float, t_end: float) -> dict:
        """Mean of the interpolated values between t_start and t_end (seconds into the trial)."""
        hr, spo2 = self.value_at((t_start + t_end) / 2)  # mean of a linear segment = its midpoint
        hr, spo2 = int(round(hr)), int(round(spo2))
        return {"hr": hr, "spo2": spo2,
                "hr_delta": hr - self._baseline if self._baseline is not None else None,
                "finger": True, "source": "manual", "quality": 1.0}

    def per_second(self) -> list[dict]:
        """One interpolated row per second of the trial (for the _bio.csv file)."""
        rows = []
        for t in range(int(round(self.seconds))):
            hr, spo2 = self.value_at(t)
            rows.append({"t_s": t, "hr": int(round(hr)), "spo2": int(round(spo2)), "finger": 1, "quality": 1.0})
        return rows

    def window(self) -> dict:
        if not self.ready():
            return empty_window("manual")
        return self.window_for(0, self.seconds)
