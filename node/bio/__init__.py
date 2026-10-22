"""Biosignal sources for the node (docs/NODE_INTERFACES.md §B.3).

live.py is imported lazily so replay and manual work on a laptop without I2C.
"""


class BioUnavailable(Exception):
    """Raised by make_bio_source() or start() when the requested mode can't run."""


class BioSource:
    kind: str = ""

    def start(self) -> None:
        raise NotImplementedError

    def window(self) -> dict:
        """{"hr", "spo2", "hr_delta", "finger", "source", "quality"} over the last ~3 s."""
        raise NotImplementedError

    def baseline_hr(self) -> int | None:
        raise NotImplementedError

    def stop(self) -> None:
        pass


def empty_window(source: str) -> dict:
    return {"hr": None, "spo2": None, "hr_delta": None, "finger": False, "source": source, "quality": 0.0}


def make_bio_source(mode: str, settings=None, **kw) -> BioSource:
    if mode == "live":
        from node.bio.live import LiveBio
        return LiveBio(settings, **kw)
    if mode in ("replay:rest", "replay:exertion"):
        from node.bio.replay import ReplayBio
        return ReplayBio(mode.split(":", 1)[1], **kw)
    if mode == "manual":
        from node.bio.manual import ManualBio
        return ManualBio(**kw)
    raise ValueError(f"unknown bio mode {mode!r} (use live, replay:rest, replay:exertion or manual)")
