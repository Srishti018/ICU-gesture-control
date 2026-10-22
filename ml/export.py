"""Export a fitted scaler + LogisticRegression pipeline to the JSON the Pi runtime loads."""

from datetime import datetime
import json
from pathlib import Path

import sklearn

from ml.schema import CLASSES, FEATURES


def export(pipeline, path, n_train: int) -> dict:
    scaler = pipeline.named_steps["scale"]
    lr = pipeline.named_steps["lr"]
    # scikit-learn sorts classes_ alphabetically (critical, routine, urgent);
    # reorder the rows into CLASSES order by name.
    sk_classes = [str(c) for c in lr.classes_]
    if sorted(sk_classes) != sorted(CLASSES):
        raise ValueError(f"model was trained on classes {sk_classes}, expected {CLASSES}")
    order = [sk_classes.index(c) for c in CLASSES]
    data = {
        "version": 1,
        "trained_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "features": list(FEATURES),
        "classes": list(CLASSES),
        "mean": [float(v) for v in scaler.mean_],
        "scale": [float(v) for v in scaler.scale_],
        "coef": [[float(v) for v in lr.coef_[i]] for i in order],
        "intercept": [float(lr.intercept_[i]) for i in order],
        "n_train": int(n_train),
        "sklearn_version": sklearn.__version__,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data
