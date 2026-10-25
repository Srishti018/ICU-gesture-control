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

# Gesture-only protocol (--bio none): camera only, label is gesture / no_gesture.
GESTURE_CLASSES = ["no_gesture", "gesture"]
GESTURE_SCENARIOS = {
    # code: (name, label, trials per person, light)
    "G_PALM":       ("palm",           "gesture",    6, "normal"),
    "G_PALM_DIM":   ("palm_dim_light", "gesture",    2, "dim"),
    "G_WEAK":       ("weak_palm",      "gesture",    2, "normal"),
    "G_PALM_SHAKY": ("palm_shaky",     "gesture",    2, "normal"),
    "N_REST":       ("rest",           "no_gesture", 4, "normal"),
    "N_SCRATCH":    ("incidental",     "no_gesture", 4, "normal"),
    "N_OTHER":      ("other_shapes",   "no_gesture", 2, "normal"),
    "N_NOHAND":     ("no_hand",        "no_gesture", 1, "normal"),
    "N_REST_SHAKY": ("rest_shaky",     "no_gesture", 1, "normal"),
}

WINDOW_COLUMNS = ["person", "scenario", "scenario_name", "trial", "label", "window_idx", "ts",
                  "gesture_conf", "tremor", "hand_present", "n_frames", "n_hand_frames", "fps",
                  "hr", "spo2", "hr_delta", "finger", "bio_quality", "bio_mode", "baseline_hr",
                  "light", "gesture_hand", "discarded"]
GESTURE_WINDOW_COLUMNS = WINDOW_COLUMNS + ["gesture"]  # gesture-protocol files only

BIO_COLUMNS = ["t_s", "hr", "spo2", "finger", "quality"]

WINDOW_SECONDS = 3


def scenario_label(code: str) -> str:
    return GESTURE_SCENARIOS[code][1] if code in GESTURE_SCENARIOS else SCENARIOS[code][1]


def scenario_name(code: str) -> str:
    return GESTURE_SCENARIOS[code][0] if code in GESTURE_SCENARIOS else SCENARIOS[code][0]


def is_exertion(code: str) -> bool:
    return False if code in GESTURE_SCENARIOS else SCENARIOS[code][2]


def is_gesture(code: str) -> bool:
    if code in GESTURE_SCENARIOS:
        return GESTURE_SCENARIOS[code][1] == "gesture"
    return SCENARIOS[code][3]
