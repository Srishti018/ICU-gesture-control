"""Fixed baselines. Decided before data collection; never tuned on data."""

GESTURE_THRESHOLD = 0.8
HR_DELTA_THRESHOLD = 15


def rule_level(f: dict) -> str:
    """critical if gesture_conf >= 0.8 and hr_delta >= 15; urgent if gesture_conf >= 0.8; else routine."""
    gesture = float(f["gesture_conf"]) >= GESTURE_THRESHOLD
    hr_delta = f.get("hr_delta")
    raised = hr_delta is not None and float(hr_delta) >= HR_DELTA_THRESHOLD
    if gesture and raised:
        return "critical"
    if gesture:
        return "urgent"
    return "routine"


def gesture_only_level(f: dict) -> str:
    """A gesture-only system: urgent if gesture_conf >= 0.8, else routine. Never critical."""
    return "urgent" if float(f["gesture_conf"]) >= GESTURE_THRESHOLD else "routine"
