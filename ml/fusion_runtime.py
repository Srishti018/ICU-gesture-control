"""NumPy-only fusion model runtime (runs on the Pi). See docs/NODE_INTERFACES.md §B.4."""

import json
import math
from numbers import Real

import numpy as np


class FusionModel:
    FEATURES = ["gesture_conf", "tremor", "hr_delta", "spo2"]   # fixed order
    CLASSES = ["routine", "urgent", "critical"]

    def __init__(self, mean, scale, coef, intercept, meta=None):
        self.mean = np.asarray(mean, dtype=float)
        self.scale = np.asarray(scale, dtype=float)
        self.coef = np.asarray(coef, dtype=float)
        self.intercept = np.asarray(intercept, dtype=float)
        self.meta = meta or {}
        n_f, n_c = len(self.FEATURES), len(self.CLASSES)
        if self.mean.shape != (n_f,) or self.scale.shape != (n_f,):
            raise ValueError(f"mean/scale must have {n_f} values")
        if self.coef.shape != (n_c, n_f) or self.intercept.shape != (n_c,):
            raise ValueError(f"coef must be {n_c}x{n_f} and intercept {n_c} values")
        if np.any(self.scale == 0):
            raise ValueError("scale contains zero")

    @classmethod
    def load(cls, path) -> "FusionModel":
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("features") != cls.FEATURES:
            raise ValueError(f"model features {data.get('features')} != {cls.FEATURES}")
        if data.get("classes") != cls.CLASSES:
            raise ValueError(f"model classes {data.get('classes')} != {cls.CLASSES}")
        meta = {k: v for k, v in data.items() if k not in ("mean", "scale", "coef", "intercept")}
        return cls(data["mean"], data["scale"], data["coef"], data["intercept"], meta)

    def _vector(self, features: dict) -> np.ndarray:
        values = []
        for name in self.FEATURES:
            v = features.get(name)
            if isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(float(v)):
                raise ValueError(f"feature {name!r} is missing or not a number: {v!r}")
            values.append(float(v))
        return np.array(values, dtype=float)

    def predict_proba(self, features: dict) -> dict:
        z = (self._vector(features) - self.mean) / self.scale
        logits = self.coef @ z + self.intercept
        e = np.exp(logits - logits.max())
        p = e / e.sum()
        return {c: float(p[i]) for i, c in enumerate(self.CLASSES)}
