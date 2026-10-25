"""Guided data collection session (interactive; run by the operator on the Pi in tmux).

Usage: python -m ml.collect.session --person P1 --bio live|manual|none [--resume] [--only S3,S5]

--bio none runs the gesture-only protocol instead (camera only, label gesture / no_gesture).

Holds the hardware lock for the whole session. Writes to ~/icu-data/raw/.
"""

import argparse
import json
from pathlib import Path
import random
import re
import sys
import time

from ml.collect import recorder
from ml.collect.trial import run_trial
from ml.schema import GESTURE_SCENARIOS, SCENARIOS, is_exertion, scenario_label, scenario_name

SAFETY_RULES = """SAFETY RULES (read them out loud to the participant):
  - Only team members who agree take part.
  - Anyone with a heart, lung or blood-pressure condition, or who feels unwell, skips the exercise trials.
  - Exercise stops IMMEDIATELY on dizziness, chest pain or unusual breathlessness.
  - Water is available. No camera images or video are saved. People are recorded as P1, P2, P3 only."""

SENSOR_RULES = ("Left index finger rests lightly on the sensor (don't press). Keep that hand still on the table. "
                "Use your right hand for gestures (left-handed people may swap; tell the operator).")

INSTRUCTIONS = {
    "S1": "Rest your gesture hand in view of the camera. Stay relaxed.",
    "S2": ("For 30 seconds, move naturally: scratch your face, adjust your sleeve, shift your hand, touch your "
           "hair. Do NOT hold the palm up."),
    "S3": ("Hold your open palm up towards the camera, fingers spread, for the whole 30 seconds. You may rest "
           "your elbow on the table."),
    "S4": "Rest your gesture hand in view of the camera. Do not make the gesture.",
    "S5": "Hold your open palm up towards the camera for the whole 30 seconds.",
    "H2": "Hold your hand up towards the camera with the fingers half bent, as if you were weak, for 30 seconds.",
}
INSTRUCTIONS["H1"] = INSTRUCTIONS["S3"]
INSTRUCTIONS["H3"] = INSTRUCTIONS["S5"]
INSTRUCTIONS["H4"] = INSTRUCTIONS["S2"]
INSTRUCTIONS.update({
    "G_PALM": "Hold your open palm up towards the camera, fingers spread, for the whole 30 seconds.",
    "G_PALM_DIM": "Same as before - lights are dimmed for this one.",
    "G_WEAK": "Hold your hand up towards the camera with fingers half bent, as if you were weak.",
    "G_PALM_SHAKY": "Hold your open palm up, and let your hand tremble slightly (small, gentle shake).",
    "N_REST": "Rest your hand in view of the camera. Stay relaxed.",
    "N_SCRATCH": ("Move naturally: scratch your face, adjust your sleeve, touch your hair. "
                  "Do NOT hold your palm up."),
    "N_OTHER": "Make other hand shapes: a fist, pointing, a thumbs up - but NOT an open palm.",
    "N_NOHAND": "Keep your hand out of the camera's view.",
    "N_REST_SHAKY": "Rest your hand in view and let it tremble slightly. Do NOT hold your palm up.",
})

REST_TRIALS = {"S1": 3, "S2": 3, "S3": 3}
EXERTION_ORDER = [("S4", 1), ("S5", 1), ("S4", 2), ("S5", 2), ("S4", 3), ("S5", 3), ("H4", 1), ("H3", 1)]


class NoBio:
    """--bio none: gesture-only protocol, no biosignal source."""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class Aborted(Exception):
    pass


class Session:
    def __init__(self, args, vision, bio, out_dir: Path, timing: dict):
        self.args = args
        self.person = args.person
        self.vision = vision
        self.bio = bio
        self.bio_mode = args.bio
        self.out = out_dir
        self.t = timing
        self.log = recorder.SessionLog(out_dir / f"{self.person}_session_log.txt")
        self.baseline = None
        self.gesture_hand = "right"
        self.exercise_ok = True
        self.only = set(args.only.split(",")) if args.only else None
        self.done = recorder.completed_trials(out_dir, self.person) if args.resume else set()

    # --- console helpers (everything is logged) -----------------------------------

    def say(self, text: str = "") -> None:
        print(text, flush=True)
        if text:
            self.log.write("SAY", text)

    def ask(self, text: str) -> str:
        self.log.write("ASK", text)
        try:
            answer = input(f"{text} ").strip()
        except EOFError:
            self.log.write("ANSWER", "<end of input>")
            raise Aborted("input ended") from None
        self.log.write("ANSWER", answer)
        return answer

    def enter(self, text: str) -> None:
        self.ask(f"\n>>> {text}\n    Press Enter to start.")

    def ask_reading(self, text: str) -> tuple[int, int]:
        while True:
            m = re.fullmatch(r"(\d{2,3})\s+(\d{2,3})", self.ask(f"    {text}:"))
            if m:
                return int(m.group(1)), int(m.group(2))
            self.say("    Type two numbers: heart rate and SpO2, e.g. 74 98")

    def countdown(self, seconds: int, label: str) -> None:
        for left in range(seconds, 0, -1):
            if left % 10 == 0 or left <= 5:
                print(f"    {label}: {left} s", flush=True)
            time.sleep(1)

    def wanted(self, code: str) -> bool:
        return self.only is None or code in self.only

    # --- steps ----------------------------------------------------------------

    def consent(self) -> None:
        self.say(SAFETY_RULES)
        if self.bio_mode == "none":
            if not self.ask(f"Does {self.person} agree to take part? (y/n)").lower().startswith("y"):
                raise Aborted(f"{self.person} did not agree; session stopped")
            return
        while True:
            a = self.ask(f"Does {self.person} agree to take part, and is {self.person} fine to do light exercise? "
                         "(y/n/no-exercise)").lower()
            if a in ("y", "yes"):
                return
            if a == "no-exercise":
                self.exercise_ok = False
                self.say("Exertion scenarios will be skipped for this person.")
                return
            if a in ("n", "no"):
                raise Aborted(f"{self.person} did not agree; session stopped")

    def sensor_setup(self) -> None:
        if self.bio_mode != "none":
            self.say(SENSOR_RULES)
        a = self.ask("Which hand makes the gestures? (right/left) [right]").lower()
        self.gesture_hand = "left" if a.startswith("l") else "right"

    def setup_check(self) -> None:
        while True:
            self.enter(f"SETUP CHECK ({self.t['setup']} s): hold the palm up for a few seconds, then rest it.")
            if hasattr(self.vision, "set_scenario"):
                self.vision.set_scenario("S3")
            self.vision.window()
            end = time.monotonic() + self.t["setup"]
            while time.monotonic() < end:
                time.sleep(min(2, self.t["setup"]))
                v = self.vision.window()
                hr = self.bio.window().get("hr") if self.bio_mode == "live" else self.bio_mode
                print(f"    gesture={v['gesture_conf']:.2f} hand={'yes' if v['hand_present'] else 'no'} hr={hr}",
                      flush=True)
            if self.ask("Did hand detection work (gesture high with the palm up)? (y/n)").lower().startswith("y"):
                return
            self.say("Adjust the camera or lighting, then repeat the check.")

    def baseline_step(self) -> None:
        path = self.out / f"{self.person}_baseline.json"
        if self.args.resume and path.exists():
            self.baseline = json.loads(path.read_text())["baseline_hr"]
            self.bio.set_baseline(self.baseline)
            self.say(f"Resuming: baseline HR {self.baseline} from {path.name}")
            return
        secs = self.t["baseline"]
        self.enter(f"BASELINE ({secs} s): sit still, sensor finger on, other hand resting in view.")
        start = recorder.base_name(self.person, "R1", "rest")
        if self.bio_mode == "live":
            self.baseline = self.bio.calibrate_baseline(secs)
            recs = self.bio.records(secs + 1)
            t0 = recs[0]["t"] if recs else 0
            rows = [{"t_s": round(r["t"] - t0, 2), "hr": r["hr"], "spo2": r["spo2"], "finger": r["finger"],
                     "quality": round(r["quality"], 3)} for r in recs]
            method = "live: median of valid seconds"
        else:
            hr0, s0 = self.ask_reading("Reference reading NOW, at the start (hr spo2)")
            self.bio.set_start(hr0, s0, seconds=secs)
            self.countdown(secs, "baseline")
            hr1, s1 = self.ask_reading("Reference reading NOW, at the end (hr spo2)")
            self.bio.set_end(hr1, s1)
            self.baseline = int(round((hr0 + hr1) / 2))
            self.bio.set_baseline(self.baseline)
            rows = self.bio.per_second()
            method = "manual: mean of start and end reference readings"
        recorder.write_bio(self.out / f"{start}_bio.csv", rows)
        recorder.write_json(path, {"person": self.person, "baseline_hr": self.baseline, "method": method,
                                   "seconds": secs, "values": [r["hr"] for r in rows],
                                   "recorded_at": recorder.now_iso(), "bio_mode": self.bio_mode})
        self.say(f"Baseline HR: {self.baseline} bpm (saved {path.name}, {start}_bio.csv)")

    def trial(self, code: str, trial_no: int, light: str = "normal", delay_s=None) -> None:
        notes = ""
        while True:
            if hasattr(self.vision, "set_scenario"):
                self.vision.set_scenario(code)
            self.say(f"\n=== {code} ({scenario_name(code)}, label {scenario_label(code)}) trial {trial_no} ===")
            self.say(f"Participant: {INSTRUCTIONS[code]}")
            if delay_s is None:
                self.enter("When the participant is ready")
            result = run_trial(self.vision, self.bio, self.person, code, trial_no, self.out,
                               seconds=self.t["trial"], bio_mode=self.bio_mode, baseline_hr=self.baseline,
                               light=light, gesture_hand=self.gesture_hand, delay_s=delay_s, notes=notes,
                               ask_reading=self.ask_reading, say=print)
            s = result["summary"]
            fmt = lambda v, d=2: "—" if v is None else f"{v:.{d}f}"  # noqa: E731
            if self.bio_mode == "none":
                self.say(f"Summary: mean gesture {fmt(s['gesture'])}, hand {fmt(s['hand'] * 100, 0)}%")
            else:
                self.say(f"Summary: mean gesture {fmt(s['gesture'])}, hand {fmt(s['hand'] * 100, 0)}%, "
                         f"mean hr_delta {fmt(s['hr_delta'], 1)}, finger {fmt(s['finger'] * 100, 0)}%")
            while True:
                a = self.ask("k keep / r redo / n add a note:").lower()
                if a == "n":
                    notes = (notes + " " + self.ask("Note:")).strip()
                    meta_path = self.out / f"{result['base']}_meta.json"
                    meta = json.loads(meta_path.read_text())
                    meta["notes"] = notes
                    recorder.write_json(meta_path, meta)
                    continue
                if a in ("k", "r"):
                    break
            if a == "k":
                return
            recorder.mark_discarded(self.out, result["base"])
            self.say("Marked as discarded; repeating this trial.")
            notes = ""  # a note belongs to the discarded attempt, not the repeat
            if delay_s is not None:
                return self.exertion_trial(code, trial_no)  # needs fresh exercise

    def rest_block(self) -> None:
        order = [(code, n) for code, k in REST_TRIALS.items() for n in range(1, k + 1)]
        random.Random(self.person).shuffle(order)
        self.say("Rest block order: " + ", ".join(f"{c}-T{n}" for c, n in order) + ", then H1, H2")
        first = True
        for code, n in order + [("H1", 1), ("H2", 1)]:
            if not self.wanted(code) or (code, n) in self.done:
                continue
            if not first:
                self.countdown(self.t["pause"], "pause")
            first = False
            if code == "H1":
                self.enter("Dim the room lights now (H1).")
            self.trial(code, n, light="dim" if code == "H1" else "normal")
            if code == "H1":
                self.enter("Turn the room lights back on.")

    def gesture_block(self) -> None:
        """Gesture-only protocol: fixed shuffled order per person, label fixed by the scenario."""
        order = [(code, n) for code, spec in GESTURE_SCENARIOS.items() for n in range(1, spec[2] + 1)]
        random.Random(self.person).shuffle(order)
        self.say("Gesture block order: " + ", ".join(f"{c}-T{n}" for c, n in order))
        first = True
        for code, n in order:
            if not self.wanted(code) or (code, n) in self.done:
                continue
            if not first:
                self.countdown(self.t["pause"], "pause")
            first = False
            light = GESTURE_SCENARIOS[code][3]
            if light == "dim":
                self.enter(f"Dim the room lights now ({code}).")
            self.trial(code, n, light=light)
            if light == "dim":
                self.enter("Turn the room lights back on.")

    def exercise(self, brisk_walk: bool) -> float:
        if brisk_walk:
            self.enter("Walk briskly on the spot for 60 seconds.")
        else:
            self.enter("Do 60 seconds of spot jogging (or jumping jacks) now. "
                       "STOP AT ONCE IF YOU FEEL DIZZY OR UNWELL.")
        self.countdown(self.t["exercise"], "exercise")
        return time.monotonic()

    def recovery(self) -> None:
        self.say(f"Recovery: at least {self.t['recovery']} s and HR within baseline + 10 bpm.")
        self.countdown(self.t["recovery"], "recovery")
        limit = (self.baseline or 0) + 10
        while True:
            if self.bio_mode == "live":
                hr = self.bio.window().get("hr")
            else:
                hr, _ = self.ask_reading("Reference reading now (hr spo2)")
            if hr is not None and hr <= limit:
                return
            self.say(f"    HR {hr} is above {limit}; waiting 15 s more.")
            time.sleep(min(15, self.t["recovery"]))

    def exertion_trial(self, code: str, n: int) -> None:
        finished = self.exercise(brisk_walk=(code == "H3"))
        self.ask(f"Sit, put the sensor finger back, {'raise the palm' if SCENARIOS[code][3] else 'rest the other hand'} "
                 "as instructed, then press Enter.")
        delay = round(time.monotonic() - finished, 1)
        if delay > 20:
            self.say(f"WARNING: {delay} s between exercise and trial (more than 20 s).")
        self.trial(code, n, delay_s=delay)

    def exertion_block(self) -> None:
        todo = [(c, n) for c, n in EXERTION_ORDER if self.wanted(c) and (c, n) not in self.done]
        for i, (code, n) in enumerate(todo):
            self.exertion_trial(code, n)
            if i < len(todo) - 1 or self.only is None:
                self.recovery()

    def replay_r2(self) -> None:
        secs = self.t["r2"]
        self.say("\n=== Replay recording R2 (bio only) ===")
        self.exercise(brisk_walk=False)
        self.ask(f"Sit, sensor finger on, no gesture. Press Enter to record {secs} s.")
        base = recorder.base_name(self.person, "R2", "exertion")
        if self.bio_mode == "live":
            time.sleep(secs)
            recs = self.bio.records(secs + 1)
            t0 = recs[0]["t"] if recs else 0
            rows = [{"t_s": round(r["t"] - t0, 2), "hr": r["hr"], "spo2": r["spo2"], "finger": r["finger"],
                     "quality": round(r["quality"], 3)} for r in recs]
        else:
            hr0, s0 = self.ask_reading("Reference reading NOW, at the start (hr spo2)")
            self.bio.set_start(hr0, s0, seconds=secs)
            self.countdown(secs, "R2")
            hr1, s1 = self.ask_reading("Reference reading NOW, at the end (hr spo2)")
            self.bio.set_end(hr1, s1)
            rows = self.bio.per_second()
        recorder.write_bio(self.out / f"{base}_bio.csv", rows)
        self.say(f"Saved {base}_bio.csv")

    def run(self) -> None:
        self.say(f"Session for {self.person}, bio mode {self.bio_mode}, output {self.out}")
        self.consent()
        self.sensor_setup()
        self.setup_check()
        if self.bio_mode == "none":
            self.gesture_block()
            self.say(f"\nGesture session for {self.person} finished.")
            return
        self.baseline_step()
        self.rest_block()
        if self.exercise_ok and (self.only is None or any(is_exertion(c) for c in self.only)):
            self.exertion_block()
            if self.only is None:
                self.replay_r2()
        self.say(f"\nSession for {self.person} finished.")


def load_vision(kind: str):
    if kind == "synthetic":
        from ml.collect.synthetic_vision import SyntheticVision
        return SyntheticVision(None)
    try:
        from node.vision.features import VisionFeatureExtractor
    except ModuleNotFoundError as e:
        raise SystemExit(f"Role A's node/vision/features.py is not available ({e}). "
                         "The real session needs it; for a dry run use --vision synthetic.") from e
    try:
        from node.settings import Settings
        settings = Settings.load()
    except ModuleNotFoundError:
        settings = None
    return VisionFeatureExtractor(settings)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Guided ICU Fusion data collection session")
    parser.add_argument("--person", required=True, help="P1, P2, P3 (or PTEST for a dry run)")
    parser.add_argument("--bio", choices=["live", "manual", "none"], required=True,
                        help="none = gesture-only protocol (camera only)")
    parser.add_argument("--resume", action="store_true", help="skip trials already recorded (not discarded)")
    parser.add_argument("--only", default=None, help="comma-separated scenario codes, e.g. S3,S5")
    parser.add_argument("--out", default=str(recorder.DEFAULT_OUT), help=argparse.SUPPRESS)
    parser.add_argument("--seconds", type=int, default=30, help=argparse.SUPPRESS)
    parser.add_argument("--quick", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--vision", choices=["camera", "synthetic"], default="camera", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if not re.fullmatch(r"P\d+|PTEST", args.person):
        parser.error("--person must be a code like P1 (no names)")
    if args.only:
        known = GESTURE_SCENARIOS if args.bio == "none" else SCENARIOS
        unknown = [c for c in args.only.split(",") if c not in known]
        if unknown:
            parser.error(f"unknown scenario(s): {', '.join(unknown)}")
    if args.seconds % 3 or args.seconds < 3:
        parser.error("--seconds must be a multiple of 3")
    out = Path(args.out).expanduser()
    if args.vision == "synthetic" and (args.person != "PTEST" or out.resolve() == recorder.DEFAULT_OUT.resolve()):
        parser.error("--vision synthetic is for dry runs only: use --person PTEST and a separate --out folder")
    out.mkdir(parents=True, exist_ok=True)

    timing = {"trial": args.seconds, "setup": 20, "baseline": 60, "pause": 10 if args.bio == "none" else 15,
              "exercise": 60, "recovery": 120, "r2": 90}
    if args.quick:
        timing.update(setup=2, baseline=3, pause=1, exercise=2, recovery=1, r2=6)

    from node.bio import BioUnavailable, make_bio_source
    from node.bio.hwlock_compat import HardwareBusy, HardwareLock
    try:
        with HardwareLock("ml.collect.session"):
            vision = load_vision(args.vision)
            if args.bio == "none":
                bio = NoBio()
            else:
                bio = make_bio_source(args.bio, None, **({"take_lock": False} if args.bio == "live" else {}))
            vision.start()
            bio.start()
            try:
                Session(args, vision, bio, out, timing).run()
            except Aborted as e:
                print(f"\nSession stopped: {e}. Rerun with --resume to continue.", file=sys.stderr)
                return 1
            except KeyboardInterrupt:
                print("\nSession interrupted. Rerun with --resume to continue.", file=sys.stderr)
                return 1
            finally:
                bio.stop()
                vision.stop()
    except HardwareBusy as e:
        print(f"{e}. Stop that program first, then rerun.", file=sys.stderr)
        return 1
    except BioUnavailable as e:
        print(f"Biosignal source unavailable: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
