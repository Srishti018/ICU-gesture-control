"""Fusion: Role B's trained model (ml/fusion_runtime.py), or the fixed rule as a fallback."""

import logging

from node.payload import LEVELS

log = logging.getLogger("node.fusion")

GESTURE_THRESHOLD = 0.8
HR_DELTA_THRESHOLD = 15


class RuleFusion:
    """Same rule as Role B's baseline (docs/NODE_INTERFACES.md §B.4); 0.90 on the chosen level."""

    mode = "rule"

    def predict_proba(self, f: dict) -> dict:
        gesture = float(f["gesture_conf"]) >= GESTURE_THRESHOLD
        level = "critical" if gesture and float(f["hr_delta"]) >= HR_DELTA_THRESHOLD else \
                "urgent" if gesture else "routine"
        return {lv: (0.90 if lv == level else 0.05) for lv in LEVELS}


class ModelFusion:
    mode = "model"

    def __init__(self, model):
        self.model = model

    def predict_proba(self, f: dict) -> dict:
        return self.model.predict_proba(f)


def load_fusion(settings, mode: str):
    """mode "model" falls back to the rule (with a clear log line) if the model can't load."""
    if mode == "rule":
        log.info("fusion: fixed rule (requested)")
        return RuleFusion()
    if mode != "model":
        raise ValueError(f"unknown fusion mode {mode!r}")
    try:
        from ml.fusion_runtime import FusionModel
        model = FusionModel.load(settings.model_path)
    except FileNotFoundError:
        log.warning("MODEL NOT FOUND (%s), using rule fallback", settings.model_path)
        return RuleFusion()
    except (ImportError, ValueError, KeyError) as e:
        log.warning("MODEL NOT USABLE (%s: %s), using rule fallback", settings.model_path, e)
        return RuleFusion()
    log.info("fusion: model %s (trained %s, n=%s)", settings.model_path,
             model.meta.get("trained_at"), model.meta.get("n_train"))
    return ModelFusion(model)
