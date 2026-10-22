"""ICU Fusion bed node: vision + biosignals -> fusion model -> MQTT (docs/contracts.md).

Run from the repo root:  .venv/bin/python -m node.main --help
"""

import argparse
import logging
from pathlib import Path
import signal
import sys
import threading
import time

from node.control import HELP, Control
from node.fusion_adapter import load_fusion
from node.hwlock import EXIT_BUSY, HardwareBusy, HardwareLock
from node.local_io.buzzer import make_buzzer
from node.local_io.oled import format_lines, make_oled
from node.mqtt_pub import NodePublisher
from node.payload import level_of, round_probs, should_publish_alert, status_payload
from node.runlog import RunLog
from node.settings import Settings, SettingsError

log = logging.getLogger("node")

EXIT_SETTINGS, EXIT_VISION, EXIT_BIO = 2, 4, 5
BIO_REUSE_S = 10.0
DEFAULT_SPO2 = 97
BASELINE_S = 60


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="python -m node.main",
        description="ICU Fusion bed node: camera + MediaPipe gesture/tremor, biosignals (replay or live), "
                    "3-class fusion, MQTT publishing with heartbeat and Last Will.",
        epilog=HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--node", help="node id and MQTT user (default: NODE_ID from .env, else bed1)")
    p.add_argument("--vision", choices=["camera", "synthetic"], default="camera",
                   help="camera = real MediaPipe on the webcam; synthetic = fake values, toggled with g "
                        "(default: camera)")
    p.add_argument("--camera", choices=["usb", "picam"], default="usb",
                   help="USB webcam (OpenCV) or Pi Camera Module (default: usb)")
    p.add_argument("--camera-index", type=int, default=0, help="USB camera index, /dev/videoN (default: 0)")
    p.add_argument("--bio", choices=["replay:rest", "replay:exertion", "live"], default="replay:rest",
                   help="biosignals fed to the model (default: replay:rest; keys r/x/l switch)")
    p.add_argument("--display-bio", choices=["live", "none"], default=None,
                   help="live sensor shown on the OLED only (default: live on the Pi, none elsewhere)")
    p.add_argument("--fusion", choices=["model", "rule"], default="model",
                   help="model = ml/models/model.json (falls back to the rule if missing); rule = fixed rule "
                        "(default: model)")
    p.add_argument("--no-oled", action="store_true", help="disable the OLED")
    p.add_argument("--no-buzzer", action="store_true", help="disable the buzzer")
    p.add_argument("--mock-io", action="store_true",
                   help="print what the OLED would show and the beep patterns to the log (laptop)")
    p.add_argument("--oled-driver", choices=["ssd1306", "sh1106"], default="ssd1306", help="OLED chip")
    p.add_argument("--broker", help="broker host (default: BROKER_HOST from .env)")
    p.add_argument("--broker-port", type=int, help="broker port (default: BROKER_PORT from .env, else 1883)")
    p.add_argument("--log-dir", help="folder for node.log and run_YYYYMMDD.csv (default: ~/icu-data/logs)")
    p.add_argument("--params", help="gesture parameters JSON (default: node/vision/gesture_params.json)")
    p.add_argument("--model", help="fusion model JSON (default: ml/models/model.json)")
    return p.parse_args(argv)


def setup_logging(log_dir: Path) -> None:
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(fmt)
    root.addHandler(out)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "node.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(fh)
    except OSError as e:
        root.warning("cannot write %s/node.log (%s); logging to the terminal only", log_dir, e)
    for noisy in ("werkzeug", "absl"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class Node:
    def __init__(self, args, settings: Settings):
        self.args = args
        self.s = settings
        self.quit = threading.Event()
        self.lock = None
        self.pub = None
        self.vision = None
        self.bio = None
        self.bio_mode = args.bio
        self.display_bio = None
        self.fusion = None
        self.oled = None
        self.buzzer = None
        self.runlog = RunLog(settings.log_dir)
        self.prev_level = "routine"
        self.last = {}                 # latest window, for the OLED and `s`
        self.last_bio = None           # (time, bio window) of the last valid reading
        self.last_spo2 = None
        self._bio_lock = threading.Lock()

    # --- startup ------------------------------------------------------------------------

    def needs_hardware_lock(self) -> bool:
        a = self.args
        return a.vision == "camera" or a.bio == "live" or self.display_mode() == "live" or \
            (self.s.on_pi and not a.mock_io and not (a.no_oled and a.no_buzzer))

    def display_mode(self) -> str:
        return self.args.display_bio or ("live" if self.s.on_pi else "none")

    def start(self) -> None:
        from node.bio import BioUnavailable, make_bio_source
        a = self.args
        if self.needs_hardware_lock():
            self.lock = HardwareLock("node.main")
            self.lock.__enter__()
        self.fusion = load_fusion(self.s, a.fusion)

        self.pub = NodePublisher(self.s)
        self.pub.start()
        if not self.pub.wait_connected(5):
            log.warning("MQTT not connected yet (broker %s:%s); will keep retrying",
                        self.s.broker_host, self.s.broker_port)

        if a.vision == "camera":
            from node.vision.features import VisionFeatureExtractor
            self.vision = VisionFeatureExtractor(self.s)
        else:
            from node.vision.synthetic import SyntheticVision
            self.vision = SyntheticVision(self.s)
        self.vision.start()

        self.bio = self._make_bio(a.bio, make_bio_source)
        if self.display_mode() == "live" and a.bio != "live":
            try:
                self.display_bio = make_bio_source("live", self.s, take_lock=False)
                self.display_bio.start()
            except BioUnavailable as e:
                log.warning("live sensor for the OLED unavailable: %s", e)
                self.display_bio = None

        oled_on = self.s.on_pi and not a.no_oled
        buzzer_on = self.s.on_pi and not a.no_buzzer
        self.oled = make_oled(oled_on or (a.mock_io and not a.no_oled), a.mock_io and not a.no_oled, a.oled_driver)
        self.buzzer = make_buzzer(buzzer_on or (a.mock_io and not a.no_buzzer), a.mock_io and not a.no_buzzer)

        Control({"r": lambda: self.switch_bio("replay:rest"), "x": lambda: self.switch_bio("replay:exertion"),
                 "l": lambda: self.switch_bio("live"), "g": self.toggle_gesture, "s": self.print_status,
                 "q": self.quit.set, "h": lambda: print(HELP, flush=True)}).start()
        self.pub.start_heartbeat()
        threading.Thread(target=self._oled_loop, name="oled", daemon=True).start()

    def _make_bio(self, mode: str, make_bio_source):
        kw = {"replay_dir": self.s.replay_dir} if mode.startswith("replay:") else {"take_lock": False}
        bio = make_bio_source(mode, self.s, **kw)
        bio.start()
        if mode == "live":
            log.info("calibrating the resting baseline for %d s; keep the finger on the sensor", BASELINE_S)
            bio.calibrate_baseline(BASELINE_S)
            log.info("baseline HR %s bpm", bio.baseline_hr())
        if getattr(bio, "meta", {}).get("source") == "synthetic-placeholder":
            log.warning("replay %s is a SYNTHETIC PLACEHOLDER (not a real recording); replace before the demo",
                        mode)
        return bio

    def summary(self) -> str:
        a, s = self.args, self.s
        oled = getattr(self.oled, "kind", "off")
        buzzer = getattr(self.buzzer, "kind", "off")
        vision = (f"camera ({a.camera} index {a.camera_index}, {getattr(getattr(self.vision, '_tracker', None), 'api', '?')} API)"
                  if a.vision == "camera" else "synthetic (press g to toggle the gesture)")
        lines = [
            "=" * 64,
            f" ICU Fusion node {s.node_id}",
            f"  broker   {s.broker_host}:{s.broker_port} as {s.node_user} "
            f"({'connected' if self.pub.connected else 'connecting...'})",
            f"  vision   {vision}",
            f"  bio      {self.bio_mode} (model input); OLED sensor: {self.display_mode()}",
            f"  fusion   {self.fusion.mode}" + ("" if self.fusion.mode == "model" else " (fixed rule)"),
            f"  OLED     {oled}    buzzer {buzzer}",
            f"  logs     {s.log_dir}/node.log, {self.runlog.path().name}",
            "  keys     r rest · x exertion · l live · g gesture (synthetic) · s status · q quit · h help",
            "=" * 64,
        ]
        return "\n".join(lines)

    # --- controls ---------------------------------------------------------------------------

    def switch_bio(self, mode: str) -> None:
        from node.bio import BioUnavailable, make_bio_source
        if mode == "live" and self.args.bio != "live" and self.display_bio is None:
            print("live sensor not available on this node (start with --bio live on the Pi)", flush=True)
            return
        try:
            if mode == "live":
                new = self.display_bio if self.args.bio != "live" else self.bio
                if new is None or new.baseline_hr() is None:
                    print("live sensor has no baseline yet (start with --bio live to calibrate it)", flush=True)
                    return
            else:
                new = self._make_bio(mode, make_bio_source)
        except BioUnavailable as e:
            print(f"cannot switch to {mode}: {e}", flush=True)
            return
        with self._bio_lock:
            old, self.bio, self.bio_mode = self.bio, new, mode
            self.last_bio = None
        if old is not new and old is not self.display_bio and getattr(old, "kind", "") == "replay":
            old.stop()
        log.info("model biosignals -> %s", mode)

    def toggle_gesture(self) -> None:
        if not hasattr(self.vision, "toggle_gesture"):
            print("g only works with --vision synthetic", flush=True)
            return
        on = self.vision.toggle_gesture()
        log.info("synthetic gesture %s", "ON" if on else "OFF")

    def print_status(self) -> None:
        w = self.last
        print(f"status: MQTT {'connected' if self.pub.connected else 'DISCONNECTED'} · level {self.prev_level} · "
              f"bio {self.bio_mode} · fusion {self.fusion.mode} · g={w.get('gesture_conf')} tr={w.get('tremor')} "
              f"hr={w.get('hr')} Δ{w.get('hr_delta')} spo2={w.get('spo2')} · {w.get('fps', 0)}fps", flush=True)

    # --- window loop --------------------------------------------------------------------------

    def bio_window(self) -> tuple[dict, str]:
        """Model biosignals for this window, with the §3.3 fallback when there's no valid reading."""
        with self._bio_lock:
            bio, mode = self.bio, self.bio_mode
        b = bio.window()
        now = time.monotonic()
        if b.get("hr") is not None and b.get("hr_delta") is not None:
            self.last_bio = (now, b)
            if b.get("spo2") is not None:
                self.last_spo2 = b["spo2"]
            return b, mode
        if self.last_bio and now - self.last_bio[0] < BIO_REUSE_S:
            return self.last_bio[1], mode
        base = bio.baseline_hr() or 75
        log.warning("BIO MISSING (%s): using baseline HR %s, hr_delta 0", mode, base)
        return {"hr": base, "hr_delta": 0, "spo2": b.get("spo2") or self.last_spo2 or DEFAULT_SPO2,
                "finger": False, "source": b.get("source", "live"), "quality": 0.0}, mode

    def step(self) -> None:
        v = self.vision.window()
        b, mode = self.bio_window()
        feats = {"gesture_conf": v["gesture_conf"], "tremor": v["tremor"],
                 "hr_delta": b["hr_delta"], "spo2": b["spo2"] if b["spo2"] is not None else DEFAULT_SPO2}
        p = round_probs(self.fusion.predict_proba(feats))
        level = level_of(p)
        bio_source = "replay" if mode.startswith("replay:") else "live"
        payload = status_payload(self.s.node_id, level, p, feats, b["hr"], bio_source)
        self.pub.publish_status(payload)
        alert = should_publish_alert(self.prev_level, level)
        if alert:
            self.pub.publish_alert(level, payload)
        f = payload["features"]
        log.info("%s p=.%02d/.%02d/.%02d g=%.2f tr=%.3f hr=%d Δ%d spo2=%d [%s] %.1ffps%s",
                 f"{level:<8}", round(p["routine"] * 100), round(p["urgent"] * 100), round(p["critical"] * 100),
                 f["gesture_conf"], f["tremor"], payload["hr"], f["hr_delta"], f["spo2"], mode, v["fps"],
                 f"  ALERT {level} published" if alert else "")
        if alert and self.buzzer:
            self.buzzer.play(level)
        self.runlog.write({"ts": payload["ts"], "level": level, "p_routine": p["routine"], "p_urgent": p["urgent"],
                           "p_critical": p["critical"], "gesture_conf": f["gesture_conf"], "tremor": f["tremor"],
                           "hr": payload["hr"], "hr_delta": f["hr_delta"], "spo2": f["spo2"], "bio_mode": mode,
                           "bio_source": bio_source, "hand_present": v["hand_present"], "n_frames": v["n_frames"],
                           "fps": v["fps"], "fusion_mode": self.fusion.mode, "alert_published": alert})
        self.prev_level = level
        self.last = {**f, "hr": payload["hr"], "fps": v["fps"], "level": level}

    def _oled_loop(self) -> None:
        while not self.quit.is_set():
            if self.oled:
                sensor = None
                src = self.display_bio or (self.bio if self.bio_mode == "live" else None)
                if src is not None:
                    try:
                        sensor = src.window()
                    except Exception:
                        sensor = None
                lines, inv = format_lines(self.s.node_id, self.pub.connected, sensor, self.bio_mode,
                                          self.last.get("gesture_conf"), self.last.get("tremor"),
                                          self.last.get("level"), self.fusion.mode)
                self.oled.show(lines, inv)
            self.quit.wait(1.0)

    def run(self) -> int:
        window_s = self.s.window_s
        next_t = time.monotonic() + window_s
        while not self.quit.is_set():
            if self.quit.wait(max(0.0, next_t - time.monotonic())):
                break
            if getattr(self.vision, "error", None):
                log.error("stopping: %s", self.vision.error)
                return EXIT_VISION
            started = time.monotonic()
            try:
                self.step()
            except Exception:
                log.exception("window failed; continuing")
            next_t += window_s
            took = time.monotonic() - started
            if time.monotonic() > next_t:
                skipped = int((time.monotonic() - next_t) // window_s) + 1
                log.warning("window took %.1f s; skipping %d slot(s)", took, skipped)
                next_t += skipped * window_s
        return 0

    def shutdown(self) -> None:
        log.info("shutting down (clean quit: publishing offline)")
        if self.pub:
            self.pub.clean_quit()
        for part in (self.vision, self.bio, self.display_bio):
            try:
                if part:
                    part.stop()
            except Exception as e:
                log.warning("stop failed: %s", e)
        for part in (self.oled, self.buzzer):
            try:
                if part:
                    part.close()
            except Exception:
                pass
        if self.lock:
            self.lock.__exit__(None, None, None)


def main(argv=None) -> int:
    args = parse_args(argv)
    overrides = {"node_id": args.node, "broker_host": args.broker, "broker_port": args.broker_port,
                 "camera_kind": args.camera, "camera_index": args.camera_index,
                 "log_dir": Path(args.log_dir).expanduser() if args.log_dir else None,
                 "params_path": Path(args.params) if args.params else None,
                 "model_path": Path(args.model) if args.model else None}
    settings = Settings.load(**overrides)
    setup_logging(settings.log_dir)
    try:
        settings.check_broker()
    except SettingsError as e:
        log.error("SETTINGS: %s", e)
        return EXIT_SETTINGS

    node = Node(args, settings)
    signal.signal(signal.SIGTERM, lambda *_: node.quit.set())
    signal.signal(signal.SIGINT, lambda *_: node.quit.set())
    code = 0
    try:
        node.start()
        print(node.summary(), flush=True)
        code = node.run()
    except HardwareBusy as e:
        log.error("%s. Stop that program first (cat /tmp/icu-hw.lock).", e)
        return EXIT_BUSY
    except Exception as e:
        from node.bio import BioUnavailable
        from node.vision.camera import CameraError
        if isinstance(e, CameraError):
            log.error("CAMERA: %s", e)
            code = EXIT_VISION
        elif isinstance(e, BioUnavailable):
            log.error("BIOSIGNALS: %s", e)
            code = EXIT_BIO
        elif type(e).__name__ == "TrackerError":
            log.error("HAND TRACKER: %s", e)
            code = EXIT_VISION
        else:
            raise
    finally:
        node.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
