"""Record one trial: vision + bio every 3 s, then write windows/bio CSV and meta JSON."""

from datetime import datetime, timedelta
import time

from ml.collect import recorder
from ml.schema import WINDOW_SECONDS, scenario_label, scenario_name


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def run_trial(vision, bio, person: str, scenario: str, trial: int, out_dir, *, seconds: int = 30,
              bio_mode: str = "live", baseline_hr=None, light: str = "normal", gesture_hand: str = "right",
              delay_s=None, notes: str = "", ask_reading=None, sleep=time.sleep, clock=time.monotonic,
              say=print) -> dict:
    """Returns {"base", "meta", "summary"}. In manual mode ask_reading(text) -> (hr, spo2) is called
    before and after the trial and the windows get interpolated bio values afterwards."""
    if bio_mode == "manual":
        hr0, spo20 = ask_reading("Reference reading NOW, at the start (hr spo2)")
        bio.set_start(hr0, spo20, seconds=seconds)

    vision.window()  # discard frames from before the trial
    start_wall = datetime.now()
    start = clock()
    n_windows = int(seconds // WINDOW_SECONDS)
    rows = []
    for i in range(n_windows):
        target = start + WINDOW_SECONDS * (i + 1)
        delay = target - clock()
        if delay > 0:
            sleep(delay)
        v = vision.window()
        b = bio.window() if bio_mode != "manual" else None
        row = {
            "person": person, "scenario": scenario, "scenario_name": scenario_name(scenario), "trial": trial,
            "label": scenario_label(scenario), "window_idx": i,
            "ts": (start_wall + timedelta(seconds=WINDOW_SECONDS * (i + 1))).strftime("%Y-%m-%dT%H:%M:%S"),
            "gesture_conf": v["gesture_conf"], "tremor": v["tremor"], "hand_present": bool(v["hand_present"]),
            "n_frames": v["n_frames"], "n_hand_frames": v["n_hand_frames"], "fps": v["fps"],
            "bio_mode": bio_mode, "baseline_hr": baseline_hr, "light": light, "gesture_hand": gesture_hand,
            "discarded": 0,
        }
        if b is not None:
            row.update(hr=b["hr"], spo2=b["spo2"], hr_delta=b["hr_delta"], finger=b["finger"], bio_quality=b["quality"])
            say(f"  w{i} g={v['gesture_conf']:.2f} tr={v['tremor']:.3f} hand={float(v['hand_present']):.1f} "
                f"hr={b['hr']} Δ{b['hr_delta']} spo2={b['spo2']}")
        else:
            say(f"  w{i} g={v['gesture_conf']:.2f} tr={v['tremor']:.3f} hand={float(v['hand_present']):.1f}")
        rows.append(row)
    end_wall = datetime.now()

    if bio_mode == "manual":
        hr1, spo21 = ask_reading("Reference reading NOW, at the end (hr spo2)")
        bio.set_end(hr1, spo21)
        for i, row in enumerate(rows):
            b = bio.window_for(WINDOW_SECONDS * i, WINDOW_SECONDS * (i + 1))
            row.update(hr=b["hr"], spo2=b["spo2"], hr_delta=b["hr_delta"], finger=True, bio_quality=b["quality"])
        bio_rows = bio.per_second()
    else:
        recs = bio.records(seconds + 1) if hasattr(bio, "records") else []
        t0 = recs[0]["t"] if recs else 0
        bio_rows = [{"t_s": round(r["t"] - t0, 2), "hr": r["hr"], "spo2": r["spo2"], "finger": r["finger"],
                     "quality": round(r["quality"], 3)} for r in recs]

    base = recorder.base_name(person, scenario, trial, start_wall)
    meta = {
        "person": person, "scenario": scenario, "scenario_name": scenario_name(scenario),
        "label": scenario_label(scenario), "trial": trial, "bio_mode": bio_mode, "baseline_hr": baseline_hr,
        "light": light, "gesture_hand": gesture_hand, "seconds": seconds,
        "start_time": start_wall.strftime("%Y-%m-%dT%H:%M:%S"), "end_time": end_wall.strftime("%Y-%m-%dT%H:%M:%S"),
        "delay_s": delay_s, "notes": notes, "discarded": False, "git_commit": recorder.git_commit(),
        "vision": "synthetic" if getattr(vision, "is_synthetic", False) else "camera",
    }
    recorder.write_windows(out_dir / f"{base}_windows.csv", rows)
    recorder.write_bio(out_dir / f"{base}_bio.csv", bio_rows)
    recorder.write_json(out_dir / f"{base}_meta.json", meta)

    summary = {
        "gesture": _mean([r["gesture_conf"] for r in rows]),
        "hand": _mean([1.0 if r["hand_present"] else 0.0 for r in rows]),
        "hr_delta": _mean([r.get("hr_delta") for r in rows]),
        "finger": _mean([1.0 if r.get("finger") else 0.0 for r in rows]),
    }
    return {"base": base, "meta": meta, "summary": summary}
