# Node interfaces between Role A and Role B (fixed)

Copied verbatim from Appendix B of `docs/ROLE_B_IMPLEMENTATION_PLAN.md` (identical copy in Role A's plan). Changes need both roles to agree.

### B.1 Ownership
| Path | Owner |
| --- | --- |
| `node/` (except `node/bio/`), `docs/ROLE_A_NOTES.md` | Role A |
| `node/bio/`, `ml/` (including `ml/fusion_runtime.py`, `ml/models/`, `ml/replay/`, `ml/collect/`), `docs/ROLE_B_NOTES.md`, `docs/ML_RESULTS.md` | Role B |
| `node/requirements*.txt`, `node/hwlock.py` | Role A (Role B asks for additions) |

### B.2 Vision (Role A provides) — `node/vision/features.py`
```python
class VisionFeatureExtractor:
    def __init__(self, settings) -> None: ...
    def start(self) -> None: ...          # opens the camera, starts the capture thread
    def window(self) -> dict: ...         # features over all frames since the previous call
    def stop(self) -> None: ...
# window() returns:
# {"hand_present": bool, "gesture_conf": float 0..1 (3 dp), "tremor": float >= 0 (3 dp),
#  "n_frames": int, "n_hand_frames": int, "fps": float}
```
`node.settings.Settings.load()` returns default settings that work for this class.

### B.3 Biosignals (Role B provides) — package `node/bio/`
```python
# node/bio/__init__.py
def make_bio_source(mode: str, settings) -> "BioSource": ...
#   mode: "live" | "replay:rest" | "replay:exertion" | "manual"
class BioUnavailable(Exception): ...      # raised by make_bio_source/start() if the mode can't run

class BioSource:
    kind: str                             # "live" | "replay" | "manual"
    def start(self) -> None: ...
    def window(self) -> dict: ...         # values over the last ~3 s
    def baseline_hr(self) -> int | None: ...
    def stop(self) -> None: ...
# window() returns:
# {"hr": int | None, "spo2": int | None, "hr_delta": int | None,
#  "finger": bool, "source": "live" | "replay" | "manual", "quality": float 0..1}
```
- `live`: reads the MAX30100 (I2C bus 1, `0x57`) through `smbus2`; takes the hardware lock only when run standalone (inside `node.main` the node already holds it); `calibrate_baseline(seconds=60)` sets the baseline. `hr_delta = hr − baseline`.
- `replay:*`: plays `ml/replay/{rest|exertion}.csv` (columns `t_s,hr,spo2`, 1 row per second) in real time, looping; `hr_delta = hr − baseline_hr` from the matching `.json`; restarting the source restarts the file from row 0.
- `manual`: values typed by the operator (used only by the data collector).
- Values are `None` when there is no valid reading (no finger, poor signal).

### B.4 Fusion model (Role B provides) — `ml/fusion_runtime.py` + `ml/models/model.json`
```python
class FusionModel:
    FEATURES = ["gesture_conf", "tremor", "hr_delta", "spo2"]   # fixed order
    CLASSES  = ["routine", "urgent", "critical"]
    @classmethod
    def load(cls, path) -> "FusionModel": ...
    def predict_proba(self, features: dict) -> dict: ...  # {"routine": p, "urgent": p, "critical": p}, sums to 1
```
- NumPy only (no scikit-learn needed on the Pi): `z = (x − mean) / scale`, `logits = W·z + b`, softmax.
- `model.json`: `{"version", "trained_at", "features", "classes", "mean", "scale", "coef" (3×4, rows in "classes" order), "intercept" (3), "n_train", "sklearn_version"}`.
- **Rule baseline** (fixed before data collection, used by both roles): `critical` if `gesture_conf ≥ 0.8 and hr_delta ≥ 15`; `urgent` if `gesture_conf ≥ 0.8`; else `routine`.

### B.5 Hardware lock
`node/hwlock.py`: `with HardwareLock("name"):` takes an exclusive non-blocking `flock` on `/tmp/icu-hw.lock`; raises `HardwareBusy` with the holder's name and PID. Every program that opens the camera or I2C devices uses it.
