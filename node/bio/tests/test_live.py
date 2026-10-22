"""LiveBio with a fake driver (no hardware) and the hardware-lock stand-in."""

import time

import numpy as np
import pytest

from node.bio import BioUnavailable
from node.bio.live import LiveBio
from node.bio.max30100 import SensorError

PARAMS = {"red_code": 8, "ir_code": 15, "finger_ir_min": 20000}


class FakeDriver:
    """Feeds a 72 bpm synthetic PPG, 16 samples per poll (4x real time)."""

    def __init__(self, bpm=72, dc_ir=40000.0, fail_open=False, fail_reads=False):
        self.bpm, self.dc_ir = bpm, dc_ir
        self.fail_open, self.fail_reads = fail_open, fail_reads
        self.i = 0
        self.closed = self.shut = False
        self.rng = np.random.default_rng(0)

    def open(self):
        if self.fail_open:
            raise SensorError("MAX30100 not found or wrong part ID: 0x00")
        return self

    def configure(self):
        pass

    def read_samples(self):
        if self.fail_reads:
            raise OSError("I2C read failed")
        t = (self.i + np.arange(16)) / 100
        self.i += 16
        f = self.bpm / 60
        wave = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t + 0.5)
        ir = self.dc_ir + 400 * wave + self.rng.normal(0, 10, 16)
        red = 0.75 * self.dc_ir + 0.6 * 0.75 * 400 * wave + self.rng.normal(0, 10, 16)
        return list(zip(ir.astype(int).tolist(), red.astype(int).tolist()))

    def shutdown(self):
        self.shut = True

    def close(self):
        self.closed = True


def wait_for(fn, timeout=6.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.1)
    return fn()


def test_live_window_reports_hr_and_delta():
    driver = FakeDriver(bpm=72)
    bio = LiveBio(params=PARAMS, driver=driver)
    bio.start()
    try:
        w = wait_for(lambda: (x := bio.window())["hr"] is not None and x)
        assert w and abs(w["hr"] - 72) <= 2, w
        assert w["finger"] is True and w["source"] == "live"
        assert w["hr_delta"] is None            # no baseline yet
        assert 90 <= w["spo2"] <= 100
        bio.set_baseline(70)
        w = bio.window()
        assert w["hr_delta"] == w["hr"] - 70
        assert bio.baseline_hr() == 70
    finally:
        bio.stop()
    assert driver.shut and driver.closed


def test_calibrate_baseline():
    bio = LiveBio(params=PARAMS, driver=FakeDriver(bpm=66))
    bio.start()
    try:
        wait_for(lambda: bio.window()["hr"] is not None)
        base = bio.calibrate_baseline(seconds=2)
        assert abs(base - 66) <= 2
    finally:
        bio.stop()


def test_no_finger_gives_none():
    bio = LiveBio(params=PARAMS, driver=FakeDriver(dc_ir=500.0))
    bio.start()
    try:
        time.sleep(2.5)
        w = bio.window()
        assert w["hr"] is None and w["finger"] is False and w["quality"] == 0
    finally:
        bio.stop()


def test_missing_sensor_raises_bio_unavailable():
    with pytest.raises(BioUnavailable, match="wrong part ID"):
        LiveBio(params=PARAMS, driver=FakeDriver(fail_open=True)).start()


def test_repeated_i2c_errors_mark_failed():
    bio = LiveBio(params=PARAMS, driver=FakeDriver(fail_reads=True))
    bio.start()
    try:
        assert wait_for(lambda: bio.failed, timeout=3)
        assert bio.window()["hr"] is None
    finally:
        bio.stop()


def test_hardware_lock_busy(tmp_path):
    from node.bio import hwlock_compat
    if hwlock_compat.USING_ROLE_A_LOCK:
        pytest.skip("Role A's node.hwlock is in use; it has its own tests")
    path = str(tmp_path / "lock")
    with hwlock_compat.HardwareLock("first", path=path):
        with pytest.raises(hwlock_compat.HardwareBusy, match="first"):
            with hwlock_compat.HardwareLock("second", path=path):
                pass
    with hwlock_compat.HardwareLock("third", path=path):
        pass
