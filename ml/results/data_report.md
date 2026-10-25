# Data report

- Folder: `ml/data/raw`
- Files read: 52
- Rows: 520
- People: P1, P2
- Bio mode(s): none
- Protocol: gesture-only (label column: gesture)

## Trials per person × scenario (not discarded)

| person | G_PALM | G_PALM_DIM | G_WEAK | G_PALM_SHAKY | N_REST | N_SCRATCH | N_OTHER | N_NOHAND | N_REST_SHAKY |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 | 6 | 2 | 2 | 2 | 4 | 4 | 2 | 1 | 1 |
| P2 | 6 | 2 | 2 | 2 | 4 | 4 | 2 | 1 | 1 |

## Discarded trials

- P1_G_WEAK_T1_20261025-212051
- P1_N_REST_T1_20261025-205241
- P1_N_REST_T1_20261025-205335
- P2_G_WEAK_T2_20261025-214225

## Windows per label after exclusions (§12.1)

| gesture | windows |
| --- | --- |
| no_gesture | 216 |
| gesture | 216 |

Excluded: 52 first windows, 36 windows from 4 discarded trial(s), 0 windows with missing hr_delta/spo2

## Per trial

| trial | label | windows | gesture_conf | hand_present | hr_delta | finger | bio_mode |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P1_G_PALM_T1_20261025-204408 | gesture | 10 | 0.931 | 1.00 | — | — | none |
| P1_G_PALM_T2_20261025-204636 | gesture | 10 | 0.935 | 1.00 | — | — | none |
| P1_G_PALM_T3_20261025-211106 | gesture | 10 | 0.940 | 1.00 | — | — | none |
| P1_G_PALM_T4_20261025-212225 | gesture | 10 | 0.953 | 1.00 | — | — | none |
| P1_G_PALM_T5_20261025-210116 | gesture | 10 | 0.984 | 1.00 | — | — | none |
| P1_G_PALM_T6_20261025-211953 | gesture | 10 | 0.953 | 1.00 | — | — | none |
| P1_G_PALM_DIM_T1_20261025-203056 | gesture | 10 | 0.894 | 1.00 | — | — | none |
| P1_G_PALM_DIM_T2_20261025-204150 | gesture | 10 | 0.956 | 1.00 | — | — | none |
| P1_G_PALM_SHAKY_T1_20261025-205717 | gesture | 10 | 0.868 | 1.00 | — | — | none |
| P1_G_PALM_SHAKY_T2_20261025-202829 | gesture | 10 | 0.938 | 1.00 | — | — | none |
| P1_G_WEAK_T1_20261025-212127 | gesture | 10 | 0.950 | 1.00 | — | — | none |
| P1_G_WEAK_T2_20261025-202947 | gesture | 10 | 0.252 | 1.00 | — | — | none |
| P1_N_NOHAND_T1_20261025-210216 | no_gesture | 10 | 0.000 | 0.00 | — | — | none |
| P1_N_OTHER_T1_20261025-210549 | no_gesture | 10 | 0.000 | 1.00 | — | — | none |
| P1_N_OTHER_T2_20261025-210959 | no_gesture | 10 | 0.000 | 1.00 | — | — | none |
| P1_N_REST_T1_20261025-205541 | no_gesture | 10 | 0.156 | 1.00 | — | — | none |
| P1_N_REST_T2_20261025-205818 | no_gesture | 10 | 0.524 | 1.00 | — | — | none |
| P1_N_REST_T3_20261025-203323 | no_gesture | 10 | 0.000 | 1.00 | — | — | none |
| P1_N_REST_T4_20261025-203423 | no_gesture | 10 | 0.094 | 1.00 | — | — | none |
| P1_N_REST_SHAKY_T1_20261025-203518 | no_gesture | 10 | 0.000 | 1.00 | — | — | none |
| P1_N_SCRATCH_T1_20261025-211300 | no_gesture | 10 | 0.140 | 1.00 | — | — | none |
| P1_N_SCRATCH_T2_20261025-203640 | no_gesture | 10 | 0.160 | 0.90 | — | — | none |
| P1_N_SCRATCH_T3_20261025-211634 | no_gesture | 10 | 0.000 | 1.00 | — | — | none |
| P1_N_SCRATCH_T4_20261025-211202 | no_gesture | 10 | 0.293 | 1.00 | — | — | none |
| P2_G_PALM_T1_20261025-214851 | gesture | 10 | 1.000 | 1.00 | — | — | none |
| P2_G_PALM_T2_20261025-222758 | gesture | 10 | 0.981 | 1.00 | — | — | none |
| P2_G_PALM_T3_20261025-221404 | gesture | 10 | 1.000 | 1.00 | — | — | none |
| P2_G_PALM_T4_20261025-222223 | gesture | 10 | 1.000 | 1.00 | — | — | none |
| P2_G_PALM_T5_20261025-222357 | gesture | 10 | 1.000 | 1.00 | — | — | none |
| P2_G_PALM_T6_20261025-215217 | gesture | 10 | 0.999 | 1.00 | — | — | none |
| P2_G_PALM_DIM_T1_20261025-215633 | gesture | 10 | 0.981 | 1.00 | — | — | none |
| P2_G_PALM_DIM_T2_20261025-221736 | gesture | 10 | 1.000 | 1.00 | — | — | none |
| P2_G_PALM_SHAKY_T1_20261025-220655 | gesture | 10 | 0.984 | 1.00 | — | — | none |
| P2_G_PALM_SHAKY_T2_20261025-214652 | gesture | 10 | 0.993 | 1.00 | — | — | none |
| P2_G_WEAK_T1_20261025-220532 | gesture | 10 | 0.831 | 1.00 | — | — | none |
| P2_G_WEAK_T2_20261025-214316 | gesture | 10 | 0.947 | 1.00 | — | — | none |
| P2_N_NOHAND_T1_20261025-214752 | no_gesture | 10 | 0.000 | 0.00 | — | — | none |
| P2_N_OTHER_T1_20261025-220217 | no_gesture | 10 | 0.000 | 1.00 | — | — | none |
| P2_N_OTHER_T2_20261025-220010 | no_gesture | 10 | 0.003 | 1.00 | — | — | none |
| P2_N_REST_T1_20261025-220421 | no_gesture | 10 | 0.873 | 1.00 | — | — | none |
| P2_N_REST_T2_20261025-215856 | no_gesture | 10 | 0.945 | 1.00 | — | — | none |
| P2_N_REST_T3_20261025-221224 | no_gesture | 10 | 0.556 | 1.00 | — | — | none |
| P2_N_REST_T4_20261025-220946 | no_gesture | 10 | 0.838 | 1.00 | — | — | none |
| P2_N_REST_SHAKY_T1_20261025-214531 | no_gesture | 10 | 0.938 | 1.00 | — | — | none |
| P2_N_SCRATCH_T1_20261025-214411 | no_gesture | 10 | 0.230 | 1.00 | — | — | none |
| P2_N_SCRATCH_T2_20261025-222628 | no_gesture | 10 | 0.394 | 1.00 | — | — | none |
| P2_N_SCRATCH_T3_20261025-220315 | no_gesture | 10 | 0.280 | 0.90 | — | — | none |
| P2_N_SCRATCH_T4_20261025-221504 | no_gesture | 10 | 0.166 | 1.00 | — | — | none |

## Flags (for review with the team; nothing was changed)

None.

## Result

OK: enough data to train.
