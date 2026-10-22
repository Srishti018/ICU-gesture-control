"""Camera: OpenCV USB webcam or Pi Camera Module (picamera2), same interface."""

import logging
import sys

log = logging.getLogger("node.camera")

MAX_FAILED_READS = 30


class CameraError(Exception):
    pass


def list_hint() -> str:
    if sys.platform.startswith("linux"):
        return "List cameras with: ls /dev/video*  (or: v4l2-ctl --list-devices)"
    return "Check the camera in the system settings and try --camera-index 1"


class Camera:
    def __init__(self, kind: str = "usb", index: int = 0, width: int = 640, height: int = 480, fps: int = 30):
        if kind not in ("usb", "picam"):
            raise ValueError(f"camera kind must be usb or picam, got {kind!r}")
        self.kind, self.index = kind, index
        self.width, self.height, self.fps = width, height, fps
        self._cap = None
        self._picam = None
        self._failures = 0

    def open(self) -> "Camera":
        if self.kind == "usb":
            import cv2
            backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
            cap = cv2.VideoCapture(self.index, backend)
            if not cap.isOpened():
                cap.release()
                raise CameraError(f"cannot open USB camera index {self.index}. {list_hint()}; "
                                  "on a laptop, check the camera key/privacy switch.")
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ok, _ = cap.read()
            if not ok:
                cap.release()
                raise CameraError(f"USB camera index {self.index} opened but returns no frames "
                                  f"(another program may be using it). {list_hint()}")
            self._cap = cap
            log.info("camera: USB index %d, %dx%d", self.index,
                     int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        else:
            try:
                from picamera2 import Picamera2
            except ImportError as e:
                raise CameraError("picamera2 is not installed (sudo apt-get install -y python3-picamera2 "
                                  "--no-install-recommends)") from e
            try:
                cam = Picamera2()
                cam.configure(cam.create_video_configuration(main={"size": (self.width, self.height),
                                                                   "format": "RGB888"}))
                cam.start()
            except Exception as e:
                raise CameraError(f"cannot start the Pi Camera Module: {e} "
                                  "(check with: rpicam-hello --list-cameras)") from e
            self._picam = cam
            log.info("camera: Pi Camera Module, %dx%d", self.width, self.height)
        return self

    def read(self):
        """(ok, frame_bgr). Raises CameraError after 30 failed reads in a row."""
        if self._cap is not None:
            ok, frame = self._cap.read()
        elif self._picam is not None:
            try:
                frame, ok = self._picam.capture_array(), True  # RGB888 arrives in BGR order
            except Exception:
                frame, ok = None, False
        else:
            raise CameraError("camera is not open")
        if ok:
            self._failures = 0
            return True, frame
        self._failures += 1
        if self._failures >= MAX_FAILED_READS:
            raise CameraError(f"camera ({self.kind} {self.index}) failed {MAX_FAILED_READS} reads in a row "
                              "(unplugged or in use by another program)")
        return False, None

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._picam is not None:
            try:
                self._picam.stop()
                self._picam.close()
            finally:
                self._picam = None
