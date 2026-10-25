import cv2, time, csv, os, random
from collections import deque
import numpy as np
import mediapipe as mp

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

CSV_FILE = "samples.csv"
HEADER = ["trial", "scenario", "gesture_conf", "tremor", "hr_delta", "spo2", "label"]
SAMPLE_EVERY = 0.5      # seconds between saved rows
TREMOR_WINDOW = 2.5     # seconds of history for tremor

# key -> (scenario name, label)
SCENARIOS = {
    "1": ("calm", 0),
    "2": ("gesture_only", 0),
    "3": ("hr_only", 0),
    "4": ("combined", 1),
}

def fake_vitals(scenario):
    """Stand-in for MAX30100 until the Pi is ready."""
    if scenario in ("calm", "gesture_only"):
        return random.gauss(2, 3), random.gauss(97.5, 0.8)
    if scenario == "hr_only":
        return random.gauss(25, 6), random.gauss(96, 1.0)
    return random.gauss(25, 6), random.gauss(93, 2.0)  # combined

def dist(a, b):
    return np.hypot(a.x - b.x, a.y - b.y)

def gesture_confidence(lm):
    """Open palm score 0..1 = how extended the 5 fingers are."""
    scores = []
    # index, middle, ring, pinky: fingertip vs PIP joint, distance from wrist
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        ratio = dist(lm[0], lm[tip]) / dist(lm[0], lm[pip])
        scores.append(np.clip((ratio - 1.0) / 0.3, 0, 1))
    # thumb: tip vs IP joint, distance from the pinky base
    ratio = dist(lm[4], lm[17]) / dist(lm[3], lm[17])
    scores.append(np.clip((ratio - 1.0) / 0.3, 0, 1))
    return float(np.mean(scores))

buf = deque()  # (time, x, y) of index fingertip relative to wrist

def tremor_value(lm, now):
    scale = dist(lm[0], lm[9])  # hand size, so camera distance doesn't matter
    x = (lm[8].x - lm[0].x) / scale
    y = (lm[8].y - lm[0].y) / scale
    buf.append((now, x, y))
    while buf and now - buf[0][0] > TREMOR_WINDOW:
        buf.popleft()
    if len(buf) < 10:
        return 0.0
    arr = np.array(buf)
    return float(np.sqrt(arr[:, 1].var() + arr[:, 2].var()))

new_file = not os.path.exists(CSV_FILE)
f = open(CSV_FILE, "a", newline="")
writer = csv.writer(f)
if new_file:
    writer.writerow(HEADER)

scenario, label = SCENARIOS["1"]
recording = False
trial_id = 0
last_save = 0
rows_this_session = 0

cap = cv2.VideoCapture(0)
with mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.6,
                    min_tracking_confidence=0.6) as hands:
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.flip(frame, 1)
        results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        now = time.time()
        conf = tremor = 0.0
        hr_delta, spo2 = fake_vitals(scenario)

        if results.multi_hand_landmarks:
            hand = results.multi_hand_landmarks[0]
            mp_draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS)
            lm = hand.landmark
            conf = gesture_confidence(lm)
            tremor = tremor_value(lm, now)

            if recording and now - last_save >= SAMPLE_EVERY:
                writer.writerow([trial_id, scenario, round(conf, 3), round(tremor, 4),
                                 round(hr_delta, 1), round(spo2, 1), label])
                f.flush()
                last_save = now
                rows_this_session += 1
        else:
            buf.clear()

        status = "REC" if recording else "paused"
        cv2.putText(frame, f"[{status}] scenario: {scenario} (label {label})", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"gesture {conf:.2f}  tremor {tremor:.3f}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"hr_delta {hr_delta:.0f}  spo2 {spo2:.0f}  rows {rows_this_session}",
                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("collect", frame)

        key = chr(cv2.waitKey(1) & 0xFF)
        if key in SCENARIOS:
            scenario, label = SCENARIOS[key]
        elif key == "r":
            recording = not recording
            if recording:
                trial_id = int(time.time())  # new trial id each time you press r
        elif key == "q":
            break

f.close()
cap.release()
cv2.destroyAllWindows()