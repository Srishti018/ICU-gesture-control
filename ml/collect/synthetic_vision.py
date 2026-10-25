"""Local stand-in for Role A's VisionFeatureExtractor (docs/NODE_INTERFACES.md §B.2).

For dry runs of the collector without a camera only. The session tells it the
current scenario (set_scenario) so the fake values look like that scenario.
Data recorded with it is tagged and must never be used for training.
"""

import random

from ml.schema import GESTURE_SCENARIOS, SCENARIOS, is_gesture


class SyntheticVision:
    is_synthetic = True

    def __init__(self, settings=None, seed: int = 0):
        self._rng = random.Random(seed)
        self._scenario = "S1"
        self._running = False

    def set_scenario(self, code: str) -> None:
        self._scenario = code if code in SCENARIOS or code in GESTURE_SCENARIOS else "S1"

    def start(self) -> None:
        self._running = True

    def window(self) -> dict:
        rng = self._rng
        gesture = is_gesture(self._scenario)
        hand = gesture or (self._scenario != "N_NOHAND" and rng.random() < 0.9)
        conf = rng.uniform(0.82, 0.95) if gesture else rng.uniform(0.0, 0.2)
        n_frames = rng.randint(27, 33)
        return {
            "hand_present": hand,
            "gesture_conf": round(conf if hand else 0.0, 3),
            "tremor": round(rng.uniform(0.005, 0.03), 3),
            "n_frames": n_frames,
            "n_hand_frames": n_frames if hand else 0,
            "fps": round(n_frames / 3, 1),
        }

    def stop(self) -> None:
        self._running = False
