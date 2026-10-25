"""Train and evaluate the fusion model on the COMPOSED dataset (laptop only).

Usage: python -m ml.train_composed --gestures ml/data/raw --vitals ml/data/public/bidmc_news2_windows.csv
       [--out ml/results] [--models ml/models] [--vitals-folds 3] [--seed 42]
       [--no-gesture-abnormal routine|exclude]

The dataset is composed, not recorded simultaneously: gesture windows from our Pi camera
(gesture-only protocol, `ml.collect.session --bio none`) are paired with real ICU vitals windows
from BIDMC labelled with NEWS2 rules (`ml/bidmc_windows.py`).

Pairing rule (labels come from the two source labels only, never from the feature values):
  gesture    + NEWS2 normal   -> urgent
  gesture    + NEWS2 abnormal -> critical
  no_gesture + NEWS2 normal   -> routine
  no_gesture + NEWS2 abnormal -> routine (default: alerts in this system are patient-initiated;
                                 vitals-only alarms belong to the bedside monitor)
                                 or left out with --no-gesture-abnormal exclude
Every gesture window (first window of each trial and discarded trials dropped) is used once with a
normal and once with an abnormal vitals window, so urgent and critical differ only in the vitals.
Classes are balanced: n = min(#gesture, #no_gesture) windows per class; routine is half
normal, half abnormal vitals (or all normal with `exclude`). Vitals windows are drawn at random
without replacement where the pool allows. All randomness uses --seed.

Evaluation: leave-one-gesture-participant-out x BIDMC patient-grouped split. Patients are put into
K groups (stratified, so every group has both normal and abnormal patients). Every fold holds out
one participant AND one patient group; training pairs use only the other participants and the
other patient groups, test pairs only the held-out ones. Model, rule and gesture-only are scored on
the same test pairs. A random 5-fold split of the full pair set is reported for comparison only.
The final model is fitted on all pairs, exported to model.json and checked for runtime parity.
"""

import argparse
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold

from ml.dataset import apply_exclusions, is_gesture_only, is_synthetic, load_windows
from ml.export import export
from ml.fusion_runtime import FusionModel
from ml.rule import gesture_only_level, rule_level
from ml.schema import CLASSES, FEATURES
from ml.train import (METHODS, PROTECTED, _coef_chart, _confusion_chart, _r, build_pipeline,
                      method_metrics)

DEFAULT_SEED = 42
DEFAULT_VITALS_FOLDS = 3
PARITY_TOLERANCE = 1e-9
FOLD_METRICS = ["accuracy", "macro_f1", "alert_recall", "alert_fpr", "critical_precision", "critical_recall"]
RANDOM_SPLIT_NOTE = ("A random split looks better because the same participant and the same ICU patient "
                     "appear in both training and test pairs (and windows from one 30-s trial or one patient "
                     "recording are near-copies). The participant x patient-grouped split is the honest "
                     "estimate for a new person and a new patient.")


# --- data -------------------------------------------------------------------------------------------

def load_gestures(folder) -> pd.DataFrame:
    data = load_windows(folder)
    if not is_gesture_only(data):
        raise SystemExit(f"{folder}: these are not gesture-only files (no 'gesture' column); "
                         "record them with `python -m ml.collect.session --bio none`")
    discarded_attempts = sorted(data.loc[data["discarded"] == 1, "trial_id"].unique())
    # A redone trial whose earlier attempt was not flagged: keep only the latest non-discarded attempt.
    # trial_id ends in _YYYYMMDD-HHMMSS, so the latest attempt sorts last.
    live = data[data["discarded"] == 0].drop_duplicates("trial_id")
    unflagged = []
    for _, attempts in live.groupby(["person", "scenario", "trial"])["trial_id"]:
        unflagged += sorted(attempts)[:-1]
    data.loc[data["trial_id"].isin(unflagged), "discarded"] = 1
    kept, excl = apply_exclusions(data)  # drops first window of each trial and discarded attempts
    excl["attempts_dropped"] = {"flagged_discarded": discarded_attempts, "unflagged_duplicates": sorted(unflagged),
                                "total": len(discarded_attempts) + len(unflagged)}
    kept = kept[["person", "trial_id", "scenario", "gesture", "gesture_conf", "tremor"]].copy()
    kept["gesture_conf"] = kept["gesture_conf"].astype(float)
    kept["tremor"] = kept["tremor"].astype(float)
    if kept[["gesture_conf", "tremor"]].isna().any().any():
        raise SystemExit("gesture windows with missing gesture_conf/tremor")
    kept.attrs["synthetic"] = is_synthetic(data)
    kept.attrs["exclusions"] = excl
    return kept.reset_index(drop=True)


def load_vitals(path) -> pd.DataFrame:
    v = pd.read_csv(path)
    missing = {"patient", "hr_delta", "spo2", "label"} - set(v.columns)
    if missing:
        raise SystemExit(f"{path}: missing columns {sorted(missing)}")
    if not set(v["label"]) <= {"normal", "abnormal"}:
        raise SystemExit(f"{path}: labels must be normal/abnormal")
    return v.reset_index(drop=True)


def patient_groups(vitals: pd.DataFrame, k: int, seed: int) -> dict:
    """Patient -> group 0..k-1. Stratified by each patient's majority label, balancing window counts."""
    counts = vitals.groupby(["patient", "label"]).size().unstack(fill_value=0)
    for c in ("normal", "abnormal"):
        if c not in counts:
            counts[c] = 0
    majority = np.where(counts["abnormal"] > counts["normal"], "abnormal", "normal")
    rng = np.random.default_rng(seed)
    groups = {}
    for label in ("normal", "abnormal"):
        patients = list(counts.index[majority == label])
        if len(patients) < k:
            raise SystemExit(f"only {len(patients)} {label}-majority patients; cannot make {k} groups")
        rng.shuffle(patients)
        patients.sort(key=lambda p: -int(counts.loc[p].sum()))  # stable: shuffled order breaks ties
        load = [0] * k
        for p in patients:
            g = int(np.argmin(load))
            groups[p] = g
            load[g] += int(counts.loc[p].sum())
    for g in range(k):
        labels = set(vitals.loc[vitals["patient"].map(groups) == g, "label"])
        if labels != {"normal", "abnormal"}:
            raise SystemExit(f"patient group {g} lacks normal or abnormal windows")
    return groups


def _draw(pool: pd.DataFrame, n: int, rng) -> pd.DataFrame:
    idx = rng.choice(len(pool), size=n, replace=len(pool) < n)
    return pool.iloc[idx].reset_index(drop=True)


def compose(gest: pd.DataFrame, vit: pd.DataFrame, rng, no_gesture_abnormal: str = "routine") -> pd.DataFrame:
    """Pair gesture windows with vitals windows by the pairing rule; balanced classes."""
    G = gest[gest["gesture"] == "gesture"]
    N = gest[gest["gesture"] == "no_gesture"]
    VN = vit[vit["label"] == "normal"]
    VA = vit[vit["label"] == "abnormal"]
    n = min(len(G), len(N))
    if n == 0 or len(VN) == 0 or len(VA) == 0:
        raise ValueError(f"cannot compose: {len(G)} gesture, {len(N)} no_gesture, "
                         f"{len(VN)} normal, {len(VA)} abnormal windows")
    G = G.iloc[np.sort(rng.choice(len(G), n, replace=False))].reset_index(drop=True)
    N = N.iloc[np.sort(rng.choice(len(N), n, replace=False))].reset_index(drop=True)
    if no_gesture_abnormal == "routine":
        half = rng.permutation(n) < n // 2
        n_parts = [(N[~half], VN), (N[half], VA)]
    else:
        n_parts = [(N, VN)]
    parts = [(G, VN, "urgent"), (G, VA, "critical")] + [(g, v, "routine") for g, v in n_parts]
    frames = []
    for g, pool, level in parts:
        v = _draw(pool, len(g), rng)
        frames.append(pd.DataFrame({
            "person": g["person"].to_numpy(), "trial_id": g["trial_id"].to_numpy(),
            "scenario": g["scenario"].to_numpy(), "gesture": g["gesture"].to_numpy(),
            "patient": v["patient"].to_numpy(), "vitals_label": v["label"].to_numpy(),
            "gesture_conf": g["gesture_conf"].to_numpy(), "tremor": g["tremor"].to_numpy(),
            "hr_delta": v["hr_delta"].astype(float).to_numpy(), "spo2": v["spo2"].astype(float).to_numpy(),
            "label": level,
        }))
    return pd.concat(frames, ignore_index=True)


# --- evaluation -------------------------------------------------------------------------------------

def predict_all(model, pairs: pd.DataFrame) -> dict:
    rows = pairs[FEATURES].to_dict("records")
    return {
        "model": model.predict(pairs[FEATURES].to_numpy()).astype(str),
        "rule": np.array([rule_level(r) for r in rows]),
        "gesture_only": np.array([gesture_only_level(r) for r in rows]),
    }


def fold_summary(y, pred) -> dict:
    m = method_metrics(y, pred, np.zeros(len(y)))
    return {"accuracy": m["accuracy"], "macro_f1": m["macro_f1"], "alert_recall": m["alert"]["recall"],
            "alert_fpr": m["alert"]["false_positive_rate"], "critical_precision": m["critical"]["precision"],
            "critical_recall": m["critical"]["recall"]}


def _mean_sd(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return {"mean": None, "sd": None}
    return {"mean": _r(np.mean(vals)), "sd": _r(np.std(vals, ddof=1) if len(vals) > 1 else 0.0)}


def evaluate_folds(gest, vit, groups, vitals_folds, seed, no_gesture_abnormal, verbose=False):
    """The held-out evaluation: per-fold summaries and every test pair with each method's prediction
    (columns pred_model / pred_rule / pred_gesture_only). Deterministic for a given seed."""
    vit = vit.assign(group=vit["patient"].map(groups))
    folds, tests, fold_no = [], [], 0
    for person in sorted(gest["person"].unique()):
        for g in range(vitals_folds):
            rng = np.random.default_rng([seed, fold_no])
            train = compose(gest[gest["person"] != person], vit[vit["group"] != g], rng, no_gesture_abnormal)
            test = compose(gest[gest["person"] == person], vit[vit["group"] == g], rng, no_gesture_abnormal)
            model = build_pipeline().fit(train[FEATURES].to_numpy(), train["label"].to_numpy())
            preds = predict_all(model, test)
            y = test["label"].to_numpy()
            fold = {"fold": fold_no, "test_person": person, "test_group": g,
                    "test_patients": sorted(p for p, gg in groups.items() if gg == g),
                    "n_train": int(len(train)), "n_test": int(len(test))}
            fold.update({name: fold_summary(y, preds[name]) for name in METHODS})
            folds.append(fold)
            tests.append(test.assign(fold=fold_no, **{f"pred_{n}": preds[n] for n in METHODS}))
            if verbose:
                print(f"fold {fold_no}: test {person} x group {g} ({fold['n_test']} pairs): "
                      + ", ".join(f"{n} {fold[n]['accuracy']}" for n in METHODS))
            fold_no += 1
    return folds, pd.concat(tests, ignore_index=True)


def pooled_metrics(test_pairs: pd.DataFrame) -> dict:
    y, persons = test_pairs["label"].to_numpy(), test_pairs["person"].to_numpy()
    return {n: method_metrics(y, test_pairs[f"pred_{n}"].to_numpy(), persons) for n in METHODS}


def check_parity(pipe, model_json: Path, pairs: pd.DataFrame) -> float:
    runtime = FusionModel.load(model_json)
    sk = pipe.predict_proba(pairs[FEATURES].to_numpy())
    sk = sk[:, [list(pipe.classes_).index(c) for c in CLASSES]]
    worst = 0.0
    for i, row in enumerate(pairs[FEATURES].to_dict("records")):
        p = runtime.predict_proba({k: float(v) for k, v in row.items()})
        worst = max(worst, float(np.max(np.abs(np.array([p[c] for c in CLASSES]) - sk[i]))))
    if worst >= PARITY_TOLERANCE:
        raise SystemExit(f"PARITY FAILED: runtime differs from scikit-learn by {worst:.2e}")
    return worst


def _check_outputs(paths, synthetic: bool) -> None:
    if not synthetic:
        return
    for p in paths:
        p = Path(p).resolve()
        if any(p == prot or prot in p.parents for prot in PROTECTED):
            raise SystemExit(f"refusing to write synthetic-data results into {p} (synthetic data is for tests only)")


def _fmt_mean_sd(x: dict) -> str:
    return "—" if x["mean"] is None else f"{x['mean']:.3f} ± {x['sd']:.3f}"


def _metrics_md(m: dict) -> str:
    f = lambda v: "—" if v is None else f"{v:.3f}"  # noqa: E731
    lines = ["# Composed-dataset evaluation", ""]
    if m["synthetic"]:
        lines += ["> **SYNTHETIC GESTURE DATA — pipeline test only. Not a result; never use in the report.**", ""]
    d = m["dataset"]
    lines += [f"Participants: {', '.join(d['participants'])} · BIDMC patients: {d['n_patients']} in "
              f"{m['split']['vitals_folds']} groups · folds: {len(m['folds'])} · seed {m['seed']} · "
              f"no_gesture + abnormal → {m['pairing']['no_gesture_abnormal']}", "",
              "## Mean over folds (held-out participant × held-out patient group)", "",
              "| method | " + " | ".join(FOLD_METRICS) + " |", "| --- " * (len(FOLD_METRICS) + 1) + "|"]
    for name in METHODS:
        lines.append(f"| {name} | " + " | ".join(_fmt_mean_sd(m["mean"][name][k]) for k in FOLD_METRICS) + " |")
    lines += ["", "## Per fold", "", "| fold | person | patient group | test pairs | model acc | rule acc | "
              "gesture-only acc | model macro-F1 | model critical recall |", "| --- " * 9 + "|"]
    for fd in m["folds"]:
        lines.append(f"| {fd['fold']} | {fd['test_person']} | {fd['test_group']} | {fd['n_test']} | "
                     f"{f(fd['model']['accuracy'])} | {f(fd['rule']['accuracy'])} | "
                     f"{f(fd['gesture_only']['accuracy'])} | {f(fd['model']['macro_f1'])} | "
                     f"{f(fd['model']['critical_recall'])} |")
    lines += ["", "## Pooled test pairs (all folds)", ""]
    for name in METHODS:
        x = m["pooled"][name]
        lines += [f"### {name}", "", f"accuracy {f(x['accuracy'])}, macro-F1 {f(x['macro_f1'])}", "",
                  "| true \\ pred | " + " | ".join(CLASSES) + " |", "| --- | --- | --- | --- |"]
        lines += [f"| {c} | " + " | ".join(str(v) for v in x["confusion"][i]) + " |" for i, c in enumerate(CLASSES)]
        lines.append("")
    rs = m["random_split"]
    lines += ["## Random 5-fold split (comparison only)", "",
              f"Model accuracy {f(rs['accuracy'])}, macro-F1 {f(rs['macro_f1'])} (grouped split mean: "
              f"{f(m['mean']['model']['accuracy']['mean'])}, {f(m['mean']['model']['macro_f1']['mean'])}).",
              "", rs["note"], "", "## Final model coefficients (standardised features)", "",
              "| class | " + " | ".join(FEATURES) + " | intercept |", "| --- " * (len(FEATURES) + 2) + "|"]
    for c in CLASSES:
        row = m["coefficients"][c]
        lines.append(f"| {c} | " + " | ".join(f"{row[ft]:+.3f}" for ft in FEATURES) + f" | {row['intercept']:+.3f} |")
    lines += ["", f"Final model: {m['final']['n_pairs']} pairs; runtime parity max |Δp| = "
              f"{m['final']['parity_max_abs_diff']:.2e} (< {PARITY_TOLERANCE:g}).",
              "No hyper-parameter tuning: C=1.0, class_weight=balanced."]
    return "\n".join(lines) + "\n"


def run(gestures_dir, vitals_csv, out_dir, models_dir=None, *, vitals_folds=DEFAULT_VITALS_FOLDS,
        seed=DEFAULT_SEED, no_gesture_abnormal="routine") -> dict:
    out_dir = Path(out_dir)
    models_dir = Path(models_dir) if models_dir else out_dir
    gest = load_gestures(gestures_dir)
    synthetic = bool(gest.attrs["synthetic"])
    _check_outputs([out_dir, models_dir], synthetic)
    vit = load_vitals(vitals_csv)
    people = sorted(gest["person"].unique())
    if len(people) < 2:
        raise SystemExit("leave-one-participant-out needs at least 2 participants")
    groups = patient_groups(vit, vitals_folds, seed)
    vit["group"] = vit["patient"].map(groups)
    print(f"gesture windows: {len(gest)} kept ({gest['gesture'].value_counts().to_dict()}), people {people}; "
          f"vitals windows: {len(vit)} ({vit['label'].value_counts().to_dict()}), {len(groups)} patients")

    folds, test_pairs = evaluate_folds(gest, vit, groups, vitals_folds, seed, no_gesture_abnormal, verbose=True)
    pooled = pooled_metrics(test_pairs)
    mean = {n: {k: _mean_sd([fd[n][k] for fd in folds]) for k in FOLD_METRICS} for n in METHODS}

    all_pairs = compose(gest, vit, np.random.default_rng([seed, 9999]), no_gesture_abnormal)
    X, y = all_pairs[FEATURES].to_numpy(), all_pairs["label"].to_numpy()
    rs_pred = np.empty(len(y), dtype=object)
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=seed).split(X, y):
        rs_pred[te] = build_pipeline().fit(X[tr], y[tr]).predict(X[te])
    rs_pred = rs_pred.astype(str)
    random_split = {"accuracy": _r(accuracy_score(y, rs_pred)),
                    "macro_f1": _r(f1_score(y, rs_pred, labels=CLASSES, average="macro", zero_division=0)),
                    "note": RANDOM_SPLIT_NOTE}

    final = build_pipeline().fit(X, y)
    models_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, models_dir / "model.joblib")
    exported = export(final, models_dir / "model.json", n_train=len(y))
    parity = check_parity(final, models_dir / "model.json", all_pairs)
    all_pairs.to_csv(out_dir / "final_pairs.csv", index=False)
    coef = np.array(exported["coef"])
    coefficients = {c: {**{ft: float(coef[i, j]) for j, ft in enumerate(FEATURES)},
                        "intercept": float(exported["intercept"][i])} for i, c in enumerate(CLASSES)}
    with (out_dir / "coefficients.csv").open("w", encoding="utf-8") as fh:
        fh.write("class," + ",".join(FEATURES) + ",intercept\n")
        for c in CLASSES:
            fh.write(c + "," + ",".join(f"{coefficients[c][ft]:.6f}" for ft in FEATURES)
                     + f",{coefficients[c]['intercept']:.6f}\n")
    pd.DataFrame([{"fold": fd["fold"], "test_person": fd["test_person"], "test_group": fd["test_group"],
                   "n_train": fd["n_train"], "n_test": fd["n_test"],
                   **{f"{n}_{k}": fd[n][k] for n in METHODS for k in FOLD_METRICS}} for fd in folds]
                 ).to_csv(out_dir / "per_fold.csv", index=False)

    metrics = {
        "kind": "composed",
        "synthetic": synthetic,
        "seed": seed,
        "dataset": {
            "participants": people,
            "gesture_windows": {k: int(v) for k, v in gest["gesture"].value_counts().items()},
            "gesture_windows_per_person": {p: {k: int(v) for k, v in gest[gest["person"] == p]["gesture"]
                                               .value_counts().items()} for p in people},
            "gesture_exclusions": gest.attrs["exclusions"],
            "gesture_conf_by_scenario": {
                f"{p}/{sc}": {"label": str(d["gesture"].iloc[0]), "windows": int(len(d)),
                              "median": _r(d["gesture_conf"].median()),
                              "share_ge_0_8": _r((d["gesture_conf"] >= 0.8).mean())}
                for (p, sc), d in gest.groupby(["person", "scenario"])},
            "vitals_csv": str(vitals_csv),
            "vitals_windows": {k: int(v) for k, v in vit["label"].value_counts().items()},
            "n_patients": int(vit["patient"].nunique()),
        },
        "pairing": {"no_gesture_abnormal": no_gesture_abnormal,
                    "rule": "gesture+normal=urgent, gesture+abnormal=critical, no_gesture+normal=routine, "
                            f"no_gesture+abnormal={no_gesture_abnormal}",
                    "balanced": "n = min(#gesture, #no_gesture) windows per class"},
        "split": {"kind": "leave-one-participant-out x patient-grouped", "vitals_folds": vitals_folds,
                  "patient_groups": {str(g): sorted(p for p, gg in groups.items() if gg == g)
                                     for g in range(vitals_folds)}},
        "model_desc": "StandardScaler + LogisticRegression(C=1.0, class_weight=balanced, max_iter=2000)",
        "folds": folds,
        "mean": mean,
        "pooled": pooled,
        "random_split": random_split,
        "coefficients": coefficients,
        "final": {"n_pairs": int(len(y)), "windows_per_label": {c: int((y == c).sum()) for c in CLASSES},
                  "parity_max_abs_diff": parity, "model_json": str(models_dir / "model.json")},
    }
    note = " — SYNTHETIC (pipeline test)" if synthetic else ""
    _confusion_chart(pooled, out_dir / "confusion.png", note,
                     title="Participant × patient-grouped confusion matrices (pooled test pairs)")
    _coef_chart(coef, out_dir / "coefficients.png", note)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    (out_dir / "metrics.md").write_text(_metrics_md(metrics), encoding="utf-8")
    print("mean accuracy: " + ", ".join(f"{n} {mean[n]['accuracy']['mean']}" for n in METHODS)
          + f"; random split {random_split['accuracy']}; parity {parity:.1e}")
    print(f"outputs in {out_dir}, model in {models_dir}")
    return metrics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Train and evaluate the fusion model on the composed dataset")
    parser.add_argument("--gestures", default="ml/data/raw", help="folder of gesture-only *_windows.csv files")
    parser.add_argument("--vitals", default="ml/data/public/bidmc_news2_windows.csv")
    parser.add_argument("--out", default="ml/results")
    parser.add_argument("--models", default="ml/models", help="where to save model.joblib/model.json")
    parser.add_argument("--vitals-folds", type=int, default=DEFAULT_VITALS_FOLDS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--no-gesture-abnormal", choices=["routine", "exclude"], default="routine")
    args = parser.parse_args(argv)
    run(args.gestures, args.vitals, args.out, args.models, vitals_folds=args.vitals_folds, seed=args.seed,
        no_gesture_abnormal=args.no_gesture_abnormal)
    return 0


if __name__ == "__main__":
    sys.exit(main())
