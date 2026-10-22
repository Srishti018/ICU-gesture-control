"""MJPEG camera preview with landmarks and g, for placing the camera (setup only, not during the demo).

Usage: .venv/bin/python -m node.tools.preview [--port 8080] [--host 0.0.0.0]
Open http://localhost:8080 (laptop) or http://icu-pi.local:8080 (Pi). Nothing is saved.
"""

import argparse
import sys
import time

from node.tools._common import run_locked, setup_logging

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>ICU node camera preview</title>
<style>body{background:#111;color:#eee;font-family:system-ui,sans-serif;text-align:center;margin:16px}
img{width:min(96vw,960px);image-rendering:pixelated;border:1px solid #444}</style></head>
<body><h1>Camera preview</h1><p>Raised open hand should fill about a quarter to a third of the picture height.
Green lines = detected hand; g = gesture score for this frame.</p><img src="/stream" alt="camera stream"></body></html>"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--camera", choices=["usb", "picam"], default="usb")
    p.add_argument("--index", type=int, default=0)
    args = p.parse_args(argv)
    setup_logging()

    def run():
        import cv2
        from flask import Flask, Response
        from node.settings import Settings
        from node.vision.camera import CameraError
        from node.vision.features import VisionFeatureExtractor
        from node.vision.hands import TrackerError
        vision = VisionFeatureExtractor(Settings.load(camera_kind=args.camera, camera_index=args.index))
        try:
            vision.start()
        except (CameraError, TrackerError) as e:
            print(f"VISION: {e}", file=sys.stderr)
            return 4
        app = Flask(__name__)

        @app.get("/")
        def index():
            return PAGE

        @app.get("/stream")
        def stream():
            def frames():
                while True:
                    img = vision.snapshot()
                    if img is not None:
                        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        if ok:
                            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n"
                    time.sleep(0.1)
            return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

        print(f"preview on http://localhost:{args.port} (Ctrl+C to stop; it holds the camera)", flush=True)
        try:
            app.run(host=args.host, port=args.port, debug=False, use_reloader=False, threaded=True)
        finally:
            vision.stop()
        return 0

    return run_locked("preview", run)


if __name__ == "__main__":
    sys.exit(main())
