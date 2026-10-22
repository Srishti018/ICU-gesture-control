"""MediaPipe hand tracker -> (21, 2) landmark pixels in the 320x240 inference image.

Prefers the Tasks HandLandmarker (VIDEO mode); falls back to mp.solutions.hands
(model_complexity=0) when the Tasks API is unavailable or fails. Newer MediaPipe
releases (1.x) only ship the Tasks API; older Pi wheels may only have solutions.
"""

import logging
from pathlib import Path
import time

import numpy as np

log = logging.getLogger("node.hands")

INFER_W, INFER_H = 320, 240
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/"
             "float16/latest/hand_landmarker.task")


class TrackerError(Exception):
    pass


class HandTracker:
    def __init__(self, model_path=None, api: str = "auto", infer_size=(INFER_W, INFER_H)):
        import cv2
        import mediapipe as mp
        self._cv2, self._mp = cv2, mp
        self.infer_w, self.infer_h = infer_size
        self._last_ts = 0
        self.api = None
        errors = []
        if api in ("auto", "tasks"):
            try:
                self._init_tasks(Path(model_path) if model_path else None)
                self.api = "tasks"
            except TrackerError as e:
                errors.append(str(e))
                if api == "tasks":
                    raise
        if self.api is None and api in ("auto", "solutions"):
            if not hasattr(mp, "solutions"):
                errors.append(f"mediapipe {mp.__version__} has no mp.solutions")
            else:
                self._hands = mp.solutions.hands.Hands(static_image_mode=False, max_num_hands=1, model_complexity=0,
                                                       min_detection_confidence=0.5, min_tracking_confidence=0.5)
                self.api = "solutions"
        if self.api is None:
            raise TrackerError("no usable MediaPipe hand tracker: " + "; ".join(errors))
        log.info("hand tracker: MediaPipe %s (%s API, inference %dx%d)", mp.__version__, self.api,
                 self.infer_w, self.infer_h)

    def _init_tasks(self, model_path):
        mp = self._mp
        if not hasattr(mp, "tasks"):
            raise TrackerError(f"mediapipe {mp.__version__} has no Tasks API")
        if model_path is None or not model_path.exists():
            raise TrackerError(f"hand model not found at {model_path}; download it with: "
                               f"mkdir -p {model_path.parent if model_path else '~/icu-data/models'} && "
                               f"curl -fL -o {model_path or '~/icu-data/models/hand_landmarker.task'} {MODEL_URL}")
        from mediapipe.tasks.python import BaseOptions, vision
        opts = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO, num_hands=1,
            min_hand_detection_confidence=0.5, min_hand_presence_confidence=0.5, min_tracking_confidence=0.5)
        try:
            self._landmarker = vision.HandLandmarker.create_from_options(opts)
        except Exception as e:
            raise TrackerError(f"Tasks HandLandmarker failed to start: {e}") from e

    def prepare(self, frame_bgr):
        small = self._cv2.resize(frame_bgr, (self.infer_w, self.infer_h)) \
            if frame_bgr.shape[1] != self.infer_w or frame_bgr.shape[0] != self.infer_h else frame_bgr
        return small, self._cv2.cvtColor(small, self._cv2.COLOR_BGR2RGB)

    def process(self, frame_bgr):
        """Returns (landmarks (21,2) float pixels or None, score, small_bgr)."""
        small, rgb = self.prepare(frame_bgr)
        scale = np.array([self.infer_w, self.infer_h], dtype=float)
        if self.api == "tasks":
            ts = max(self._last_ts + 1, int(time.monotonic() * 1000))  # strictly increasing
            self._last_ts = ts
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
            result = self._landmarker.detect_for_video(image, ts)
            if not result.hand_landmarks:
                return None, 0.0, small
            pts = np.array([[lm.x, lm.y] for lm in result.hand_landmarks[0]], dtype=float) * scale
            score = float(result.handedness[0][0].score) if result.handedness else 1.0
            return pts, score, small
        result = self._hands.process(rgb)
        if not result.multi_hand_landmarks:
            return None, 0.0, small
        pts = np.array([[lm.x, lm.y] for lm in result.multi_hand_landmarks[0].landmark], dtype=float) * scale
        score = float(result.multi_handedness[0].classification[0].score) if result.multi_handedness else 1.0
        return pts, score, small

    def close(self) -> None:
        try:
            if self.api == "tasks":
                self._landmarker.close()
            elif self.api == "solutions":
                self._hands.close()
        except Exception:
            pass
