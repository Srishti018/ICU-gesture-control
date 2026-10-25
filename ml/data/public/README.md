# Public data: BIDMC vitals with NEWS2-based labels

`bidmc_news2_windows.csv` holds 3-second windows of heart rate (HR) and SpO2 from real ICU patients. Each window is labelled `normal` or `abnormal` with rules based on NEWS2. It is the vitals half of the composed fusion dataset; the gesture half is recorded with our own Pi camera (`python -m ml.collect.session --bio none`).

## Source and licence

- **Dataset:** BIDMC PPG and Respiration Dataset, version 1.0.0, PhysioNet: <https://physionet.org/content/bidmc/1.0.0/>. 53 adult ICU recordings of 8 minutes each, from Beth Israel Deaconess Medical Center.
- **Files used:** `bidmc_csv/bidmc_##_Numerics.csv` for all 53 patients. Columns are `Time [s], HR, PULSE, RESP, SpO2`, one row per second. We use only `HR` and `SpO2`.
- **Licence:** Open Data Commons Attribution License v1.0 (ODC-By 1.0). This derived file is shared under the same attribution terms.
- **Citation:** Pimentel, M. A. F., Johnson, A. E. W., Charlton, P. H., Birrenkott, D., Watkinson, P. J., Tarassenko, L., & Clifton, D. A. (2016). Toward a robust estimation of respiratory rate from pulse oximeters. *IEEE Transactions on Biomedical Engineering*, 64(8), 1914–1923. doi:10.1109/TBME.2016.2613124
- **PhysioNet:** Goldberger, A., et al. (2000). PhysioBank, PhysioToolkit, and PhysioNet. *Circulation*, 101(23), e215–e220.
- **Labelling reference:** Royal College of Physicians (2017). *National Early Warning Score (NEWS) 2: Standardising the assessment of acute-illness severity in the NHS.* London: RCP.

## How the windows were made

Regenerate the CSV with `python -I ml/bidmc_windows.py <folder with the Numerics CSVs>`.

1. Each patient's recording is cut into consecutive, non-overlapping 3-second windows: seconds 0–2, 3–5, and so on.
2. A window is used only if all 3 seconds have HR > 0 and SpO2 > 0. Windows with missing samples or sensor dropouts are skipped.
3. `hr` and `spo2` are the means of the 3 seconds.
4. `hr_delta = hr - 75`. 75 bpm is used as an adult resting reference because the patients have no personal baseline.

## Labelling rules (exact)

The rules are applied to the window means, in this order:

| Condition | Label |
| --- | --- |
| HR ≤ 50 | excluded |
| SpO2 ≤ 93 **or** HR ≥ 111 | `abnormal` |
| SpO2 ≥ 96 **and** 51 ≤ HR ≤ 90 | `normal` |
| anything else (SpO2 94–95, or HR 91–110 with SpO2 ≥ 94) | excluded |

How these rules map to NEWS2:

- `abnormal` means a single-parameter score of at least 2 on SpO2 Scale 1 (SpO2 ≤ 93) or on pulse (HR ≥ 111).
- `normal` means a score of 0 on both parameters.
- The borderline 1-point bands (SpO2 94–95 and HR 91–110) are excluded so that the two classes are clearly separated.

**Why HR ≤ 50 is excluded:** NEWS2 scores a low HR as abnormal too (41–50 scores 1 point; ≤ 40 scores 3). However, the fusion model is a logistic regression with `hr_delta` as a linear input, so it can only learn "the higher the HR, the more abnormal" (or the reverse). It cannot also flag a low HR. Keeping slow-HR windows labelled as abnormal would put both ends of the HR range in the same class and blur the HR effect, so they are left out. Only 1 window was removed by this rule.

## Columns

`patient` (bidmc_01 … bidmc_53), `window_idx` (index of the 3-s window in the recording), `t_start_s`, `hr`, `spo2`, `hr_delta`, `label` (`normal` / `abnormal`).

## Counts

- **Windows:** 5,271 in total: 3,392 normal and 1,879 abnormal.
- **Patients:** 49 of the 53 have at least one window. bidmc_05, 07, 14 and 15 fall only in the excluded bands.
- **What made windows abnormal:** SpO2 ≤ 93 alone in 1,294 windows, HR ≥ 111 alone in 446, and both in 139.

**Important for training:** the label is almost constant within each patient. Only 3 patients have windows of both classes. Any train/test split must therefore be **grouped by patient**. Otherwise windows from the same patient end up on both sides and the test score is inflated.
