"""SyntheticVision: same interface as VisionFeatureExtractor, no camera. For tests and the `g` key."""

import random
import threading


class SyntheticVision:
    is_synthetic = True

    def __init__(self, settings=None, seed: int | None = None):
        self._rng = random.Random(seed)
        self._gesture = False
        self._lock = threading.Lock()
        self.error = None

    def set_gesture(self, on: bool) -> None:
        with self._lock:
            self._gesture = bool(on)

    def toggle_gesture(self) -> bool:
        with self._lock:
            self._gesture = not self._gesture
            return self._gesture

    @property
    def gesture(self) -> bool:
        with self._lock:
            return self._gesture

    def start(self) -> None:
        pass

    def window(self) -> dict:
        rng = self._rng
        conf = rng.uniform(0.85, 0.95) if self.gesture else rng.uniform(0.0, 0.10)
        n = rng.randint(27, 33)
        return {"hand_present": True, "gesture_conf": round(conf, 3), "tremor": round(rng.uniform(0.005, 0.02), 3),
                "n_frames": n, "n_hand_frames": n, "fps": round(n / 3, 1)}

    def stop(self) -> None:
        pass
