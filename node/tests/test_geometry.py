import numpy as np
import pytest

from node.vision import geometry
from node.vision.features import summarise

WRIST = np.array([100.0, 200.0])


def palm(curl_deg: float = 0.0, thumb_out: bool = True) -> np.ndarray:
    """Open palm pointing up (y down). curl_deg bends each finger at the PIP joint
    (0 = straight, PIP angle = 180 - curl)."""
    L = np.zeros((21, 2))
    L[0] = WRIST
    # thumb CMC, MCP, IP, tip
    L[1], L[2], L[3] = [80, 190], [68, 178], [58, 170]
    L[4] = [48, 165] if thumb_out else [86, 158]
    for k, x in enumerate([85.0, 100.0, 115.0, 128.0]):        # index, middle, ring, pinky
        mcp, pip, dip, tip = 5 + 4 * k, 6 + 4 * k, 7 + 4 * k, 8 + 4 * k
        L[mcp] = [x, 150.0]
        L[pip] = [x, 125.0]
        th = np.radians(curl_deg)
        d = np.array([np.sin(th), -np.cos(th)])                 # direction after the PIP joint
        L[dip] = L[pip] + 12 * d
        L[tip] = L[pip] + 24 * d
    return L


def fist() -> np.ndarray:
    L = palm(curl_deg=170.0, thumb_out=False)
    return L


def rotate(L, deg, center=WRIST) -> np.ndarray:
    th = np.radians(deg)
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    return (L - center) @ R.T + center


def g(L):
    return geometry.frame_gesture_score(L)[0]


def test_open_palm_up_scores_high():
    assert g(palm()) > 0.85


def test_fist_scores_low():
    assert g(fist()) < 0.15


def test_palm_sideways_scores_low():
    assert g(rotate(palm(), 90)) < 0.15
    assert g(rotate(palm(), -90)) < 0.15


def test_half_curled_is_in_between():
    L = palm(curl_deg=40.0)                     # PIP angle 140 degrees
    assert abs(geometry.finger_angle(L, 5, 6, 8) - 140.0) < 0.5
    assert 0.2 < g(L) < 0.7


def test_scale_and_position_invariance():
    L = palm(curl_deg=25.0)
    L2 = (L - WRIST) * 2.0 + WRIST + np.array([40.0, -30.0])
    assert abs(g(L) - g(L2)) < 0.01


def test_too_small_hand_is_no_hand():
    L = (palm() - WRIST) * 0.1 + WRIST          # hand size 5 px < 10 px
    score, details = geometry.frame_gesture_score(L)
    assert score == 0.0 and details["too_small"]


def test_ramp_and_clamp():
    assert geometry.ramp(120, 120, 165) == 0.0
    assert geometry.ramp(165, 120, 165) == 1.0
    assert geometry.ramp(142.5, 120, 165) == pytest.approx(0.5)
    assert geometry.clamp01(-3) == 0.0 and geometry.clamp01(7) == 1.0


def test_tremor_identical_points_is_zero():
    tips = [[100.0, 90.0]] * 10
    wrists = [[100.0, 200.0]] * 10
    assert geometry.tremor(tips, wrists, [50.0] * 10) == 0.0


def test_tremor_known_std():
    rng = np.random.default_rng(0)
    rel = rng.normal(0, 1, (40, 2)) * np.array([0.02, 0.04])
    wrists = np.tile(WRIST, (40, 1))
    sizes = np.full(40, 50.0)
    tips = wrists + rel * 50.0
    expected = (np.std(rel[:, 0]) + np.std(rel[:, 1])) / 2
    assert geometry.tremor(tips, wrists, sizes) == pytest.approx(expected, abs=1e-6)


def test_tremor_scale_invariant():
    rng = np.random.default_rng(1)
    rel = rng.normal(0, 0.03, (20, 2))
    wrists = np.tile(WRIST, (20, 1)) + rng.normal(0, 3, (20, 2))   # the whole hand also moves
    tips = wrists + rel * 50.0
    t1 = geometry.tremor(tips, wrists, np.full(20, 50.0))
    t2 = geometry.tremor(tips * 2, wrists * 2, np.full(20, 100.0))
    assert t1 == pytest.approx(t2, abs=1e-9)
    # moving the whole hand without finger movement relative to the wrist is not tremor
    still = wrists + np.array([0.0, -100.0])
    assert geometry.tremor(still, wrists, np.full(20, 50.0)) == pytest.approx(0.0, abs=1e-12)


def test_tremor_needs_five_frames():
    assert geometry.tremor([[1, 2]] * 4, [[0, 0]] * 4, [50] * 4) == 0.0


def test_window_summary():
    tip, wrist = np.array([100.0, 90.0]), WRIST
    frames = [(0.1 * i, True, 0.9, tip, wrist, 50.0) for i in range(6)] + \
             [(0.6 + 0.1 * i, False, 0.0, None, None, 0.0) for i in range(4)]
    w = summarise(frames, elapsed=1.0)
    assert w == {"hand_present": True, "gesture_conf": 0.54, "tremor": 0.0, "n_frames": 10,
                 "n_hand_frames": 6, "fps": 10.0}
    assert summarise([], 3.0)["hand_present"] is False
    assert summarise(frames[:4] + frames[6:] + frames[6:], 1.0)["hand_present"] is False   # 4 of 12 frames
