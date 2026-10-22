"""Pure hand-geometry functions (no MediaPipe). Formulas: Role A plan §8.2.

Landmarks are (21, 2) arrays of pixel coordinates, x right and y DOWN.
0 wrist; thumb 1-4; index 5 MCP, 6 PIP, 8 tip; middle 9-12; ring 13-16; pinky 17-20.
"""

import numpy as np

DEFAULT_PARAMS = {
    "min_hand_size_px": 10.0,
    "finger_angle_lo": 120.0,
    "finger_angle_hi": 165.0,
    "thumb_lo": 0.35,
    "thumb_hi": 0.70,
    "upright_lo": 0.8,
    "upright_hi": 1.5,
}
FINGERS = {"index": (5, 6, 8), "middle": (9, 10, 12), "ring": (13, 14, 16), "pinky": (17, 18, 20)}
MIN_TREMOR_FRAMES = 5


def clamp01(v: float) -> float:
    return min(1.0, max(0.0, float(v)))


def ramp(v: float, lo: float, hi: float) -> float:
    return clamp01((v - lo) / (hi - lo))


def _p(params: dict | None) -> dict:
    return {**DEFAULT_PARAMS, **(params or {})}


def hand_size(L) -> float:
    """Wrist (0) to middle-finger MCP (9), in pixels."""
    L = np.asarray(L, dtype=float)
    return float(np.linalg.norm(L[9] - L[0]))


def finger_angle(L, mcp: int, pip: int, tip: int) -> float:
    """Angle at the PIP joint between PIP->MCP and PIP->TIP, in degrees (180 = straight)."""
    L = np.asarray(L, dtype=float)
    a, b = L[mcp] - L[pip], L[tip] - L[pip]
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    cos = float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def finger_scores(L, params: dict | None = None) -> dict:
    p = _p(params)
    return {name: ramp(finger_angle(L, *j), p["finger_angle_lo"], p["finger_angle_hi"])
            for name, j in FINGERS.items()}


def thumb_score(L, params: dict | None = None) -> float:
    """Thumb tip (4) away from the index MCP (5), relative to hand size."""
    p = _p(params)
    L = np.asarray(L, dtype=float)
    s = hand_size(L)
    if s == 0:
        return 0.0
    return ramp(float(np.linalg.norm(L[4] - L[5])) / s, p["thumb_lo"], p["thumb_hi"])


def upright_factor(L) -> float:
    """u = (wrist.y - middle_tip.y) / hand size; about 0 for a flat or sideways hand."""
    L = np.asarray(L, dtype=float)
    s = hand_size(L)
    return 0.0 if s == 0 else float((L[0, 1] - L[12, 1]) / s)


def frame_gesture_score(L, params: dict | None = None) -> tuple[float, dict]:
    """g = open x up, with open = 0.8 mean(four fingers) + 0.2 thumb. 0 if the hand is too small."""
    p = _p(params)
    s = hand_size(L)
    if s < p["min_hand_size_px"]:
        return 0.0, {"s": s, "too_small": True}
    fingers = finger_scores(L, p)
    t = thumb_score(L, p)
    open_ = 0.8 * float(np.mean(list(fingers.values()))) + 0.2 * t
    u = upright_factor(L)
    up = ramp(u, p["upright_lo"], p["upright_hi"])
    angles = {name: finger_angle(L, *j) for name, j in FINGERS.items()}
    return open_ * up, {"s": s, "angles": angles, "fingers": fingers, "t": t, "u": u,
                        "open": open_, "up": up, "too_small": False}


def tremor(tips, wrists, sizes) -> float:
    """Fingertip (8) relative to the wrist (0), divided by hand size per frame;
    tremor = (std(x) + std(y)) / 2 over the window. Needs >= 5 hand frames, else 0."""
    if len(tips) < MIN_TREMOR_FRAMES:
        return 0.0
    tips = np.asarray(tips, dtype=float)
    wrists = np.asarray(wrists, dtype=float)
    sizes = np.asarray(sizes, dtype=float).reshape(-1, 1)
    if np.any(sizes <= 0):
        return 0.0
    rel = (tips - wrists) / sizes
    return float((np.std(rel[:, 0]) + np.std(rel[:, 1])) / 2)
