# Composed-dataset evaluation

Participants: P1, P2 · BIDMC patients: 49 in 3 groups · folds: 6 · seed 42 · no_gesture + abnormal → routine

## Mean over folds (held-out participant × held-out patient group)

| method | accuracy | macro_f1 | alert_recall | alert_fpr | critical_precision | critical_recall |
| --- | --- | --- | --- | --- | --- | --- |
| model | 0.819 ± 0.074 | 0.815 ± 0.076 | 0.931 ± 0.079 | 0.219 ± 0.234 | 0.868 ± 0.110 | 0.785 ± 0.174 |
| rule | 0.731 ± 0.071 | 0.722 ± 0.074 | 0.940 ± 0.035 | 0.153 ± 0.167 | 0.766 ± 0.104 | 0.506 ± 0.158 |
| gesture_only | 0.596 ± 0.044 | 0.492 ± 0.031 | 0.940 ± 0.035 | 0.153 ± 0.167 | — | 0.000 ± 0.000 |

## Per fold

| fold | person | patient group | test pairs | model acc | rule acc | gesture-only acc | model macro-F1 | model critical recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | P1 | 0 | 324 | 0.910 | 0.772 | 0.636 | 0.912 | 0.880 |
| 1 | P1 | 1 | 324 | 0.827 | 0.732 | 0.636 | 0.820 | 0.593 |
| 2 | P1 | 2 | 324 | 0.886 | 0.827 | 0.636 | 0.884 | 0.907 |
| 3 | P2 | 0 | 324 | 0.772 | 0.688 | 0.556 | 0.765 | 0.759 |
| 4 | P2 | 1 | 324 | 0.710 | 0.620 | 0.556 | 0.707 | 0.574 |
| 5 | P2 | 2 | 324 | 0.809 | 0.747 | 0.556 | 0.803 | 1.000 |

## Pooled test pairs (all folds)

### model

accuracy 0.819, macro-F1 0.819

| true \ pred | routine | urgent | critical |
| --- | --- | --- | --- |
| routine | 506 | 81 | 61 |
| urgent | 40 | 577 | 31 |
| critical | 49 | 90 | 509 |

### rule

accuracy 0.731, macro-F1 0.726

| true \ pred | routine | urgent | critical |
| --- | --- | --- | --- |
| routine | 549 | 63 | 36 |
| urgent | 39 | 544 | 65 |
| critical | 39 | 281 | 328 |

### gesture_only

accuracy 0.596, macro-F1 0.494

| true \ pred | routine | urgent | critical |
| --- | --- | --- | --- |
| routine | 549 | 99 | 0 |
| urgent | 39 | 609 | 0 |
| critical | 39 | 609 | 0 |

## Random 5-fold split (comparison only)

Model accuracy 0.884, macro-F1 0.883 (grouped split mean: 0.819, 0.815).

A random split looks better because the same participant and the same ICU patient appear in both training and test pairs (and windows from one 30-s trial or one patient recording are near-copies). The participant x patient-grouped split is the honest estimate for a new person and a new patient.

## Final model coefficients (standardised features)

| class | gesture_conf | tremor | hr_delta | spo2 | intercept |
| --- | --- | --- | --- | --- | --- |
| routine | -1.744 | +0.865 | +0.069 | -0.197 | +0.687 |
| urgent | +0.937 | -0.488 | -1.169 | +2.010 | -0.474 |
| critical | +0.808 | -0.377 | +1.100 | -1.813 | -0.213 |

Final model: 648 pairs; runtime parity max |Δp| = 2.22e-16 (< 1e-09).
No hyper-parameter tuning: C=1.0, class_weight=balanced.
