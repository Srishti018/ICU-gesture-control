"""Train and evaluate the 3-class fusion model (laptop only).

Usage: python -m ml.train --data ml/data/raw --out ml/results [--models ml/models]

Leave-one-person-out evaluation of the model against the fixed rule and the
gesture-only rule; a random 5-fold split for comparison only; final fit on all
data, exported to model.joblib + model.json. No hyper-parameter tuning.
"""

import argparse
import json
from pathlib import Path
import sys

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support  # noqa: E402
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from ml.dataset import apply_exclusions, is_synthetic, load_windows  # noqa: E402
from ml.export import export  # noqa: E402
from ml.rule import gesture_only_level, rule_level  # noqa: E402
from ml.schema import CLASSES, FEATURES  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTECTED = [(REPO_ROOT / "ml" / "models").resolve(), (REPO_ROOT / "ml" / "results").resolve()]
RANDOM_STATE = 42
METHODS = ["model", "rule", "gesture_only"]
RANDOM_SPLIT_NOTE = ("A random split looks better because windows from the same 30-s trial are near-copies, "
                     "so the test folds contain near-duplicates of training rows; leave-one-person-out "
                     "is the honest estimate for a new patient.")


def build_pipeline() -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()),
        ("lr", LogisticRegression(C=1.0, class_weight="balanced", max_iter=2000, random_state=RANDOM_STATE)),
    ])


def _r(v, digits=4):
    return None if v is None or v != v else round(float(v), digits)


def _safe_div(a, b):
    return a / b if b else None


def method_metrics(y_true, y_pred, groups) -> dict:
    y_true, y_pred, groups = np.asarray(y_true), np.asarray(y_pred), np.asarray(groups)
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=CLASSES, zero_division=0)
    per_class = {c: {"precision": _r(p[i]), "recall": _r(r[i]), "f1": _r(f[i]), "support": int(s[i])}
                 for i, c in enumerate(CLASSES)}
    true_alert, pred_alert = y_true != "routine", y_pred != "routine"
    tp = int((true_alert & pred_alert).sum())
    routine = ~true_alert
    crit_t, crit_p = y_true == "critical", y_pred == "critical"
    return {
        "accuracy": _r(accuracy_score(y_true, y_pred)),
        "macro_f1": _r(f1_score(y_true, y_pred, labels=CLASSES, average="macro", zero_division=0)),
        "per_class": per_class,
        "confusion": confusion_matrix(y_true, y_pred, labels=CLASSES).tolist(),
        "alert": {
            "precision": _r(_safe_div(tp, int(pred_alert.sum()))),
            "recall": _r(_safe_div(tp, int(true_alert.sum()))),
            "false_positive_rate": _r(_safe_div(int((routine & pred_alert).sum()), int(routine.sum()))),
        },
        "critical": {
            "precision": _r(_safe_div(int((crit_t & crit_p).sum()), int(crit_p.sum()))),
            "recall": _r(_safe_div(int((crit_t & crit_p).sum()), int(crit_t.sum()))),
        },
        "per_person_accuracy": {str(g): _r(accuracy_score(y_true[groups == g], y_pred[groups == g]))
                                for g in sorted(set(groups))},
    }


def _check_outputs(paths, synthetic: bool) -> None:
    if not synthetic:
        return
    for p in paths:
        p = Path(p).resolve()
        if any(p == prot or prot in p.parents for prot in PROTECTED):
            raise SystemExit(f"refusing to write synthetic-data results into {p} (synthetic data is for tests only)")


def _confusion_chart(metrics: dict, path: Path, title_note: str) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    for ax, name in zip(axes, METHODS):
        cm = np.array(metrics[name]["confusion"])
        ax.imshow(cm, cmap="Blues")
        ax.set_xticks(range(3), CLASSES)
        ax.set_yticks(range(3), CLASSES)
        ax.set_xlabel("predicted")
        ax.set_ylabel("true")
        ax.set_title(f"{name} (acc {metrics[name]['accuracy']:.2f})")
        vmax = cm.max() or 1
        for i in range(3):
            for j in range(3):
                ax.text(j, i, int(cm[i, j]), ha="center", va="center",
                        color="white" if cm[i, j] > vmax / 2 else "black")
    fig.suptitle("Leave-one-person-out confusion matrices" + title_note)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _coef_chart(coef: np.ndarray, path: Path, title_note: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.2))
    x = np.arange(len(FEATURES))
    width = 0.26
    for i, c in enumerate(CLASSES):
        ax.bar(x + (i - 1) * width, coef[i], width, label=c)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x, FEATURES)
    ax.set_ylabel("coefficient (standardised feature)")
    ax.set_title("Final model coefficients" + title_note)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _metrics_md(m: dict) -> str:
    lines = ["# Model evaluation", ""]
    if m["synthetic"]:
        lines += ["> **SYNTHETIC DATA — pipeline test only. Not a result; never use in the report.**", ""]
    lines += [f"Windows after exclusions: {m['n_windows']} · people: {', '.join(m['people'])} · "
              f"evaluation: leave-one-person-out · model: {m['model_desc']}", ""]
    lines += ["## Comparison (held-out people)", "",
              "| method | accuracy | macro-F1 | alert precision | alert recall | alert FPR | critical precision | critical recall |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    f = lambda v: "—" if v is None else f"{v:.3f}"  # noqa: E731
    for name in METHODS:
        x = m["methods"][name]
        lines.append(f"| {name} | {f(x['accuracy'])} | {f(x['macro_f1'])} | {f(x['alert']['precision'])} | "
                     f"{f(x['alert']['recall'])} | {f(x['alert']['false_positive_rate'])} | "
                     f"{f(x['critical']['precision'])} | {f(x['critical']['recall'])} |")
    for name in METHODS:
        x = m["methods"][name]
        lines += ["", f"### {name}", "", "| | precision | recall | F1 | support |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {c} | {f(x['per_class'][c]['precision'])} | {f(x['per_class'][c]['recall'])} | "
                  f"{f(x['per_class'][c]['f1'])} | {x['per_class'][c]['support']} |" for c in CLASSES]
        lines += ["", "Confusion (rows = true, columns = predicted):", "",
                  "| true \\ pred | " + " | ".join(CLASSES) + " |", "| --- | --- | --- | --- |"]
        lines += [f"| {c} | " + " | ".join(str(v) for v in x["confusion"][i]) + " |" for i, c in enumerate(CLASSES)]
        lines += ["", "Per-person accuracy: " + ", ".join(f"{p} {f(a)}" for p, a in x["per_person_accuracy"].items())]
    rs = m["random_split"]
    lines += ["", "## Random 5-fold split (comparison only)", "",
              f"Model accuracy {f(rs['accuracy'])}, macro-F1 {f(rs['macro_f1'])} "
              f"(leave-one-person-out: {f(m['methods']['model']['accuracy'])}, {f(m['methods']['model']['macro_f1'])}).",
              "", rs["note"], ""]
    lines += ["## Final model coefficients (standardised features)", "",
              "| class | " + " | ".join(FEATURES) + " | intercept |", "| --- " * (len(FEATURES) + 2) + "|"]
    for c in CLASSES:
        row = m["coefficients"][c]
        lines.append(f"| {c} | " + " | ".join(f"{row[ft]:+.3f}" for ft in FEATURES) + f" | {row['intercept']:+.3f} |")
    lines += ["", "No hyper-parameter tuning (too little data): C=1.0, class_weight=balanced."]
    return "\n".join(lines) + "\n"


def train(data_dir, out_dir, models_dir=None) -> dict:
    out_dir = Path(out_dir)
    models_dir = Path(models_dir) if models_dir else out_dir
    data = load_windows(data_dir)
    synthetic = is_synthetic(data)
    _check_outputs([out_dir, models_dir], synthetic)
    kept, excl = apply_exclusions(data)
    print(f"windows: {len(data)} loaded, {len(kept)} kept after exclusions {excl}")

    X = kept[FEATURES].astype(float).to_numpy()
    y = kept["label"].astype(str).to_numpy()
    groups = kept["person"].astype(str).to_numpy()
    people = sorted(set(groups))
    if len(people) < 2:
        raise SystemExit("leave-one-person-out needs at least 2 people")

    pred = np.empty(len(y), dtype=object)
    for train_idx, test_idx in LeaveOneGroupOut().split(X, y, groups):
        model = build_pipeline().fit(X[train_idx], y[train_idx])
        pred[test_idx] = model.predict(X[test_idx])
    rows = kept[FEATURES].to_dict("records")
    preds = {
        "model": pred.astype(str),
        "rule": np.array([rule_level(r) for r in rows]),
        "gesture_only": np.array([gesture_only_level(r) for r in rows]),
    }
    methods = {name: method_metrics(y, preds[name], groups) for name in METHODS}

    rs_pred = np.empty(len(y), dtype=object)
    for train_idx, test_idx in StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE).split(X, y):
        rs_pred[test_idx] = build_pipeline().fit(X[train_idx], y[train_idx]).predict(X[test_idx])
    rs_pred = rs_pred.astype(str)
    random_split = {
        "accuracy": _r(accuracy_score(y, rs_pred)),
        "macro_f1": _r(f1_score(y, rs_pred, labels=CLASSES, average="macro", zero_division=0)),
        "note": RANDOM_SPLIT_NOTE,
    }

    final = build_pipeline().fit(X, y)
    models_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, models_dir / "model.joblib")
    exported = export(final, models_dir / "model.json", n_train=len(y))
    coef = np.array(exported["coef"])
    coefficients = {c: {**{ft: float(coef[i, j]) for j, ft in enumerate(FEATURES)},
                        "intercept": float(exported["intercept"][i])} for i, c in enumerate(CLASSES)}
    with (out_dir / "coefficients.csv").open("w", encoding="utf-8") as fh:
        fh.write("class," + ",".join(FEATURES) + ",intercept\n")
        for c in CLASSES:
            fh.write(c + "," + ",".join(f"{coefficients[c][ft]:.6f}" for ft in FEATURES)
                     + f",{coefficients[c]['intercept']:.6f}\n")

    metrics = {
        "synthetic": synthetic,
        "n_windows": int(len(y)),
        "people": people,
        "exclusions": excl,
        "windows_per_label": {c: int((y == c).sum()) for c in CLASSES},
        "model_desc": "StandardScaler + LogisticRegression(C=1.0, class_weight=balanced, max_iter=2000)",
        "methods": methods,
        "random_split": random_split,
        "coefficients": coefficients,
    }
    note = " — SYNTHETIC (pipeline test)" if synthetic else ""
    _confusion_chart(methods, out_dir / "confusion.png", note)
    _coef_chart(coef, out_dir / "coefficients.png", note)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (out_dir / "metrics.md").write_text(_metrics_md(metrics), encoding="utf-8")
    print(f"LOPO accuracy: model {methods['model']['accuracy']}, rule {methods['rule']['accuracy']}, "
          f"gesture-only {methods['gesture_only']['accuracy']}; outputs in {out_dir}, model in {models_dir}")
    return metrics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Train and evaluate the fusion model")
    parser.add_argument("--data", default="ml/data/raw")
    parser.add_argument("--out", default="ml/results")
    parser.add_argument("--models", default=None, help="where to save model.joblib/model.json (default: --out)")
    args = parser.parse_args(argv)
    train(args.data, args.out, args.models)
    return 0


if __name__ == "__main__":
    sys.exit(main())
