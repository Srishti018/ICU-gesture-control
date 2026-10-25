import pandas as pd
import numpy as np
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import confusion_matrix

FEATURES = ["gesture_conf", "tremor", "hr_delta", "spo2"]

df = pd.read_csv("samples.csv")

# ---------- cleanup (the CSV file itself is never changed) ----------
# relabel open-palm trials that were recorded as hr_only by mistake
fix = [1792662600, 1792662616, 1792662657]
df.loc[df["trial"].isin(fix), ["scenario", "label"]] = ["combined", 1]

# drop messy trials
df = df[~df["trial"].isin([1792662483, 1792662636, 1792662676])]

# drop rows where the palm wasn't really open but label says distress
df = df[~((df["label"] == 1) & (df["gesture_conf"] < 0.75))]

# drop tracking glitch rows (tremor warm-up zeros)
df = df[df["tremor"] > 0]
# ---------------------------------------------------------------------

print("Rows per scenario:")
print(df["scenario"].value_counts().to_string())
print("Trials per scenario:")
print(df.groupby("scenario")["trial"].nunique().to_string())

X, y, groups = df[FEATURES], df["label"], df["trial"]

# split by trial so rows from the same trial never appear in both train and test
splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
train_idx, test_idx = next(splitter.split(X, y, groups))
X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

print(f"\nTrain rows: {len(X_train)}  Test rows: {len(X_test)}")
print("Test label counts:", y_test.value_counts().to_dict())

model = make_pipeline(StandardScaler(), LogisticRegression())
model.fit(X_train, y_train)

def report(name, pred):
    tn, fp, fn, tp = confusion_matrix(y_test, pred, labels=[0, 1]).ravel()
    acc = (tp + tn) / (tp + tn + fp + fn)
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    fpr = fp / (fp + tn) if (fp + tn) else 0
    print(f"{name:14s} acc={acc:.2f} precision={prec:.2f} recall={rec:.2f} false_pos_rate={fpr:.2f}")

print()
proba = model.predict_proba(X_test)[:, 1]
report("LR (fusion)", (proba >= 0.5).astype(int))

# baselines on the SAME test data
report("gesture-only", (X_test["gesture_conf"] > 0.8).astype(int))
rule = ((X_test["gesture_conf"] > 0.8) & (X_test["hr_delta"] > 15)).astype(int)
report("rule-based", rule)

# what the model learned (features are standardized, so coefficients are comparable)
print("\nLearned coefficients:")
for name, coef in zip(FEATURES, model[-1].coef_[0]):
    print(f"  {name:13s} {coef:+.2f}")

joblib.dump(model, "fusion_model.pkl")
print("\nSaved fusion_model.pkl")

def severity(p):
    if p < 0.4:
        return "routine"
    if p < 0.7:
        return "urgent"
    return "critical"

print("\nSample severities:", [severity(p) for p in proba[:10]])