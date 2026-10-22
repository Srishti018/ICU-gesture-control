"""Single source of truth for features, classes, scenarios and the windows CSV format.

Plain Python only: imported on the Pi (collector) as well as on the laptop.
Booleans in CSV files are stored as 1/0.
"""

FEATURES = ["gesture_conf", "tremor", "hr_delta", "spo2"]
CLASSES = ["routine", "urgent", "critical"]
CLASS_INDEX = {c: i for i, c in enumerate(CLASSES)}

SCENARIOS = {
    # code: (name, label, exertion, gesture, notes)
    "S1": ("calm",                  "routine",  False, False, "hand resting in view"),
    "S2": ("incidental_movement",   "routine",  False, False, "scratch face, adjust sleeve/blanket, shift hand"),
    "S3": ("gesture_only",          "urgent",   False, True,  "open palm held up for the whole trial"),
    "S4": ("exertion_only",         "routine",  True,  False, "after exercise, hand resting in view"),
    "S5": ("exertion_gesture",      "critical", True,  True,  "after exercise, open palm held up"),
    "H1": ("gesture_dim_light",     "urgent",   False, True,  "S3 with room lights dimmed"),
    "H2": ("weak_gesture",          "urgent",   False, True,  "palm up, fingers half-bent (weak patient)"),
    "H3": ("mild_exertion_gesture", "critical", True,  True,  "after 60 s brisk walking only, open palm"),
    "H4": ("exertion_incidental",   "routine",  True,  False, "after exercise, scratching/adjusting"),
}
CORE_SCENARIOS = ["S1", "S2", "S3", "S4", "S5"]

WINDOW_COLUMNS = ["person", "scenario", "scenario_name", "trial", "label", "window_idx", "ts",
                  "gesture_conf", "tremor", "hand_present", "n_frames", "n_hand_frames", "fps",
                  "hr", "spo2", "hr_delta", "finger", "bio_quality", "bio_mode", "baseline_hr",
                  "light", "gesture_hand", "discarded"]

BIO_COLUMNS = ["t_s", "hr", "spo2", "finger", "quality"]

WINDOW_SECONDS = 3


def scenario_label(code: str) -> str:
    return SCENARIOS[code][1]


def scenario_name(code: str) -> str:
    return SCENARIOS[code][0]


def is_exertion(code: str) -> bool:
    return SCENARIOS[code][2]


def is_gesture(code: str) -> bool:
    return SCENARIOS[code][3]
