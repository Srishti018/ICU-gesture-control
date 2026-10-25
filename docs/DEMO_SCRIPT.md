# Demo script — ICU Gesture + Biosignal Fusion

On stage: **Pi = `bed1`** (Pi camera, real gesture detection, ICU vitals replayed from BIDMC, fusion model) and the **fake node = `bed2`**. The laptop runs the broker, the server and the dashboard.

## Roles

| Role | Where | Does |
| --- | --- | --- |
| **Presenter** | facing the audience | says the one sentence for each step |
| **Patient** | seated in front of the Pi camera | makes the hand movements |
| **Operator** | laptop terminal: an SSH session attached to the Pi node | types the node keys (`r`, `x`) and runs `kill_node.sh` |
| **Nurse** | laptop browser, projected | refreshes the page and clicks **Acknowledge** |

The node reads a key when you type it **and press Enter**. The operator's terminal stays attached to the node with `ssh -t icu-pi tmux attach -t icu`.

---

## Pre-demo checklist (start 30 minutes before)

**Laptop**
- [ ] On the phone hotspot. Note the laptop's IP: `hostname -I`.
- [ ] `git pull`. Check that `ml/models/model.json` exists and `ml/replay/rest.json` says `"source": "BIDMC (PhysioNet)"`.
- [ ] `./stop_all.sh`, then `./scripts/reset_demo.sh` (empties the database and the retained alerts), then `./start_all.sh`. Wait for the three tabs and the dashboard URL.
- [ ] Open http://localhost:5173. Switch to the **light theme** (projector) and click **Enable sound**. The page should say "Waiting for bed devices…".
- [ ] Start `bed2` in a new terminal: `.venv/bin/python sim/fake_node.py --node bed2`. The Bed 2 tile shows Online / Routine.

**Pi**
- [ ] `node/tools/deploy.sh` (on the laptop: pushes and pulls on the Pi, installs requirements). If the broker IP changed, run `ssh icu-pi '~/icu-fusion/node/tools/set_broker.sh <laptop IP>'`.
- [ ] Start the node: `ssh icu-pi 'cd ~/icu-fusion && node/tools/run_demo.sh --node bed1 --camera picam'`. This runs `pi_check.sh` first, then `python -m node.main --bio replay:rest --fusion model --camera picam` in tmux session `icu`.
- [ ] Attach: `ssh -t icu-pi tmux attach -t icu`. The startup summary must show `fusion: model ml/models/model.json (trained …)`, **not** `MODEL NOT FOUND`, and bio = replay rest.
- [ ] The Bed 1 tile shows Online, Routine, the HR sparkline and the badge "Biosignals: replay".

**Room and rehearsal**
- [ ] Camera framing: the patient's raised palm fills about a third of the image, with steady light and no window behind the patient.
- [ ] Check the gesture with `s` + Enter: palm up gives gesture ≥ 0.8; resting hand gives low gesture.
- [ ] Do one full run of the 8 steps. Then reset: `./stop_all.sh` → `./scripts/reset_demo.sh` → `./start_all.sh`, and restart both nodes.
- [ ] `docs/ML_RESULTS.md` §4 four-case check: no palm + rest → routine, palm + rest → urgent, palm + exertion → critical. If not, use Fallback 1.

---

## The 8 steps

Before step 2, `bed1` runs the normal ICU replay (`r`). In step 6 the operator switches to the abnormal replay with `x`. Each alert needs the palm held for about 6 s (two 3-s windows).

| # | Who | Action | Key / command | Presenter says |
| --- | --- | --- | --- | --- |
| 1 | Presenter, Nurse | Show the dashboard with both beds Online and Routine. Point at the "Biosignals: replay" badge. | — | "Each bed device fuses the patient's hand gesture with their vital signs and reports routine, urgent or critical to this nurse station over MQTT." |
| 2 | Operator, Patient | Normal ICU vitals; the patient rests their hand in view. | Operator: `r` Enter | "The camera is live; the heart rate and SpO₂ are replayed from a real ICU patient with normal vitals, and with a resting hand the bed stays routine." |
| 3 | Patient | Scratch the face, adjust a sleeve, touch the hair. The tile stays **Routine**. | — | "Everyday movements don't raise an alarm: the model looks for a held, upright open palm, not just any hand movement." |
| 4 | Patient | Hold the open palm up to the camera for about 6 s. Bed 1 turns **URGENT** with a sound, and the alert strip shows the timer. | — | "Holding the palm up is the patient's call for help; with normal vitals it is urgent." |
| 5 | Nurse, Patient | The patient lowers their hand. The nurse clicks **Acknowledge** on Bed 1. The tile shows "Acknowledged · response N s". | Nurse: click **Acknowledge** | "The nurse acknowledges, and the system records how long the response took." |
| 6 | Operator, Patient | Switch to the abnormal ICU vitals (HR 115, SpO₂ 92–93). Wait about 5 s, then the patient holds the palm up for about 6 s. Bed 1 turns **CRITICAL**. | Operator: `x` Enter | "Now the replay is a real ICU patient with abnormal vitals by the NEWS2 score; the same gesture with these vitals becomes critical." |
| 7 | Nurse | Refresh the browser (F5). The critical alert is still there, because it is retained by the broker until acknowledged. Then click **Acknowledge**. Open History or Statistics. | Nurse: `F5`, then **Acknowledge** | "Alerts survive a dashboard restart until a nurse acknowledges them, and every alert and response time is logged." |
| 8 | Operator | Simulate a device failure. Within about 10 s Bed 1 shows **Offline**, sent by the broker's Last Will. Then restart the node; Bed 1 is Online again. | `ssh icu-pi '~/icu-fusion/node/tools/kill_node.sh'`; restart: `ssh icu-pi 'cd ~/icu-fusion && node/tools/stop_node.sh; node/tools/run_demo.sh --node bed1 --camera picam'` | "If a bed device dies without saying goodbye, the broker announces it offline, so a silent device is never mistaken for a calm patient." |

After step 8, press `r` again (the node restarts on the rest replay anyway) and leave the hand resting.

### If asked
- **"Are the vitals real?"** Yes, but replayed. They are real ICU recordings from the BIDMC dataset (PhysioNet): rest = record 39, abnormal = record 52. The bed's own MAX30100 sensor saturates, so it isn't used for the demo.
- **"What if vitals are abnormal but there is no gesture?"** In this system the alert levels are triggered by the patient's gesture. A vitals-only alarm is the bedside monitor's job.

---

## Fallbacks

Decide quickly. Each fallback keeps all 8 steps.

**1. The model misbehaves (wrong level, or `MODEL NOT FOUND`) → fixed rule.**
```
ssh icu-pi 'cd ~/icu-fusion && node/tools/stop_node.sh; node/tools/run_demo.sh --node bed1 --camera picam --fusion rule'
```
The rule is: critical if gesture ≥ 0.8 and ΔHR ≥ 15; urgent if gesture ≥ 0.8. The abnormal replay has ΔHR +40, so steps 4 and 6 still give urgent and critical. The dashboard may show the "Rule fallback" badge. Say so.

**2. The Pi or its camera fails → the laptop is `bed1` with the webcam.**
```
ssh icu-pi '~/icu-fusion/node/tools/stop_node.sh'      # only one bed1 at a time
node/tools/run_demo.sh --node bed1                     # on the laptop
```
This opens a terminal titled "ICU node" running `--vision camera --bio replay:rest --fusion model --mock-io --no-oled`; type the keys there. If the webcam is missing (`/dev/video0` absent), press the laptop's camera key. For step 8 run `node/tools/kill_node.sh` on the laptop, and restart with `node/tools/run_demo.sh --node bed1`. Add `--fusion rule` if Fallback 1 also applies.

**3. No camera works → the fake node is `bed1`.**
```
.venv/bin/python sim/fake_node.py --node bed1
```
Keys (+ Enter): `1` routine, `2` urgent, `3` critical, `r` toggles the bio source between live and replay, `k` hard kill (Last Will → Offline), `q` clean quit. Steps 3 and 4 become `1` and `2`, step 6 becomes `3`, and step 8 becomes `k`. Say clearly that this bed is simulated.

**Broker or server problems:** `./stop_all.sh` → `./scripts/reset_demo.sh` → `./start_all.sh`, then restart the nodes. The live tiles keep working while Flask is down; only History and Statistics show "unavailable".
