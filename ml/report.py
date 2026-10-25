"""Generate docs/ML_RESULTS.md from the step-3 outputs (ml.train_composed). Every number is read from files.

Usage: python -m ml.report [--results ml/results] [--models ml/models] [--replay ml/replay]
                           [--out docs/ML_RESULTS.md]

Reads metrics.json (+ data_report.md if present) from --results, model.json from --models and the replay
JSONs/CSVs from --replay. Refuses to write synthetic results to docs/ML_RESULTS.md.
"""

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import os
import sys

import numpy as np

from ml.collect.recorder import git_commit
from ml.fusion_runtime import FusionModel
from ml.rule import rule_level
from ml.schema import CLASSES, FEATURES

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_DOC = (REPO_ROOT / "docs" / "ML_RESULTS.md").resolve()
DESIGN_NOTE = ("**Why no gesture + abnormal vitals = routine.** Our system is a patient-initiated alert channel; "
               "vitals-only deterioration is handled by the standard ICU bedside monitor alarms, so a desaturating "
               "patient without a gesture stays routine in our system by design. This matches the expected case 3 "
               "in our proposal.")
METHOD_NAMES = {"model": "Fusion model (LR)", "rule": "Fixed rule", "gesture_only": "Gesture only"}
FOLD_COLS = [("accuracy", "Accuracy"), ("macro_f1", "Macro-F1"), ("alert_recall", "Alert recall"),
             ("alert_fpr", "Alert FPR"), ("critical_precision", "Critical precision"),
             ("critical_recall", "Critical recall")]


def f3(v):
    return "—" if v is None else f"{v:.3f}"


def pct(v):
    return "—" if v is None else f"{100 * v:.1f}%"


def ms(x):
    return "—" if x["mean"] is None else f"{x['mean']:.3f} ± {x['sd']:.3f}"


def _table(headers, rows):
    return ["| " + " | ".join(headers) + " |", "|" + " --- |" * len(headers)] + \
           ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def _replay_rows(replay_dir: Path):
    out = {}
    for kind in ("rest", "exertion"):
        j, c = replay_dir / f"{kind}.json", replay_dir / f"{kind}.csv"
        if j.exists() and c.exists():
            meta = json.loads(j.read_text(encoding="utf-8"))
            with c.open(newline="", encoding="utf-8") as fh:
                rows = [(int(r["hr"]), int(r["spo2"])) for r in csv.DictReader(fh)]
            out[kind] = (meta, rows)
    return out


def _replay_windows(rows, baseline_hr):
    """(hr_delta, spo2) of every window ReplayBio produces over one loop (1-s steps, 3-s rolling mean)."""
    n, out = len(rows), []
    for pos in range(n):
        w = [rows[(pos - k) % n] for k in range(2, -1, -1)]
        hr = int(round(sum(r[0] for r in w) / 3))
        out.append((hr - baseline_hr, int(round(sum(r[1] for r in w) / 3))))
    return out


def four_case(model_json: Path, pairs_csv: Path, replay: dict):
    """Model and rule on (no palm / palm) x (rest / exertion replay), using median gesture features."""
    if not (model_json.exists() and pairs_csv.exists() and len(replay) == 2):
        return None
    import pandas as pd
    pairs = pd.read_csv(pairs_csv)
    model = FusionModel.load(model_json)
    gesture = {g: pairs[pairs["gesture"] == g][["gesture_conf", "tremor"]].median().to_dict()
               for g in ("no_gesture", "gesture")}
    cases = []
    for g, palm in (("no_gesture", "no palm"), ("gesture", "palm")):
        for kind in ("rest", "exertion"):
            meta, rows = replay[kind]
            hr = float(np.mean([r[0] for r in rows]))
            feats = {"gesture_conf": float(gesture[g]["gesture_conf"]), "tremor": float(gesture[g]["tremor"]),
                     "hr_delta": hr - meta["baseline_hr"], "spo2": float(np.mean([r[1] for r in rows]))}
            p = model.predict_proba(feats)
            expected = ("routine" if g == "no_gesture" else "urgent" if kind == "rest" else "critical")
            # every 3-s window the node sees over one replay loop (node.bio.replay.ReplayBio)
            hits = []
            for w in _replay_windows(rows, meta["baseline_hr"]):
                pw = model.predict_proba({**feats, "hr_delta": float(w[0]), "spo2": float(w[1])})
                hits.append(max(pw, key=pw.get) == expected)
            cases.append({"case": f"{palm} + {kind} replay", "features": feats, "proba": p,
                          "model": max(p, key=p.get), "rule": rule_level(feats), "expected": expected,
                          "windows_ok": sum(hits), "windows": len(hits)})
    return cases


def tremor_note(m: dict, pairs_csv: Path) -> str:
    """Honest reading of the tremor coefficients, with the per-scenario medians from the training pairs."""
    c = {k: m["coefficients"][k]["tremor"] for k in CLASSES}
    if max(c, key=c.get) != "routine":
        return (f"**Tremor coefficient.** routine {c['routine']:+.3f}, urgent {c['urgent']:+.3f}, critical "
                f"{c['critical']:+.3f}. Establishing tremor's clinical value needs patient data (future work).")
    medians = ""
    if pairs_csv.exists():
        import pandas as pd
        # every window of a scenario appears equally often in the pairs, so the medians equal the raw ones
        pairs = pd.read_csv(pairs_csv)
        med = pairs.groupby("scenario")["tremor"].median().sort_values(ascending=False)
        medians = (" (median tremor per 3-s window: " + ", ".join(f"{k} {v:.3f}" for k, v in med.head(3).items())
                   + f"; G_PALM {med.get('G_PALM', float('nan')):.3f})")
    return ("**Tremor coefficient — what it does and does not show.** The tremor coefficient is highest for routine "
            f"({c['routine']:+.3f}; urgent {c['urgent']:+.3f}, critical {c['critical']:+.3f}). The tremor feature "
            "measures fingertip movement over 3 s; in our recordings the largest movements came from incidental "
            f"actions (scratching, adjusting){medians}, so the model uses high movement as evidence of an accidental "
            "movement (routine). It does not show that clinical tremor indicates safety; establishing tremor's "
            "clinical value needs patient data (future work).")


def discussion(m: dict, cases) -> list[str]:
    mean, pooled = m["mean"], m["pooled"]
    acc = {k: mean[k]["accuracy"]["mean"] for k in mean}
    out = []
    d = acc["model"] - acc["rule"]
    wins = sum(1 for f in m["folds"] if f["model"]["accuracy"] > f["rule"]["accuracy"])
    out.append(f"- **Model vs rule.** Mean accuracy {f3(acc['model'])} vs {f3(acc['rule'])} "
               f"({'+' if d >= 0 else ''}{100 * d:.1f} percentage points); the model was more accurate in "
               f"{wins} of {len(m['folds'])} folds.")
    cr_m, cr_r = mean["model"]["critical_recall"]["mean"], mean["rule"]["critical_recall"]["mean"]
    if cr_m is not None and cr_r is not None:
        why = ""
        vit_path = Path(m["dataset"]["vitals_csv"])
        if vit_path.exists():
            import pandas as pd
            ab = pd.read_csv(vit_path).query("label == 'abnormal'")
            spo2_only = int(((ab["spo2"] <= 93) & (ab["hr"] < 111)).sum())
            why = (f" In the vitals data, {spo2_only} of {len(ab)} abnormal windows ({pct(spo2_only / len(ab))}) "
                   "are abnormal only because of low SpO₂, which the rule cannot see.")
        out.append(f"- **Critical cases.** The model found {pct(cr_m)} of critical pairs on average, the rule "
                   f"{pct(cr_r)}. The rule only uses heart rate (ΔHR ≥ 15); the model can also use SpO₂.{why}")
    out.append(f"- **Gesture only** cannot output critical, so its accuracy is capped near two thirds on balanced "
               f"classes (mean {f3(acc['gesture_only'])}). Its alert recall ({pct(mean['gesture_only']['alert_recall']['mean'])}) "
               "equals the rule's, because both raise an alert on the same gesture threshold.")
    fpr = mean["model"]["alert_fpr"]["mean"]
    out.append(f"- **False alerts.** The model raised an alert for {pct(fpr)} of routine pairs (rule: "
               f"{pct(mean['rule']['alert_fpr']['mean'])}).")
    by_sc = m["dataset"].get("gesture_conf_by_scenario", {})
    false_hi = {k: v for k, v in by_sc.items() if v["label"] == "no_gesture" and v["share_ge_0_8"] >= 0.5}
    missed = {k: v for k, v in by_sc.items() if v["label"] == "gesture" and v["share_ge_0_8"] < 0.5}
    if false_hi:
        out.append("- **Where the false alerts come from.** No-gesture scenarios where most windows still scored "
                   "gesture_conf ≥ 0.8: " + "; ".join(f"{k} ({pct(v['share_ge_0_8'])} of {v['windows']} windows, median "
                   f"{v['median']:.2f})" for k, v in false_hi.items())
                   + ". Labels come from the scenario and were not changed; the gesture detector (uncalibrated "
                   "defaults) could not tell this resting hand from a raised palm.")
    if missed:
        out.append("- **Gestures the detector mostly missed:** " + "; ".join(
            f"{k} ({pct(v['share_ge_0_8'])} of windows ≥ 0.8, median {v['median']:.2f})" for k, v in missed.items()) + ".")
    worst = min(m["folds"], key=lambda f: f["model"]["accuracy"])
    best = max(m["folds"], key=lambda f: f["model"]["accuracy"])
    out.append(f"- **Spread between folds.** Model accuracy ranged from {f3(worst['model']['accuracy'])} "
               f"({worst['test_person']} × patient group {worst['test_group']}) to {f3(best['model']['accuracy'])} "
               f"({best['test_person']} × group {best['test_group']}); SD {f3(mean['model']['accuracy']['sd'])}.")
    rs = m["random_split"]
    out.append(f"- **Random split.** A random 5-fold split gives {f3(rs['accuracy'])} "
               f"({'+' if rs['accuracy'] >= acc['model'] else ''}{100 * (rs['accuracy'] - acc['model']):.1f} points "
               "vs the grouped split): the same participant and patient appear on both sides, so it overstates "
               "performance for a new person and a new patient. The grouped split is the number to report.")
    c = m["coefficients"]
    diff = {ft: c["critical"][ft] - c["urgent"][ft] for ft in FEATURES}
    top = max(diff, key=lambda k: abs(diff[k]))
    out.append(f"- **What separates critical from urgent.** Largest coefficient difference (critical − urgent): "
               f"`{top}` ({diff[top]:+.2f} per standard deviation). ΔHR {diff['hr_delta']:+.2f}, "
               f"SpO₂ {diff['spo2']:+.2f}, gesture_conf {diff['gesture_conf']:+.2f}, tremor {diff['tremor']:+.2f}.")
    gr = {ft: c["urgent"][ft] - c["routine"][ft] for ft in FEATURES}
    out.append(f"- **What separates urgent from routine.** gesture_conf {gr['gesture_conf']:+.2f}, tremor "
               f"{gr['tremor']:+.2f}, ΔHR {gr['hr_delta']:+.2f}, SpO₂ {gr['spo2']:+.2f}.")
    if cases:
        ok = sum(1 for x in cases if x["model"] == x["expected"])
        out.append(f"- **Four-case check (demo inputs).** The model gave the expected level in {ok} of 4 cases "
                   "(table above).")
    return out


def build(results_dir, models_dir, replay_dir) -> str:
    results_dir, models_dir, replay_dir = Path(results_dir), Path(models_dir), Path(replay_dir)
    m = json.loads((results_dir / "metrics.json").read_text(encoding="utf-8"))
    if m.get("kind") != "composed":
        raise SystemExit(f"{results_dir / 'metrics.json'} is not from ml.train_composed")
    ds, mean, pooled = m["dataset"], m["mean"], m["pooled"]
    replay = _replay_rows(replay_dir)
    cases = four_case(models_dir / "model.json", results_dir / "final_pairs.csv", replay)
    try:
        rel = os.path.relpath(results_dir.resolve(), REAL_DOC.parent)
    except ValueError:
        rel = str(results_dir.resolve())

    L = ["# ML results — composed gesture + ICU-vitals dataset", ""]
    if m["synthetic"]:
        L += ["> **SYNTHETIC GESTURE DATA — pipeline test only. Not a result; never use in the report.**", ""]
    L += [f"Generated by `python -m ml.report` on {datetime.now():%Y-%m-%d %H:%M} from `{results_dir}` "
          f"(commit `{git_commit()}`). Do not edit by hand; re-run the generator.", ""]

    L += ["## 1. Data", "",
          "The dataset is **composed**: gesture windows and vital-sign windows come from different people and "
          "were **not recorded at the same time**. They are paired afterwards by a fixed rule.", "",
          f"- **Gestures:** our Pi camera, gesture-only protocol (`ml.collect.session --bio none`), "
          f"{len(ds['participants'])} healthy participants ({', '.join(ds['participants'])}). 30-s trials of 3-s "
          "windows, labelled `gesture` / `no_gesture` by the scenario before recording. The first window of each "
          "trial and redone (discarded) trials are dropped.",
          f"- **Vitals:** BIDMC PPG and Respiration Dataset (PhysioNet), {ds['n_patients']} ICU patients, 3-s "
          "windows of HR and SpO₂ labelled with NEWS2-based rules (`ml/data/public/README.md`): "
          f"{ds['vitals_windows'].get('normal', 0)} normal, {ds['vitals_windows'].get('abnormal', 0)} abnormal.",
          f"- **Pairing rule:** {m['pairing']['rule']}. Classes balanced ({m['pairing']['balanced']}); "
          f"seed {m['seed']}.", ""]
    if m["pairing"]["no_gesture_abnormal"] == "routine":
        L += [DESIGN_NOTE, ""]
    L += _table(["participant", "gesture windows", "no_gesture windows"],
                [[p, v.get("gesture", 0), v.get("no_gesture", 0)] for p, v in ds["gesture_windows_per_person"].items()])
    ex = ds["gesture_exclusions"]
    ad = ex.get("attempts_dropped")
    if ad:
        L += ["", f"Redone trials: {ad['total']} attempt(s) dropped, keeping one attempt per trial "
                  f"({len(ad['flagged_discarded'])} flagged as discarded by the operator"
                  + (f": {', '.join(ad['flagged_discarded'])}" if ad["flagged_discarded"] else "")
                  + f"; {len(ad['unflagged_duplicates'])} unflagged duplicate(s) dropped as older attempts"
                  + (f": {', '.join(ad['unflagged_duplicates'])}" if ad["unflagged_duplicates"] else "") + ")."]
    L += ["", f"Dropped before pairing: {ex['first_window']} first windows, {ex['discarded_windows']} windows from "
              f"{ex['discarded_trials']} discarded trial(s). Final model trained on {m['final']['n_pairs']} pairs "
              f"({', '.join(f'{k} {v}' for k, v in m['final']['windows_per_label'].items())}).", ""]

    L += ["## 2. Method", "",
          f"- **Features:** {', '.join(f'`{x}`' for x in FEATURES)} (ΔHR = HR − 75 bpm adult resting reference).",
          f"- **Model:** {m['model_desc']}. No hyper-parameter tuning.",
          f"- **Evaluation:** leave-one-participant-out × BIDMC patient-grouped split: patients in "
          f"{m['split']['vitals_folds']} groups, each with both normal and abnormal patients; each of the "
          f"{len(m['folds'])} folds holds out one participant **and** one patient group, so test pairs never share "
          "a person or an ICU patient with training pairs. With "
          f"{len(ds['participants'])} participants, leave-one-participant-out has only {len(ds['participants'])} "
          f"folds (× {m['split']['vitals_folds']} patient groups = {len(m['folds'])} folds in total), so each model "
          f"is trained on the gestures of {'a single participant' if len(ds['participants']) == 2 else 'the other participants'}.",
          "- **Baselines on the same test pairs:** fixed rule (critical if gesture_conf ≥ 0.8 and ΔHR ≥ 15; urgent "
          "if gesture_conf ≥ 0.8; else routine) and gesture only (urgent if gesture_conf ≥ 0.8, else routine).", ""]

    L += ["## 3. Results (mean ± SD over folds)", ""]
    L += _table(["Method"] + [h for _, h in FOLD_COLS],
                [[METHOD_NAMES[n]] + [ms(mean[n][k]) for k, _ in FOLD_COLS] for n in METHOD_NAMES])
    L += ["", "Alert = urgent or critical. FPR = share of routine pairs that raised an alert.", "",
          "### Per fold", ""]
    L += _table(["Fold", "Held-out participant", "Patient group", "Test pairs", "Model acc", "Rule acc",
                 "Gesture-only acc", "Model critical recall"],
                [[f["fold"], f["test_person"], f["test_group"], f["n_test"], f3(f["model"]["accuracy"]),
                  f3(f["rule"]["accuracy"]), f3(f["gesture_only"]["accuracy"]), f3(f["model"]["critical_recall"])]
                 for f in m["folds"]])
    L += ["", "### Confusion matrices (all test pairs pooled; rows = true, columns = predicted)", ""]
    for n in METHOD_NAMES:
        L += [f"**{METHOD_NAMES[n]}** (accuracy {f3(pooled[n]['accuracy'])}, macro-F1 {f3(pooled[n]['macro_f1'])})", ""]
        L += _table(["true \\ predicted"] + CLASSES,
                    [[c] + pooled[n]["confusion"][i] for i, c in enumerate(CLASSES)])
        L.append("")
    L += [f"![Confusion matrices]({rel}/confusion.png)", "",
          "### Random split (comparison only)", "",
          f"Random 5-fold split of all pairs: accuracy {f3(m['random_split']['accuracy'])}, macro-F1 "
          f"{f3(m['random_split']['macro_f1'])}. {m['random_split']['note']}", "",
          "### Final model coefficients (standardised features)", ""]
    L += _table(["Class"] + FEATURES + ["intercept"],
                [[c] + [f"{m['coefficients'][c][ft]:+.3f}" for ft in FEATURES]
                 + [f"{m['coefficients'][c]['intercept']:+.3f}"] for c in CLASSES])
    L += ["", tremor_note(m, results_dir / "final_pairs.csv"), "",
          f"![Coefficients]({rel}/coefficients.png)", "",
          f"Exported to `model.json`; the NumPy runtime on the Pi matches scikit-learn to "
          f"{m['final']['parity_max_abs_diff']:.1e} (max absolute probability difference).", ""]

    L += ["## 4. Demo replay inputs and four-case check", ""]
    if replay:
        L += _table(["Replay", "BIDMC record", "Seconds", "HR (min–max)", "SpO₂ (min–max)", "Selection"],
                    [[k, f"{meta['record']} (s {meta['start_s']}–{meta['end_s']})", meta["seconds"],
                      f"{meta['hr_min']}–{meta['hr_max']}", f"{meta['spo2_min']}–{meta['spo2_max']}", meta["selection"]]
                     for k, (meta, _) in replay.items()])
        L.append("")
    if cases:
        L += ["Median gesture_conf/tremor of the gesture and no_gesture windows, with the mean HR/SpO₂ of each replay "
              "file:", ""]
        L += _table(["Case", "gesture_conf", "ΔHR", "SpO₂", "p(routine/urgent/critical)", "Model", "Rule", "Expected",
                     "Model = expected, every replay window"],
                    [[x["case"], f"{x['features']['gesture_conf']:.2f}", f"{x['features']['hr_delta']:+.0f}",
                      f"{x['features']['spo2']:.1f}", " / ".join(f"{x['proba'][c]:.2f}" for c in CLASSES),
                      x["model"], x["rule"], x["expected"], f"{x['windows_ok']}/{x['windows']}"] for x in cases])
        L.append("")
    else:
        L += ["Four-case check not available (needs model.json, final_pairs.csv and both replay files).", ""]

    L += ["## 5. Discussion (generated from the numbers above)", ""] + discussion(m, cases) + [""]
    L += ["## 6. Limitations", "",
          "- **Composed data.** Gestures and vitals were never recorded together; the pairing rule creates the "
          "labels. The results show how well the model combines the two signals, not how real patients behave.",
          f"- **{len(ds['participants'])} healthy participants** acting out gestures; real patients may move "
          "differently (weakness, sedation, lines and dressings).",
          "- **NEWS2 as ground truth** for the vitals: a clinical early-warning score, not a diagnosis. Borderline "
          "1-point bands were excluded, which makes the vitals classes easier to separate than in practice.",
          "- **Low heart rate excluded** (HR ≤ 50): logistic regression with a linear ΔHR cannot treat both very low "
          "and very high HR as abnormal.",
          "- **ΔHR uses a fixed 75 bpm reference**, not each patient's own baseline.",
          "- **No hyper-parameter tuning, one model family**; the patient grouping and pairing use one fixed seed.", ""]
    if (results_dir / "data_report.md").exists():
        L += ["## Appendix: gesture data validation", "", "See `data_report.md` in the results folder "
              f"(`{results_dir / 'data_report.md'}`)."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate docs/ML_RESULTS.md from the step-3 outputs")
    parser.add_argument("--results", default="ml/results")
    parser.add_argument("--models", default="ml/models")
    parser.add_argument("--replay", default="ml/replay")
    parser.add_argument("--out", default=str(REAL_DOC))
    args = parser.parse_args(argv)
    doc = build(args.results, args.models, args.replay)
    synthetic = json.loads((Path(args.results) / "metrics.json").read_text(encoding="utf-8"))["synthetic"]
    if synthetic and Path(args.out).resolve() == REAL_DOC:
        raise SystemExit("refusing to write synthetic results to docs/ML_RESULTS.md (use --out <temp file>)")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(doc, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
