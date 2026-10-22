"""VisionFeatureExtractor (docs/NODE_INTERFACES.md §B.2): camera -> MediaPipe -> 3-s window features."""

from collections import deque
import json
import logging
import threading
import time

import numpy as np

from node.vision import geometry

log = logging.getLogger("node.vision")

HAND_CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
                    (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]
MAX_BUFFER = 600  # frames kept between window() calls (> 3 s at any realistic fps)


def load_params(path) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        log.warning("gesture params %s not found; using plan defaults", path)
        return dict(geometry.DEFAULT_PARAMS)
    return {k: float(data[k]) for k in geometry.DEFAULT_PARAMS if k in data} | \
        {k: v for k, v in geometry.DEFAULT_PARAMS.items() if k not in data}


def summarise(frames: list, elapsed: float) -> dict:
    """Window features from per-frame records (t, hand, g, tip, wrist, s). Pure; unit-tested."""
    n = len(frames)
    if n == 0:
        return {"hand_present": False, "gesture_conf": 0.0, "tremor": 0.0, "n_frames": 0, "n_hand_frames": 0,
                "fps": 0.0}
    hand = [f for f in frames if f[1]]
    tips = [f[3] for f in hand]
    wrists = [f[4] for f in hand]
    sizes = [f[5] for f in hand]
    return {
        "hand_present": len(hand) / n >= 0.5,
        "gesture_conf": round(float(np.mean([f[2] if f[1] else 0.0 for f in frames])), 3),
        "tremor": round(geometry.tremor(tips, wrists, sizes), 3),
        "n_frames": n,
        "n_hand_frames": len(hand),
        "fps": round(n / elapsed, 1) if elapsed > 0 else 0.0,
    }


class VisionFeatureExtractor:
    is_synthetic = False

    def __init__(self, settings, camera=None, tracker=None):
        self.settings = settings
        self.params = load_params(settings.params_path)
        self._camera = camera
        self._tracker = tracker
        self._buf = deque(maxlen=MAX_BUFFER)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._last_window_t = None
        self._latest = None          # (small_bgr, landmarks, g, details)
        self.error = None            # set if the capture thread stops on a camera error
        self.frames_total = 0
        self.infer_ms = deque(maxlen=100)

    def start(self) -> None:
        from node.vision.camera import Camera
        from node.vision.hands import HandTracker
        if self._camera is None:
            s = self.settings
            self._camera = Camera(s.camera_kind, s.camera_index, s.camera_width, s.camera_height)
        self._camera.open()
        if self._tracker is None:
            try:
                self._tracker = HandTracker(self.settings.hand_model_path)
            except Exception:
                self._camera.close()
                raise
        self._last_window_t = time.monotonic()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="vision", daemon=True)
        self._thread.start()

    def process_frame(self, frame_bgr, t: float) -> None:
        a = time.perf_counter()
        pts, _score, small = self._tracker.process(frame_bgr)
        self.infer_ms.append((time.perf_counter() - a) * 1000)
        if pts is not None:
            g, details = geometry.frame_gesture_score(pts, self.params)
            hand = not details.get("too_small", False)
        else:
            g, details, hand = 0.0, {}, False
        rec = (t, hand, g if hand else 0.0, pts[8] if hand else None, pts[0] if hand else None,
               details.get("s", 0.0) if hand else 0.0)
        with self._lock:
            self._buf.append(rec)
            self._latest = (small, pts if hand else None, g if hand else 0.0, details)
        self.frames_total += 1

    def _run(self) -> None:
        from node.vision.camera import CameraError
        while not self._stop.is_set():
            try:
                ok, frame = self._camera.read()
            except CameraError as e:
                self.error = str(e)
                log.error("VISION STOPPED: %s", e)
                return
            if not ok:
                continue
            try:
                self.process_frame(frame, time.monotonic())
            except Exception as e:  # a bad frame must not kill the thread
                log.warning("frame processing failed: %s", e)

    def window(self) -> dict:
        now = time.monotonic()
        with self._lock:
            frames = list(self._buf)
            self._buf.clear()
        elapsed = now - (self._last_window_t or now)
        self._last_window_t = now
        return summarise(frames, elapsed)

    def latest(self):
        """(landmarks or None, g, details) of the most recent frame, for vision_probe."""
        with self._lock:
            if self._latest is None:
                return None, 0.0, {}
            _small, pts, g, details = self._latest
            return pts, g, details

    def snapshot(self):
        """Latest inference image (BGR) with landmarks and g drawn, or None."""
        import cv2
        with self._lock:
            if self._latest is None:
                return None
            small, pts, g, _ = self._latest
            img = small.copy()
        if pts is not None:
            for a, b in HAND_CONNECTIONS:
                cv2.line(img, tuple(int(v) for v in pts[a]), tuple(int(v) for v in pts[b]), (0, 220, 0), 1)
            for p in pts:
                cv2.circle(img, (int(p[0]), int(p[1])), 2, (0, 0, 255), -1)
        cv2.putText(img, f"g={g:.2f}", (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        return img

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self._camera:
            self._camera.close()
        if self._tracker:
            self._tracker.close()
