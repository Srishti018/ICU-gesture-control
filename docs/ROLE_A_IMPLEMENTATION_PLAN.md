# Role A Implementation Plan — Raspberry Pi Node and Vision

**Project:** ICU Gesture + Biosignal Fusion System (CBIT, IIoT course project, Team 1)
**Scope of this plan:** Role A only. Setting up the Raspberry Pi 3 Model B+, the camera, the MediaPipe vision features (`gesture_conf`, `tremor`), the node program that publishes to the laptop broker, the OLED, the buzzer, and the demo controls.
**Written:** Thu 22 Oct 2026. **Feature freeze:** Fri 23 Oct, night. **Demo:** Sun 25 Oct 2026.
**Companion plans:** Role B (sensor + ML) works in `node/bio/` and `ml/`. Role C (broker, server, dashboard) is finished; see `docs/NODE_INTEGRATION.md` and `docs/contracts.md` in the repo.

---

## 0. Instructions for Claude Code (read first)

You are executing this plan end to end, together with a human teammate who has the hardware in front of them. Follow these rules for the whole plan.

1. **Work phase by phase, in order** (Phase 0 → Phase 9). Each phase ends with a **Gate**. Do not start the next phase until the Gate passes, unless the phase says it can run in parallel.
2. **Three kinds of step are marked in this plan:**
   - **[LAPTOP]** — you run it on this computer.
   - **[PI]** — you run it on the Raspberry Pi through SSH: `ssh icu-pi '<command>'`. Long-running programs on the Pi run inside `tmux` (see §4.4).
   - **[HUMAN]** — the teammate must do something physical (plug a cable, hold up a hand, look at a screen). Print the instruction exactly as written in the plan, in a numbered list, then **stop and wait** for them to reply. Never assume a [HUMAN] step was done. Ask for the specific confirmation the step names (for example "paste the output of `i2cdetect`").
3. **Hardware safety rules (never break these):**
   - Wiring is changed **only with the Pi powered off** (power cable unplugged). Ask the human to confirm "power is unplugged" before any wiring step, and "wiring double-checked against the table" before power goes back on.
   - Sensors and the OLED take **3.3 V from physical pin 1**. Never tell the human to use pin 2 or pin 4 (5 V) for them.
   - Never run a command that writes to the SD card's boot partition, changes overclocking, or modifies `/boot/firmware/config.txt` other than the exact lines in this plan.
4. **The MQTT contract in Appendix A is fixed.** Role C's server and dashboard are built and tested against it. Never change topic names, payload fields, types, QoS or retain flags. If something seems to need a change, STOP and ask the user.
5. **The interfaces in Appendix B are fixed** between Role A and Role B. You own the vision side and everything in `node/` except `node/bio/`. You consume Role B's `node/bio/` package and `ml/fusion_runtime.py`; never edit them. If they are missing or broken, use the stub described in §8.4 and tell the user what Role B needs to fix.
6. **Folders you may create or edit:** `node/` (except `node/bio/`), `docs/NODE_INTERFACES.md`, `docs/ROLE_A_NOTES.md`. Never edit `broker/`, `server/`, `dashboard/`, `sim/`, `tests/`, `scripts/`, `ml/`, `node/bio/`, or `docs/contracts.md`.
7. **`sudo` on the Pi:** you may run only the `sudo` commands written in this plan, exactly as written. Any other `sudo` (on the Pi or on the laptop) → stop and ask the user. Never run `sudo` on the laptop.
8. **Never print or store secrets.** The `bed1` MQTT password, the Pi login password and GitHub tokens are typed by the human directly into files on the Pi (`nano`). You never see them, echo them, or commit them.
9. **If a check fails, fix the cause, never weaken the check.** If the same failure survives 3 fix attempts, stop and report: the check, the exact error, what you tried.
10. **Commit at the end of each phase** with the message given, after `git status` shows no secrets, no `.env`, no data files and no images staged. Then `git pull --rebase` and `git push`. Teammates commit to the same repo in their own folders; if a rebase conflict touches a file outside your folders, stop and ask.
11. **Explain in plain language.** The teammate is a student. At the end of each phase, give a 3–5 line summary: what works now, what was fixed, what the Gate showed, what (if anything) the human must do next.
12. **Stop and ask the user when:** a [HUMAN] step is pending; the Pi is 32-bit; a `sudo` command not in this plan seems needed; the camera or I2C devices are not detected after the troubleshooting steps; the repo URL or Pi username is unknown; Role B's files are missing at an integration gate; anything would change the contract.

---

## 1. What Role A builds (context)

The Raspberry Pi is **`bed1`**, the "patient bed node". It:

1. Reads the camera and runs MediaPipe hand tracking.
2. Every **3 seconds** turns the frames into two vision features: `gesture_conf` (how much the hand looks like the distress gesture, an open palm held up) and `tremor` (how much the fingertip shakes).
3. Gets heart-rate features (`hr`, `hr_delta`, `spo2`) from Role B's biosignal source. **In the demo these are replayed from real recordings**; the live sensor reading is still shown on the OLED.
4. Feeds the four features into Role B's 3-class model and gets probabilities for `routine`, `urgent`, `critical`.
5. Publishes the result to the laptop's Mosquitto broker exactly as in Appendix A, with heartbeat and Last Will.
6. Shows a local summary on the OLED and beeps the buzzer when the level rises.

Role C's dashboard already shows everything the node publishes. When this plan is done, the `bed1` card on the dashboard is driven by a real hand in front of the Pi camera.

### Demo moments Role A must make work
| Demo step | What the node must do |
| --- | --- |
| Disclose replay | Publish `"bio_source": "replay"`; OLED shows the live sensor separately |
| Calm | Hand in view, no gesture → `routine` |
| Accidental movement | Scratching the face stays `routine` (low `gesture_conf` averaged over 3 s) |
| Gesture, normal vitals | Open palm held ~4 s with rest replay → `urgent` alert published once |
| Gesture + exertion replay | Press `x` on the node terminal, hold palm → `critical` alert, buzzer |
| Device failure | `kill -9` the node → broker publishes `offline` via Last Will → card goes OFFLINE |

---

## 2. Environment facts and questions to settle in Phase 0

| Item | Value |
| --- | --- |
| Pi | **Raspberry Pi 3 Model B+** (1 GB RAM, quad-core 1.4 GHz, USB 2.0 only, micro-USB power). Slow for MediaPipe: expect roughly 3–6 fps, so the vision code must stay lean (§7.6) |
| Pi OS | **Raspberry Pi OS 64-bit (Bookworm)**. `uname -m` must print `aarch64`. MediaPipe has no 32-bit build. |
| Pi Python | System `python3` (3.11 on Bookworm), venv at `~/icu-fusion/.venv` created **with `--system-site-packages`** (needed for `picamera2`, `lgpio`, `gpiozero` from apt) |
| Camera | **USB webcam preferred** (works the same on laptop and Pi through OpenCV). Pi Camera Module 3 supported through `picamera2` as an alternative. |
| Sensors on I2C bus 1 | MAX30100 at `0x57` (Role B), OLED at `0x3C` (Role A) |
| Buzzer | GPIO17 (physical pin 11) |
| Broker | Mosquitto on Role C's laptop, port 1883, user `bed1`, client ID `node-bed1` |
| Network | Same phone hotspot for the laptop and the Pi. The laptop IP changes per session. |
| Code delivery to Pi | Git: laptop pushes to GitHub; the Pi pulls with a **read-only deploy key** (§4.3) |
| Laptop (where you run) | Detect the OS in Phase 0. Linux/macOS: commands as written. Windows: use PowerShell; `ssh` and `scp` are built in; the venv Python is `.venv\Scripts\python`. |

---

## 3. Architecture

### 3.1 Where Role A sits

```
                         ┌──────────────────── Raspberry Pi 3B+ (node id: bed1) ───────────────────┐
  USB webcam ──────────▶ │ node/vision/   camera.py → MediaPipe → geometry.py → features.py        │
                         │                  (Role A)            gesture_conf, tremor per 3 s       │
  MAX30100 (I2C 0x57) ─▶ │ node/bio/      live / replay / manual sources      (Role B)            │
                         │                  hr, hr_delta, spo2 per 3 s                             │
                         │ ml/fusion_runtime.py + ml/models/model.json   (Role B)                  │
                         │                  → p{routine,urgent,critical}, level                    │
                         │ node/main.py   window scheduler · level-rise logic       (Role A)       │
                         │ node/mqtt_pub.py  status · heartbeat · online/LWT        (Role A)       │──MQTT :1883──▶ Laptop broker
                         │ node/local_io/ OLED (I2C 0x3C) · buzzer (GPIO17)         (Role A)       │                (Role C)
                         │ node/control.py  keyboard commands over SSH (in tmux)    (Role A)       │
                         └─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Threads inside `node/main.py`

| Thread | Job | Rate |
| --- | --- | --- |
| Vision capture (inside `VisionFeatureExtractor`) | Grab frame → MediaPipe → per-frame scores into a buffer | as fast as the Pi allows (target ≥ 5 fps on the 3B+) |
| Bio (inside Role B's sources) | Read the sensor / advance the replay file | sensor 100 Hz; replay 1 Hz |
| Window scheduler (main thread) | Every 3.0 s: collect vision + bio windows → model → publish → OLED/buzzer | 0.333 Hz |
| Heartbeat | Publish heartbeat | every 10 s |
| MQTT network | `client.loop_start()` | paho internal |
| Control | Read keyboard lines from stdin | on input |
| OLED | Redraw the screen | 1 Hz |

The window scheduler uses `time.monotonic()` and a fixed schedule (`next_t += 3.0`), so drift does not accumulate. If one window takes longer than 3 s, log a warning and skip to the next slot instead of bunching up.

### 3.3 One window, step by step

1. `v = vision.window()` → `{hand_present, gesture_conf, tremor, n_frames, n_hand_frames, fps}`
2. `b = model_bio.window()` → `{hr, spo2, hr_delta, finger, source, quality}` (from replay in the demo)
3. If `b["hr"]` is `None` (no valid reading): reuse the last valid bio window if it is < 10 s old; otherwise use `hr = baseline_hr`, `hr_delta = 0`, `spo2 = last valid or 97`, and log `BIO MISSING`. The model always gets four numbers.
4. `p = model.predict_proba({gesture_conf, tremor, hr_delta, spo2})` → dict summing to exactly 1.00 after rounding to 2 decimals
5. `level = argmax(p)`
6. Build the status payload (Appendix A) with `bio_source` = `"replay"` if the model's bio source is a replay, else `"live"` (manual counts as `"live"`, since a human read a real device).
7. Publish to `icu/bed1/status/routine` (QoS 0, no retain), always.
8. If `rank(level) > rank(previous_level)`: also publish the same payload to `icu/bed1/status/{level}` (QoS 1, retain). Buzzer pattern for that level.
9. `previous_level = level`. Write one row to the local run log (§9.3).

---

## 4. Repository layout and conventions

### 4.1 Files Role A creates (target)

```
icu-fusion/
├── docs/
│   ├── NODE_INTERFACES.md        # Appendix B, verbatim (Role A creates it if missing)
│   └── ROLE_A_NOTES.md           # calibration values, fps, hardware notes, decisions
└── node/
    ├── __init__.py
    ├── README.md                 # how to run the node (written in Phase 9)
    ├── requirements.txt          # common (laptop + Pi)
    ├── requirements-pi.txt       # Pi-only extras
    ├── settings.py               # config dataclass, loads ~/icu-fusion/.env
    ├── hwlock.py                 # single-user lock for camera/sensors
    ├── main.py                   # entry point: python -m node.main
    ├── payload.py                # builds contract payloads, level ranks, p rounding
    ├── mqtt_pub.py               # paho client: LWT, online, publish helpers, heartbeat
    ├── control.py                # stdin command thread
    ├── runlog.py                 # per-window CSV run log
    ├── fusion_adapter.py         # loads Role B's model, or the rule fallback
    ├── bio_stub.py               # temporary stand-in for node/bio (deleted in Phase 7)
    ├── vision/
    │   ├── __init__.py
    │   ├── camera.py             # OpenCV USB camera or picamera2, same interface
    │   ├── hands.py              # MediaPipe wrapper → 21 landmarks in pixels
    │   ├── geometry.py           # PURE functions: finger scores, upright factor, frame score, tremor
    │   ├── features.py           # VisionFeatureExtractor (Appendix B)
    │   ├── synthetic.py          # SyntheticVision for tests (keyboard-driven)
    │   └── gesture_params.json   # tuned thresholds (Phase 4)
    ├── local_io/
    │   ├── __init__.py
    │   ├── oled.py
    │   └── buzzer.py
    ├── tools/
    │   ├── pi_check.sh           # health check: OS, temp, throttling, I2C, camera, venv
    │   ├── deploy.sh             # [LAPTOP] push, then git pull on the Pi
    │   ├── set_broker.sh         # [PI] write BROKER_HOST into ~/icu-fusion/.env
    │   ├── vision_probe.py       # prints per-frame scores for calibration
    │   ├── preview.py            # MJPEG preview with landmarks on http://icu-pi.local:8080
    │   ├── fps_test.py
    │   ├── run_demo.sh           # starts the node in tmux
    │   ├── kill_node.sh          # kill -9 for the LWT demo
    │   └── oled_test.py / buzzer_test.py
    └── tests/
        ├── __init__.py
        ├── test_geometry.py
        ├── test_payload.py
        ├── test_level_logic.py
        └── verify_node_contract.py   # end-to-end against the real broker
```

`node/bio/`, `ml/` and `ml/fusion_runtime.py` belong to Role B. Read them; never edit them.

### 4.2 Files that live only on the Pi (never committed)

| Path on Pi | Contents |
| --- | --- |
| `~/icu-fusion/` | Git clone of the repo (pulled, never edited by hand) |
| `~/icu-fusion/.env` | `BROKER_HOST`, `BROKER_PORT=1883`, `NODE_ID=bed1`, `NODE_USER=bed1`, `NODE_PASS` (typed by the human) |
| `~/icu-fusion/.venv/` | Python venv |
| `~/icu-data/logs/` | Node logs and per-window run logs |
| `~/icu-data/raw/` | Role B's data collection output |

`.gitignore` already ignores `.env` and `.venv/` (Role C). Make sure it also ignores `node/models_cache/` and `*.task` if you download MediaPipe model files into the repo; prefer downloading them to `~/icu-data/models/` instead.

### 4.3 Getting code onto the Pi (one-time, Phase 1)

The Pi pulls the repo from GitHub with a **read-only deploy key**, so it never holds anyone's personal GitHub login.

- The Pi generates `~/.ssh/icu_deploy` (no passphrase).
- The **repo owner (Role C)** adds the public key in GitHub → repo → Settings → Deploy keys → Add deploy key, with **Allow write access unchecked**.
- `~/.ssh/config` on the Pi maps `github.com` to that key.
- Updating the Pi: `node/tools/deploy.sh` runs `git push` on the laptop, then `ssh icu-pi 'cd ~/icu-fusion && git pull --ff-only'`.

### 4.4 Running long programs on the Pi

Anything that runs for more than a few seconds on the Pi runs inside `tmux`, so a dropped Wi-Fi or SSH connection does not kill it (which would trigger a false OFFLINE on the dashboard).

- Start: `ssh icu-pi 'tmux new-session -d -s icu "cd ~/icu-fusion && .venv/bin/python -m node.main ... 2>&1 | tee -a ~/icu-data/logs/node.log"'`
- Watch output without attaching: `ssh icu-pi 'tmux capture-pane -pt icu | tail -40'`
- Send a key command: `ssh icu-pi 'tmux send-keys -t icu x Enter'`
- The human attaches with `ssh -t icu-pi tmux attach -t icu` and detaches with **Ctrl-b then d**.

### 4.5 Hardware lock

Only one program at a time may open the camera or I2C sensors. `node/hwlock.py` takes an exclusive `fcntl.flock` on `/tmp/icu-hw.lock` (non-blocking) and writes the program name and PID into it. If the lock is held, print `HARDWARE BUSY: <name> (pid N) is using the camera/sensors` and exit with code 3. Every program that opens the camera or I2C (`node.main`, `fps_test`, `vision_probe`, `preview`, `oled_test`, and Role B's tools) takes this lock. Role B imports the same module.

---

## 5. Phase 0 — Audit and settle the open questions

**Goal:** know exactly what exists: the teammate's MediaPipe code, the Pi's state, the hardware on the desk, and the repo. Fix nothing yet.

### 5.1 [LAPTOP] Inspect the repo
1. `git status`, `git log --oneline -15`, print the tree (excluding `.git`, `.venv`, `node_modules`).
2. Read `docs/contracts.md` and `docs/NODE_INTEGRATION.md`. Compare with Appendix A. Formatting differences are fine; any difference in topics, fields, QoS or retain → STOP and ask.
3. Check whether `docs/NODE_INTERFACES.md` exists. If it does, compare with Appendix B; any substantive difference → STOP and ask. If it doesn't, create it from Appendix B verbatim.
4. Check what is in `node/` and `ml/` already.
5. Detect the laptop OS and Python version (`python3 --version`; MediaPipe needs 3.9–3.12).

### 5.2 [HUMAN] Ask these questions, all in one message, and wait for the answers
1. "Where is the MediaPipe code your teammate started? Is it in the repo, or a file you can paste/attach? Does it run on a laptop, on the Pi, or both?"
2. "Which camera will you use: a USB webcam or the Pi Camera Module? If both are available, we will use the USB webcam."
3. "Has the Pi already been set up? If yes: what is its username, hostname and is SSH enabled? If no, do you have a microSD card (16 GB+) and an SD card reader for this laptop?"
4. "Confirm the Pi is a Raspberry Pi 3 Model B+ (printed on the board). It has 1 GB RAM."
5. "OLED: what does the board say: SSD1306 or SH1106, and is it 0.96 inch or 1.3 inch? How many pins (4 pins = I2C, which we need)?"
6. "Buzzer: does it have a sticker/label? Do you have a transistor (BC547, 2N2222 or similar) and a 1 kΩ resistor?"
7. "Do you have: the official Pi power supply (micro-USB, 5 V 2.5 A), a heatsink or fan on the Pi, a breadboard, female-to-male jumper wires?"
8. "What is the GitHub repo address (e.g. github.com/name/icu-fusion)? Is it private?"

### 5.3 Audit the teammate's MediaPipe code
If the code is available, read it and record in `docs/ROLE_A_NOTES.md`:
- Which MediaPipe API it uses (`mp.solutions.hands` or the Tasks `HandLandmarker`), which version, which camera API.
- Whether it already computes a 0–1 confidence and a tremor value, and how.
- Whether it runs headless (no `cv2.imshow` window). The Pi will usually have no monitor.
Keep any working logic: reuse its landmark handling inside `node/vision/hands.py`, but the outputs must follow Appendix B and the formulas in §7.2.

### 5.4 Write `docs/ROLE_A_NOTES.md`
Sections: Answers to 5.2 · Teammate code audit · Pi state · Decisions (camera choice, OLED driver) · Calibration (filled in Phase 4) · Performance (filled in Phase 3).

### Gate 0
All 8 answers recorded; `docs/NODE_INTERFACES.md` exists and matches Appendix B; contract matches. Commit: `node: role A audit and interface doc`.

---

## 6. Phase 1 — Pi base setup (≈ 1–1.5 h)

Skip any step the audit shows is already done correctly, but always run the checks.

### 6.1 [HUMAN] Flash the SD card (only if the Pi is not set up, or is 32-bit)
Tell the human, step by step:
1. On the laptop, install **Raspberry Pi Imager** from raspberrypi.com/software.
2. Choose Device: **Raspberry Pi 3**. Operating System: **Raspberry Pi OS (other) → Raspberry Pi OS Lite (64-bit)**. Use **Lite** (no desktop): the 3B+ has only 1 GB RAM and MediaPipe needs it. Storage: the microSD card.
3. Click Next → **Edit settings**:
   - Hostname: `icu-pi`
   - Username: `pi`, and a password the team will remember (do not type it in this chat)
   - Wireless LAN: the **phone hotspot's** name and password; country `IN`
   - Locale: time zone `Asia/Kolkata`
   - Services tab: **Enable SSH**, "Use password authentication"
4. Save → Yes → write. This erases the card.
5. Put the card in the Pi, turn on the phone hotspot, plug in the Pi's power. Wait 2 minutes.
6. Reply "Pi is booted".

### 6.2 [LAPTOP] + [HUMAN] SSH access with a key
1. [LAPTOP] `ping -c 3 icu-pi.local` (Windows: `ping -n 3 icu-pi.local`). If it fails: ask the human to check the hotspot's "connected devices" list for `icu-pi` and give you its IP; use the IP instead of `icu-pi.local` below.
2. [LAPTOP] Create a key if none: `ssh-keygen -t ed25519 -f ~/.ssh/icu_pi -N ""`.
3. [HUMAN] Run in their own terminal (it asks for the Pi password, which only they should type): `ssh-copy-id -i ~/.ssh/icu_pi.pub pi@icu-pi.local`. On Windows, instead: `type $env:USERPROFILE\.ssh\icu_pi.pub | ssh pi@icu-pi.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"`.
4. [LAPTOP] Add to `~/.ssh/config`:
   ```
   Host icu-pi
       HostName icu-pi.local
       User pi
       IdentityFile ~/.ssh/icu_pi
       ServerAliveInterval 15
   ```
5. [LAPTOP] `ssh icu-pi 'echo ok'` prints `ok` without a password prompt.

Role B needs SSH too: tell the human that Role B's teammate should repeat steps 2–4 on their own laptop.

### 6.3 [PI] Check the basics
Run and record in `ROLE_A_NOTES.md`:

| Command | Must show |
| --- | --- |
| `uname -m` | `aarch64` (if `armv7l` → STOP: reflash with 64-bit, §6.1) |
| `grep PRETTY /etc/os-release` | `bookworm` |
| `free -h` | RAM size |
| `python3 --version` | 3.11.x |
| `vcgencmd measure_temp` | below 70 °C at idle |
| `vcgencmd get_throttled` | `throttled=0x0`. Anything else means under-voltage or overheating in the past: ask the human to use the official 5 V 2.5 A micro-USB supply (phone chargers often cause under-voltage on the 3B+) and a heatsink |
| `timedatectl` | Time zone `Asia/Kolkata`, "System clock synchronized: yes" |

If the time zone is wrong: `sudo timedatectl set-timezone Asia/Kolkata`. If the clock is not synchronised, the hotspot may have no internet; the server uses its own clock for response time, so this is not fatal, but note it.

### 6.4 [PI] Enable I2C and the camera, install system packages
Run exactly:
```
sudo raspi-config nonint do_i2c 0
sudo apt-get update
sudo apt-get install -y git tmux i2c-tools python3-venv python3-dev python3-smbus python3-lgpio python3-gpiozero mosquitto-clients libgl1 libglib2.0-0
groups
```
`groups` must include `i2c`, `video` and `gpio`. If not: `sudo usermod -aG i2c,video,gpio pi`, then the human must log out and back in (or you run `sudo reboot` and wait 60 s).

Only if the **Pi Camera Module** is the chosen camera: `sudo apt-get install -y python3-picamera2 --no-install-recommends`.

### 6.5 [PI] + [HUMAN] Clone the repo with a deploy key
1. [PI] `ssh-keygen -t ed25519 -f ~/.ssh/icu_deploy -N "" -C icu-pi-deploy` then `cat ~/.ssh/icu_deploy.pub`.
2. [PI] Create `~/.ssh/config` on the Pi:
   ```
   Host github.com
       IdentityFile ~/.ssh/icu_deploy
       IdentitiesOnly yes
   ```
   and `ssh-keyscan github.com >> ~/.ssh/known_hosts`.
3. [HUMAN] Show the public key line and say: "Send this line to the repo owner (Role C). They open the repo on GitHub → Settings → Deploy keys → Add deploy key, title `icu-pi`, paste it, leave **Allow write access unchecked**, and save. Reply when done."
4. [PI] `git clone git@github.com:<owner>/<repo>.git ~/icu-fusion`.
5. [PI] `mkdir -p ~/icu-data/logs ~/icu-data/raw ~/icu-data/models`.

### 6.6 [PI] + [HUMAN] The Pi's `.env`
1. [PI] Write `~/icu-fusion/.env` with placeholders only:
   ```
   BROKER_HOST=CHANGE_ME
   BROKER_PORT=1883
   NODE_ID=bed1
   NODE_USER=bed1
   NODE_PASS=
   ```
   and `chmod 600 ~/icu-fusion/.env`.
2. [HUMAN] "Get the `bed1` password from Role C privately. Then run `ssh -t icu-pi nano ~/icu-fusion/.env`, type it after `NODE_PASS=`, save with Ctrl-O, Enter, and exit with Ctrl-X. Reply 'password set'."
3. Write `node/tools/set_broker.sh` (runs on the Pi): takes the laptop IP as its only argument, validates it looks like an IPv4 address, replaces the `BROKER_HOST=` line with `sed -i`, and prints the line. Never prints `NODE_PASS`.

### 6.7 [PI] Python environment
```
cd ~/icu-fusion
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip wheel
```
Packages are installed in Phase 2 from `node/requirements.txt`.

**3B+ memory:** with 1 GB RAM, install packages one command at a time and check `free -h` afterwards. If `pip install` or the node is killed for running out of memory (`dmesg | tail` shows `Out of memory`), raise swap: `sudo dphys-swapfile swapoff && sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile && sudo dphys-swapfile setup && sudo dphys-swapfile swapon` (allowed `sudo`).

### 6.8 `node/tools/pi_check.sh`
Write this script (committed; run on the Pi). It prints PASS/FAIL lines for: `aarch64`; Bookworm; temperature < 75 °C; throttled `0x0`; user in groups `i2c video gpio`; `/dev/i2c-1` exists; venv exists; `.env` exists and `NODE_PASS` is non-empty (check without printing it); `BROKER_HOST` is not `CHANGE_ME`; a camera device exists (`/dev/video0` for USB, or `rpicam-hello --list-cameras` lists one). It exits non-zero if any FAIL, except the camera and broker lines, which are WARN until Phases 2 and 8.

### Gate 1
`ssh icu-pi 'echo ok'` works without a password; `ssh icu-pi '~/icu-fusion/node/tools/pi_check.sh'` (after deploying it) shows PASS for all non-WARN lines. Commit: `node: pi setup scripts`.

---

## 7. Phase 2 — Camera and MediaPipe on the Pi (≈ 1–1.5 h)

### 7.1 Requirements files
`node/requirements.txt` (laptop and Pi):
```
numpy<2
opencv-python-headless>=4.8
mediapipe>=0.10.9
paho-mqtt>=2.0
python-dotenv>=1.0
smbus2>=0.4
scipy>=1.10
flask>=3.0
pytest>=8.0
```
`node/requirements-pi.txt` (Pi only): `luma.oled>=3.12`.

`smbus2` and `scipy` are listed here for Role B's `node/bio/` (Appendix B); do not remove them.

[PI] `.venv/bin/pip install -r node/requirements.txt -r node/requirements-pi.txt`. If `mediapipe` fails to install, try the two most recent 0.10.x versions explicitly and record which worked. If none install on Python 3.11 aarch64, STOP and report the pip error.

[LAPTOP] create a laptop venv (or reuse the repo `.venv`) and install `node/requirements.txt` (not the `-pi` file).

### 7.2 [HUMAN] Plug in the camera
- **USB webcam:** plug it into any USB port on the Pi (the 3B+ has four USB 2.0 ports). Reply "plugged in".
- **Pi Camera Module (only if chosen):** power off the Pi first. Lift the black/white latch of the connector marked CAMERA (between the HDMI and audio ports), insert the ribbon fully with the **blue tab facing the USB/Ethernet ports**, press the latch down. Connect the other end to the camera following the official Raspberry Pi camera guide. Power on. Reply "connected".

[PI] Check:
- USB: `v4l2-ctl --list-devices` (install with `sudo apt-get install -y v4l-utils` if missing; this `sudo` is allowed) shows the webcam with a `/dev/videoN` path. Record N.
- Pi Camera: `rpicam-hello --list-cameras` lists one camera.

### 7.3 `node/vision/camera.py`
One class `Camera(kind, index, width=640, height=480, fps=30)` with `open()`, `read() -> (ok, frame_bgr)`, `close()`:
- `kind="usb"`: `cv2.VideoCapture(index, cv2.CAP_V4L2)` on Linux (plain `cv2.VideoCapture(index)` elsewhere), set FOURCC `MJPG`, width, height, FPS; set buffer size 1 so frames are fresh.
- `kind="picam"`: `Picamera2`, `create_video_configuration(main={"size": (w, h), "format": "RGB888"})`, start; `read()` returns `capture_array()` (this format arrives in BGR order for OpenCV).
- A frame that fails to read 30 times in a row raises `CameraError` with a clear message.

### 7.4 `node/vision/hands.py`
Wrapper `HandTracker` returning, per frame, either `None` (no hand) or a `(21, 2)` NumPy array of landmark **pixel** coordinates in the inference image, plus the detection score.
- Prefer the **MediaPipe Tasks `HandLandmarker`** in `VIDEO` running mode, `num_hands=1`, `min_hand_detection_confidence=0.5`, `min_hand_presence_confidence=0.5`, `min_tracking_confidence=0.5`. Model file `hand_landmarker.task` is downloaded once to `~/icu-data/models/` (laptop: a gitignored folder) from Google's MediaPipe model storage (`https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task`).
- If the Tasks API fails on the Pi, or the teammate's working code uses `mp.solutions.hands`, use `mp.solutions.hands.Hands(static_image_mode=False, max_num_hands=1, model_complexity=0, min_detection_confidence=0.5, min_tracking_confidence=0.5)` instead. Record the choice in `ROLE_A_NOTES.md`.
- Inference image: resize the camera frame to **320×240** and convert BGR→RGB before inference. Landmark pixel coordinates are in this 320×240 space.
- Timestamps for VIDEO mode: `int(time.monotonic() * 1000)`, strictly increasing.

### 7.5 `node/tools/fps_test.py`
Takes the hardware lock, opens the camera, runs the tracker for 30 s, and prints: frames captured, frames with a hand, average fps, average inference ms, CPU temperature at the end (`vcgencmd measure_temp` on the Pi). Arguments: `--camera usb|picam --index N --seconds 30`.

### 7.6 Measure
1. [LAPTOP] run `fps_test.py` with the laptop webcam (sanity check of the code).
2. [HUMAN] "Sit in front of the Pi camera and hold your hand in view, moving it slowly, for 30 seconds after I start the test."
3. [PI] run `fps_test.py`.

| Result on the Pi | Action |
| --- | --- |
| ≥ 5 fps | Good. Continue. |
| 3–5 fps | Acceptable on the 3B+ (9–15 frames per 3-s window is enough for both features). Note it. Make sure inference is at 320×240, use `mp.solutions` with `model_complexity=0` if it is faster, and capture at 320×240 directly to save the resize. |
| < 3 fps | Check `vcgencmd get_throttled` and temperature (cooling). Close everything else on the Pi (no desktop, no `preview.py`). Try 256×192 inference. If still < 3 fps, STOP and tell the user; fallback is running vision on a laptop as `bed1`, which changes the demo story. |

Record fps, inference ms and peak temperature in `ROLE_A_NOTES.md`.

### Gate 2
Pi fps ≥ 3 (target ≥ 5) with a hand detected in > 80% of frames while the hand is in view. Commit: `node: camera and mediapipe tracker`.

---

## 8. Phase 3 — Vision features (≈ 2–3 h; develop on the laptop webcam, then confirm on the Pi)

### 8.1 Landmark indices used
MediaPipe hand landmarks: 0 wrist; thumb 1 CMC, 2 MCP, 3 IP, 4 tip; index 5 MCP, 6 PIP, 7 DIP, 8 tip; middle 9, 10, 11, 12; ring 13, 14, 15, 16; pinky 17, 18, 19, 20.

### 8.2 `node/vision/geometry.py` — exact formulas (pure functions, no MediaPipe import)

All inputs are `(21, 2)` arrays of pixel coordinates (x right, y **down**). `clamp01(v) = min(1, max(0, v))`. `ramp(v, lo, hi) = clamp01((v - lo) / (hi - lo))`. The `lo`/`hi` defaults below come from `gesture_params.json` and are tuned in Phase 4.

1. **Hand size** `s = |L[9] − L[0]|` (wrist to middle-finger MCP). If `s < 10` px, treat the frame as no hand.
2. **Finger straightness** for index, middle, ring, pinky with joints (MCP, PIP, TIP) = (5,6,8), (9,10,12), (13,14,16), (17,18,20): the angle at PIP between vectors PIP→MCP and PIP→TIP, in degrees (180 = straight). Score `f = ramp(angle, 120, 165)`.
3. **Thumb open**: `t = ramp(|L[4] − L[5]| / s, 0.35, 0.70)` (thumb tip away from the index MCP).
4. **Open-hand score** `open = 0.8 × mean(four finger scores) + 0.2 × t`.
5. **Upright factor** (fingers pointing up, palm held up): `u = (L[0].y − L[12].y) / s`; `up = ramp(u, 0.8, 1.5)`. A hand lying flat or pointing sideways gives `u ≈ 0` → `up = 0`.
6. **Frame gesture score** `g = open × up`.
7. **Tremor** over a list of frames with a hand: take fingertip `L[8]` and hand size `s` per frame; `s_med = median(s)`; `tremor = (std(x) + std(y)) / 2 / s_med`. Needs ≥ 5 hand frames; otherwise `tremor = 0.0`.

Functions: `hand_size`, `finger_angle`, `finger_scores`, `thumb_score`, `upright_factor`, `frame_gesture_score(L, params) -> (g, details_dict)`, `tremor(points_list, sizes_list)`.

### 8.3 `node/vision/features.py` — `VisionFeatureExtractor` (Appendix B)
- `start()` opens the camera and tracker, starts the capture thread. Each frame appends `(t, hand_present, g, tip_xy, s)` to a thread-safe buffer.
- `window()` takes all frames since the previous call and returns:
  - `n_frames`, `n_hand_frames`, `fps = n_frames / elapsed`
  - `hand_present = n_hand_frames / n_frames >= 0.5`
  - `gesture_conf = mean(g over all frames)`, where frames without a hand count as **0**. So holding the palm for the whole 3 s scores high; a hand passing through scores low.
  - `tremor` from §8.2 over the hand frames
  - all floats rounded to 3 decimals; if `n_frames == 0`, return zeros and `hand_present=False`
- `stop()` stops the thread and releases the camera.
- `snapshot()` returns the latest frame with landmarks drawn (for `preview.py`).

`node/vision/synthetic.py` — `SyntheticVision` with the same interface and no camera: state `gesture` on/off toggled by `set_gesture(bool)`; `window()` returns `gesture_conf` 0.85–0.95 when on, 0.00–0.10 when off; `tremor` 0.005–0.02. Used for laptop tests.

### 8.4 Tools
- `node/tools/vision_probe.py`: takes the lock, runs the tracker, prints every 0.5 s: hand yes/no, `s`, four finger angles, `t`, `u`, `open`, `up`, `g`; and every 3 s the `window()` result.
- `node/tools/preview.py`: Flask app on port 8080 serving an MJPEG stream of `snapshot()` with landmarks and the current `g` drawn on it. Lets the human position the camera from a laptop browser at `http://icu-pi.local:8080`. Takes the lock; only for setup, not during the node run.

### 8.5 Unit tests — `node/tests/test_geometry.py`
Build synthetic `(21,2)` landmark arrays by hand (helper in the test file):
- straight open palm pointing up → `g > 0.85`
- closed fist (tips folded next to MCPs) → `g < 0.15`
- open palm lying sideways (rotated 90°) → `g < 0.15`
- half-curled fingers (PIP angle ~140°) → `0.2 < g < 0.7`
- same palm scaled ×2 and shifted → same `g` within 0.01 (scale/position invariance)
- tremor: identical points → 0; points with known std → expected value within 1e-6; scaling the hand ×2 with the same relative jitter → same tremor
- fewer than 5 hand frames → tremor 0

### Gate 3
`pytest node/tests/test_geometry.py` passes on the laptop and on the Pi. `vision_probe.py` runs on the Pi. Commit: `node: vision features (gesture_conf, tremor)`.

---

## 9. Phase 4 — Camera placement and calibration (≈ 45 min, with the human)

### 9.1 [HUMAN] Place the camera
"Mount the camera about 60–90 cm from where the hand will be, at roughly hand height, looking straight at the hand. Use a plain background and light from the front (not a window behind the hand). Open `http://icu-pi.local:8080` on your laptop browser to see the camera view. Your raised open hand should fill roughly a quarter to a third of the picture height. Reply when the view looks right."

Start `preview.py` in tmux first; stop it afterwards (it holds the hardware lock).

### 9.2 [HUMAN] + [PI] Calibration poses
Run `vision_probe.py` in tmux. For each pose, tell the human to hold it **steady for 6 seconds** after you say "go", then read two consecutive `window()` lines from the tmux pane. Ask a second team member to repeat the set if available (different hand size).

| # | Pose | Target `gesture_conf` (window) |
| --- | --- | --- |
| P1 | Open palm facing the camera, fingers up, thumb out | ≥ 0.85 |
| P2 | Same, but fingers together (no gaps) | ≥ 0.75 |
| P3 | Relaxed hand resting, fingers slightly curled | ≤ 0.30 |
| P4 | Fist | ≤ 0.15 |
| P5 | Open palm lying flat / pointing sideways | ≤ 0.20 |
| P6 | Scratching the face / adjusting a blanket | ≤ 0.35 |
| P7 | Half-open palm, fingers bent ~45° | 0.30–0.70 |
| P8 | P1 in dimmer light (lights partly off) | record only |
| P9 | No hand in view | 0.00 |

### 9.3 Tuning rules
- Only the `lo`/`hi` values in `gesture_params.json` may change, each by at most ±15 (degrees) or ±0.2 (ratios) from the defaults. Change one parameter at a time, re-run the failing pose and P1.
- If P1 < 0.85: lower the finger-angle `hi` (165 → 155) or the upright `hi` (1.5 → 1.3).
- If P3/P6 > target: raise the finger-angle `lo` (120 → 130).
- If targets can't all be met within those limits after 3 rounds, keep the best setting, record the actual numbers, and continue. Role B's model learns from whatever the real values are; the rule baseline (`gesture ≥ 0.8`) depends on P1 being ≥ 0.8, so prioritise P1.
- Record the final parameters and the full P1–P9 table in `ROLE_A_NOTES.md`. These numbers go in the report.

### 9.4 Tell Role B
Write a short message for the human to send to Role B: "Vision is calibrated. Typical gesture_conf: open palm X, rest Y, scratching Z. Tremor at rest ≈ A. The vision extractor is in `node/vision/features.py` (Appendix B interface). You can start the data collector." Fill in the numbers.

### Gate 4
P1 ≥ 0.8 and P4, P5, P9 ≤ 0.2 on the Pi with the final camera placement. Commit: `node: gesture calibration`.

---

## 10. Phase 5 — Node runtime and MQTT (≈ 2–3 h; build on the laptop with Role C's broker or a local Mosquitto)

Read `docs/NODE_INTEGRATION.md` first; reuse its working Python example where it matches this section.

### 10.1 `node/settings.py`
Dataclass `Settings` loaded from the repo-root `.env` (path resolved from `__file__`), overridable by CLI:
`broker_host`, `broker_port=1883`, `node_id="bed1"`, `node_user="bed1"`, `node_pass`, `window_s=3.0`, `heartbeat_s=10`, `keepalive=5`, `camera_kind="usb"`, `camera_index=0`, `params_path=node/vision/gesture_params.json`, `model_path=ml/models/model.json`, `replay_dir=ml/replay`, `log_dir=~/icu-data/logs`, `on_pi` (True if `/proc/device-tree/model` contains "Raspberry Pi").

### 10.2 `node/payload.py`
- `LEVELS = ("routine", "urgent", "critical")`, `RANK = {"routine": 0, "urgent": 1, "critical": 2}`
- `now_ts()` → local time `YYYY-MM-DDTHH:MM:SS`
- `round_probs(p: dict) -> dict`: round each to 2 decimals; add `1.00 − sum` to the largest so the sum is exactly 1.00; keys always in the order routine, urgent, critical
- `status_payload(node, level, p, features, hr, bio_source) -> dict` with exactly the keys of Appendix A. Types: `hr`, `hr_delta`, `spo2` → `int`; `gesture_conf`, `tremor` → `float` rounded to 3 decimals; `bio_source` ∈ {`live`, `replay`}
- `heartbeat_payload(node, uptime_s)` → `{"node", "ts", "uptime_s": int}`
- `should_publish_alert(prev_level, level) -> bool` → `RANK[level] > RANK[prev_level]`; the first window's `prev_level` is `routine`

### 10.3 `node/mqtt_pub.py`
- `mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=f"node-{node_id}", clean_session=True)`
- `username_pw_set(node_user, node_pass)`
- **Before connecting:** `will_set(f"icu/{node}/online", "offline", qos=1, retain=True)`
- `reconnect_delay_set(min_delay=1, max_delay=5)`; `connect_async(host, port, keepalive=5)`; `loop_start()`
- `on_connect` (reason code success only): publish `online` to `icu/{node}/online`, QoS 1, retain. Log `MQTT connected`.
- `on_disconnect`: log `MQTT disconnected (reason)`; paho reconnects automatically.
- `publish_status(payload)`: routine topic, QoS 0, retain False
- `publish_alert(level, payload)`: `icu/{node}/status/{level}`, QoS 1, retain True
- `publish_heartbeat()` thread every 10 s
- `clean_quit()`: publish `offline` (QoS 1, retain), `wait_for_publish(timeout=3)`, `disconnect()`, `loop_stop()`
- Publishing while disconnected must not crash; paho queues QoS 1 messages and drops QoS 0.
- **Never** subscribe to anything; the node only publishes.

### 10.4 `node/fusion_adapter.py`
- `load_fusion(settings, mode)`: `mode="model"` → `from ml.fusion_runtime import FusionModel; FusionModel.load(model_path)`. `mode="rule"` → `RuleFusion`.
- `RuleFusion.predict_proba(f)`: `critical` if `gesture_conf ≥ 0.8 and hr_delta ≥ 15`; else `urgent` if `gesture_conf ≥ 0.8`; else `routine`. Returns probability 0.90 on that level and 0.05 on the other two (so the dashboard bars still render; clearly labelled as the rule in logs). This rule is identical to Role B's baseline (Appendix B §B.4).
- If `mode="model"` and the file or module is missing: log `MODEL NOT FOUND, using rule fallback` and fall back to `RuleFusion`. The OLED shows `RULE` in that case.

### 10.5 `node/bio_stub.py` (temporary)
Until Role B's `node/bio/` is in the repo, `make_bio_source` from this stub implements Appendix B with: `replay:rest` → hr 72–76, hr_delta 0–3, spo2 97–98; `replay:exertion` → hr 98–108, hr_delta 24–34, spo2 96–98; `live` → raises `BioUnavailable`. `source` field = `"replay"`. `main.py` imports `node.bio` if it exists, else this stub, and logs which one it used. Delete this file in Phase 7 once Role B's package works.

### 10.6 `node/control.py`
Thread reading stdin lines (works with keyboard in tmux and with `tmux send-keys`):

| Key | Effect |
| --- | --- |
| `r` | Model bio source = replay **rest** file (restart from its beginning) |
| `x` | Model bio source = replay **exertion** file (restart from its beginning) |
| `l` | Model bio source = live sensor (only if live is available and the baseline is done; otherwise print why not) |
| `g` | Synthetic vision only: toggle the gesture on/off |
| `s` | Print one status line: MQTT state, fps, last features, level, bio mode |
| `q` | Clean quit (publishes `offline`, exit code 0) |
| `h` or unknown | Print this help |

EOF on stdin: keep running.

### 10.7 `node/runlog.py`
Appends one CSV row per window to `~/icu-data/logs/run_YYYYMMDD.csv`: `ts, level, p_routine, p_urgent, p_critical, gesture_conf, tremor, hr, hr_delta, spo2, bio_mode, bio_source, hand_present, n_frames, fps, fusion_mode, alert_published`. Useful for the report and debugging. No images are ever saved.

### 10.8 `node/main.py`
CLI:
```
python -m node.main [--node bed1] [--vision camera|synthetic] [--camera usb|picam] [--camera-index N]
                    [--bio replay:rest|replay:exertion|live] [--display-bio live|none]
                    [--fusion model|rule] [--no-oled] [--no-buzzer] [--broker HOST]
```
Defaults: `--vision camera`, `--bio replay:rest`, `--display-bio live` on the Pi (none elsewhere), `--fusion model`, OLED and buzzer on only when `on_pi`.

Startup order: take the hardware lock (camera mode only) → load settings (fail clearly if `NODE_PASS` is empty or `BROKER_HOST` is `CHANGE_ME`) → start MQTT → start vision → start model bio source → start display bio source (live sensor for the OLED; if it fails, log and continue without it) → start OLED/buzzer (failures are logged, never fatal) → start control and heartbeat threads → window loop (§3.3).

Shutdown on `q` or SIGTERM: clean quit. On SIGKILL nothing runs, which is the point of the Last Will demo.

Log lines (stdout and `~/icu-data/logs/node.log`), one per window, short: `10:02:11 routine p=.90/.07/.03 g=0.04 tr=0.011 hr=74 Δ2 spo2=98 [replay:rest] 9.1fps`.

### 10.9 Unit tests
- `test_payload.py`: payload keys and types exactly as Appendix A; `ts` format; `round_probs` sums to exactly 1.00 for 1,000 random inputs; heartbeat payload.
- `test_level_logic.py`: sequences of levels → which windows publish alerts. `routine, urgent, urgent, critical, critical, routine, critical` → alerts at positions 1 (urgent), 3 (critical), 6 (critical). First window `critical` → alert.
- A test with a fake MQTT client object checking that `will_set` is called before `connect_async`, and that `online` is published retained with QoS 1 on connect.

### 10.10 End-to-end contract check — `node/tests/verify_node_contract.py`
Runs on the laptop against a real broker. Credentials: `bed1` from the node `.env` for the node, and a **subscriber** login the human provides through environment variables (`CHECK_USER`, `CHECK_PASS`; Role C's `logger` or `dashboard` user). It starts `python -m node.main --vision synthetic --bio replay:rest --fusion rule --no-oled --no-buzzer` as a subprocess with stdin piped, subscribes to `icu/bed1/#`, and checks:

| ID | Check |
| --- | --- |
| C1 | `icu/bed1/online` = `online`, retained, within 10 s |
| C2 | 3–4 routine messages in 10 s, QoS 0, not retained; payload matches Appendix A types |
| C3 | heartbeat within 12 s with `node`, `ts`, `uptime_s` |
| C4 | send `g` (gesture on) → exactly one `status/urgent`, QoS 1, retained; none in the next 7 s |
| C5 | send `x` (exertion replay) → exactly one `status/critical` within 9 s, `hr_delta ≥ 15` |
| C6 | a new subscriber receives the critical message with retain = True |
| C7 | send `g` (off), wait 4 s, `r`, then `g` and `x` again → a new critical alert (rise again) |
| C8 | `p` sums to 1.00 ± 0.01 in every status message |
| C9 | kill the subprocess with SIGKILL → `online` = `offline` within 10 s |
| C10 | restart, send `q` → `offline`, exit code 0 |

Cleanup in `finally`: kill the subprocess; publish empty retained messages to `icu/bed1/status/urgent`, `icu/bed1/status/critical` and `icu/bed1/online` (as the check user).

**Important:** the Pi node and Role C's fake node must not run as `bed1` while this test runs (same client ID → they kick each other off). Ask the human to confirm nothing else is running as `bed1`.

### Gate 5
Unit tests pass. `verify_node_contract.py` → C1–C10 PASS against Role C's broker (ask the human to run `./start_all.sh` on Role C's laptop and give you the IP, or use a local Mosquitto with the same users). Commit: `node: runtime, mqtt publisher, contract tests`.

---

## 11. Phase 6 — OLED and buzzer (≈ 1 h, can run in parallel with Phase 5)

### 11.1 [HUMAN] Wiring (Pi powered OFF)
Show Appendix C and this checklist. Ask for each confirmation in turn.

1. "Unplug the Pi's power cable. Reply 'power off'."
2. OLED (4 pins: GND, VCC, SCL, SDA — read the labels on the OLED, the order varies between boards):
   - OLED **VCC → breadboard + rail**, which is fed from **Pi pin 1 (3.3 V)**
   - OLED **GND → breadboard − rail**, fed from **Pi pin 6 (GND)**
   - OLED **SDA → the breadboard SDA row**, fed from **Pi pin 3**
   - OLED **SCL → the breadboard SCL row**, fed from **Pi pin 5**
   (Role B's MAX30100 shares the same rails and SDA/SCL rows. If Role B has already wired it, add the OLED to the same rows.)
3. Buzzer, **with a transistor** (preferred):
   - Pi **pin 11 (GPIO17) → 1 kΩ resistor → transistor base**. Pin order with the flat face towards you and legs down, left to right: **BC547 = C, B, E**; **PN2222A / 2N2222 (plastic) = E, B, C**. If the part number is different, look up its datasheet before wiring.
   - transistor **emitter → − rail**
   - transistor **collector → buzzer −** (short leg)
   - buzzer **+** (long leg, or the `+` mark) → **Pi pin 2 (5 V)** — this is the only thing that uses 5 V
4. Buzzer **without a transistor:** only if the buzzer is marked 3 V/3.3 V: buzzer **+** → pin 11 (GPIO17), buzzer **−** → pin 9 (GND). If it is a 5 V buzzer and there is no transistor, **skip the buzzer** (it is on the cut list).
5. "Check every wire against Appendix C. Pin 1 is the pin nearest the SD card slot corner, on the inner row (square pad). Reply 'checked'. Then plug the power back in and reply 'powered on'."

### 11.2 [PI] I2C check
`i2cdetect -y 1` must show `3c` (OLED; `3d` on some boards). With Role B's sensor attached it also shows `57`. If `3c` is missing: ask the human to re-seat the SDA/SCL wires and check VCC is on pin 1; re-run once; if still missing, OLED goes on the cut list, continue.

### 11.3 `node/local_io/oled.py`
- `luma.oled`: `i2c(port=1, address=0x3C)`, device `ssd1306(serial, width=128, height=64)`. If the board is SH1106 (from the Phase 0 answer, or the picture is shifted/garbled), use `sh1106`.
- `Oled.show(lines: list[str], invert_line: int | None)` — up to 5 lines; default font.
- Screen layout, refreshed at 1 Hz from `main.py`:
  ```
  bed1  MQTT OK              (or "MQTT --")
  Sensor HR 74 SpO2 98       (live MAX30100; "Sensor: no finger" / "Sensor: n/a")
  Model bio: REPLAY rest     (or "REPLAY exertion" / "LIVE")
  Gesture 0.91 Tr 0.012
  LEVEL: CRITICAL            (inverted when urgent or critical)
  ```
- Any I2C error is caught and logged once per minute; the node keeps running.

### 11.4 `node/local_io/buzzer.py`
- `gpiozero.Buzzer(17)` (active buzzer). If Phase 0 says passive buzzer, use `gpiozero.TonalBuzzer(17)` with a 2 kHz tone.
- Patterns run in a background thread: **urgent** = 2 × 150 ms beeps; **critical** = 3 × 400 ms beeps. Played once per alert publish, never continuously.
- `--no-buzzer` or any GPIO error → buzzer disabled, logged.

### 11.5 Tests on hardware
- `node/tools/oled_test.py` writes "ICU node OLED OK" and the time. [HUMAN] "Do you see the text on the OLED? Reply yes/no."
- `node/tools/buzzer_test.py` plays the urgent then the critical pattern. [HUMAN] "Did you hear 2 short beeps then 3 long beeps?"

### Gate 6
Both confirmed by the human, or the failing part is recorded in `ROLE_A_NOTES.md` as cut, with the reason. Commit: `node: oled and buzzer`.

---

## 12. Phase 7 — Integrate Role B's biosignals and model (Friday)

**Dependency gate:** Role B has pushed `node/bio/` (Appendix B), `ml/fusion_runtime.py`, `ml/models/model.json`, `ml/replay/rest.csv`+`.json` and `ml/replay/exertion.csv`+`.json`. Check with `git pull` and `ls`. If anything is missing, tell the user exactly which files and keep using the stub/rule; do not write them yourself.

Steps:
1. [LAPTOP] Run Role B's parity test if present (`pytest ml/tests -q`), so you know the runtime works.
2. [LAPTOP] `python -m node.main --vision synthetic --bio replay:rest --fusion model --no-oled --no-buzzer --broker <ip>`; toggle `g` and `x`; confirm the levels move routine → urgent → critical as expected. If the model never reaches `critical` with synthetic gesture + exertion replay, STOP and tell the user (Role B's model or replay files need checking).
3. Delete `node/bio_stub.py` and the stub import branch; `main.py` now requires `node.bio`.
4. [LAPTOP] Re-run `verify_node_contract.py` with `--fusion model` added to the node command; C1–C10 must still pass.
5. Deploy to the Pi (`node/tools/deploy.sh`). Start the node in tmux on the Pi with the real camera, the model and `--bio replay:rest`, and [HUMAN] do the five demo moves from §1 while you read the tmux pane. Expected per move:

| Human does | Expected node output |
| --- | --- |
| Hand resting in view, rest replay | `routine`, g < 0.3 |
| Scratch face for 6 s | stays `routine` |
| Open palm held 6 s | `urgent`, one `ALERT urgent published` line, 2 beeps |
| Press `x`, hold palm 6 s | `critical`, one alert line, 3 beeps |
| Lower hand, press `r`, wait 6 s | back to `routine`, no alert |

6. Live sensor on the OLED: with `--display-bio live`, [HUMAN] "Rest a finger lightly on the MAX30100 for 20 s. Does the OLED show a heart rate?" Record the answer. If Role B's live source does not work, run with `--display-bio none` and note it; the demo still works with replay.

### Gate 7
All five moves behave as expected on the Pi with the real camera, the real model and replay files. Commit: `node: integrate role B bio and model`.

---

## 13. Phase 8 — Demo tooling and full run with Role C's laptop

### 13.1 Scripts
- `node/tools/deploy.sh` [LAPTOP]: `git push`, then `ssh icu-pi 'cd ~/icu-fusion && git pull --ff-only && .venv/bin/pip install -q -r node/requirements.txt -r node/requirements-pi.txt'`.
- `node/tools/run_demo.sh` [PI]: refuses if a tmux session `icu` exists; runs `pi_check.sh`; then starts `python -m node.main --bio replay:rest --fusion model` in tmux session `icu`, logging to `~/icu-data/logs/node.log`; prints how to attach and the key list.
- `node/tools/kill_node.sh` [PI]: `pkill -9 -f "python -m node.main"`; prints "node killed with SIGKILL; the dashboard should show OFFLINE within ~10 s".
- `node/tools/stop_node.sh` [PI]: `tmux send-keys -t icu q Enter`, waits 3 s, kills the tmux session.

### 13.2 [HUMAN] Full run over the hotspot
1. "Connect Role C's laptop and the Pi to the same phone hotspot. On Role C's laptop run `./stop_all.sh`, then follow its demo reset steps, then `./start_all.sh`. Tell me the laptop IP it prints."
2. [PI] `~/icu-fusion/node/tools/set_broker.sh <IP>`; test: `mosquitto_pub -h <IP> -p 1883 -u bed1 -P "$(grep ^NODE_PASS ~/icu-fusion/.env | cut -d= -f2-)" -t icu/bed1/heartbeat -m test` (the password is read from the file, never printed). If it times out: the laptop's firewall or a different network — ask the human to check both devices are on the same hotspot and that Role C ran `ufw allow 1883/tcp` if ufw is active.
3. [PI] `~/icu-fusion/node/tools/run_demo.sh`.
4. [HUMAN] "Open the dashboard on Role C's laptop. Do you see a `bed1` card that says Online, with the REPLAY badge?"
5. Walk through the full demo script (§1 table) with the human, including Acknowledge on the dashboard and `kill_node.sh` at the end. After the kill, restart with `run_demo.sh` and confirm the card comes back Online.
6. Record times: alert to dashboard (should feel instant), kill to OFFLINE (should be ≤ 10 s).

### Gate 8
The full demo works end to end twice in a row. Commit: `node: demo scripts`.

---

## 14. Phase 9 — Documentation and final check

1. `node/README.md`: what the node does (5 lines + §3.1 diagram); Pi setup summary; wiring (Appendix C); how to deploy; how to run (`run_demo.sh`), keys, kill/stop; troubleshooting table:

| Symptom | Fix |
| --- | --- |
| `HARDWARE BUSY` | Another tool holds the camera/sensors: `cat /tmp/icu-hw.lock`, stop it |
| Card never appears | Wrong `BROKER_HOST` (run `set_broker.sh`), different network, laptop firewall |
| Card flickers Online/Offline | Something else connects as `bed1` (fake node or a test) |
| Low fps / laggy | Check `vcgencmd get_throttled`, temperature, power supply |
| OLED blank | `i2cdetect -y 1` for `3c`; try `sh1106` driver |
| Always routine | Camera placement; check `vision_probe.py` P1 value |

2. `docs/ROLE_A_NOTES.md` complete: calibration table, fps, temperatures, decisions, what was cut and why.
3. Report material (put in `docs/ROLE_A_NOTES.md` under "For the report"): gesture definition and formulas (§8.2), calibration results, fps on the Pi, the one-sentence honest statement that biosignals were replayed in the demo while gesture detection was live.
4. Run everything once more: `pytest node/tests -q` on the laptop and on the Pi; `verify_node_contract.py` on the laptop; `pi_check.sh` on the Pi.

### Gate 9
All tests pass; docs written; git clean and pushed. Commit: `node: docs and final verification`.

Final message to the user: results table; anything cut; the demo-day checklist (§15); what Role C and Role B still need from them.

---

## 15. Demo-day checklist (Role A)

1. Charge the phone; turn on the hotspot. Pi with official power supply and cooling.
2. Role C: stop, reset, `./start_all.sh`; note the IP.
3. `ssh icu-pi`, `~/icu-fusion/node/tools/set_broker.sh <IP>`, `mosquitto_pub` test.
4. Camera placed and checked with `preview.py` (then stopped).
5. `run_demo.sh`; confirm `bed1` Online with REPLAY badge on the dashboard.
6. Make sure no fake node runs as `bed1` (Role C's fake node runs as `bed2`).
7. Keep a terminal attached to tmux for the `x` / `r` keys, and one for `kill_node.sh`.
8. If anything fails on stage: `stop_node.sh`, `run_demo.sh --fusion rule` as a fallback; if the Pi itself fails, Role C's fake node can run as `bed1` on the laptop.

## 16. Schedule (Role A)

| When | Phases | Done when |
| --- | --- | --- |
| Thu 22 Oct, morning | 0, 1 | Pi reachable by SSH, repo cloned |
| Thu 22 Oct, afternoon | 2, 3 | Vision features working on the Pi |
| Thu 22 Oct, evening | 4, start 5 | Calibrated; Role B can start collecting data |
| Fri 23 Oct, morning | Data collection with Role B (their plan), 5, 6 | Node publishes to Role C's broker; OLED/buzzer |
| Fri 23 Oct, afternoon | 7, 8 | Real model + replay; full demo run. **Freeze at night** |
| Sat 24 Oct | 9, rehearsals | Docs; two full rehearsals |

Cut order if behind: buzzer → OLED → live sensor on the OLED → `preview.py`. Never cut: Last Will, `bio_source: "replay"`, the level-rise rule.

---

## Appendix A — MQTT contract v1 (fixed; same as `docs/contracts.md`)

### Broker
- Mosquitto 2.x on Role C's laptop. Anonymous access disabled. Port 1883 MQTT (nodes, server), port 9001 WebSockets (browser only).
- Users: `bed1`, `bed2` (nodes), `logger` (server), `dashboard` (browser). The Pi uses `bed1`, client ID `node-bed1`.
- Timestamps: ISO 8601 local time, seconds precision, no time zone, e.g. `2026-10-25T10:02:11`.

### Topics
| Topic | Publisher | QoS | Retain | When |
| --- | --- | --- | --- | --- |
| `icu/{node}/status/routine` | node | 0 | no | every 3 s window |
| `icu/{node}/status/urgent` | node | 1 | yes | when the level rises to urgent |
| `icu/{node}/status/critical` | node | 1 | yes | when the level rises to critical |
| `icu/{node}/heartbeat` | node | 0 | no | every 10 s |
| `icu/{node}/online` | node / broker (LWT) | 1 | yes | `online` on connect; the broker sends `offline` via the Last Will |
| `icu/{node}/ack` | dashboard | 1 | no | nurse presses Acknowledge (the node does not subscribe) |

### Status payload (same shape on routine, urgent, critical)
```json
{"node": "bed1", "ts": "2026-10-25T10:02:11", "level": "critical",
 "p": {"routine": 0.04, "urgent": 0.11, "critical": 0.85},
 "features": {"gesture_conf": 0.91, "tremor": 0.010, "hr_delta": 24, "spo2": 98},
 "hr": 99, "bio_source": "replay"}
```
Heartbeat: `{"node": "bed1", "ts": "2026-10-25T10:02:11", "uptime_s": 312}`. Online: plain text `online` / `offline`.

### Rules for the node
1. Keepalive 5 s; Last Will `icu/{node}/online` = `offline`, QoS 1, retain, set before connecting.
2. On connect, publish `online` (QoS 1, retain).
3. Publish urgent/critical only when the level rises compared with the previous window. Staying at the same level does not republish.
4. Routine messages carry the live values every window, whatever the level.
5. After a nurse acknowledges, the server clears the retained alerts; the node does nothing.
6. Empty payloads are clears; the node never publishes empty payloads.
7. `bio_source` is `live` or `replay`; the dashboard shows a REPLAY badge for `replay`.
8. Never run two clients as `bed1` at once.

---

## Appendix B — Node interfaces between Role A and Role B (fixed; copy into `docs/NODE_INTERFACES.md`)

### B.1 Ownership
| Path | Owner |
| --- | --- |
| `node/` (except `node/bio/`), `docs/ROLE_A_NOTES.md` | Role A |
| `node/bio/`, `ml/` (including `ml/fusion_runtime.py`, `ml/models/`, `ml/replay/`, `ml/collect/`), `docs/ROLE_B_NOTES.md`, `docs/ML_RESULTS.md` | Role B |
| `node/requirements*.txt`, `node/hwlock.py` | Role A (Role B asks for additions) |

### B.2 Vision (Role A provides) — `node/vision/features.py`
```python
class VisionFeatureExtractor:
    def __init__(self, settings) -> None: ...
    def start(self) -> None: ...          # opens the camera, starts the capture thread
    def window(self) -> dict: ...         # features over all frames since the previous call
    def stop(self) -> None: ...
# window() returns:
# {"hand_present": bool, "gesture_conf": float 0..1 (3 dp), "tremor": float >= 0 (3 dp),
#  "n_frames": int, "n_hand_frames": int, "fps": float}
```
`node.settings.Settings.load()` returns default settings that work for this class.

### B.3 Biosignals (Role B provides) — package `node/bio/`
```python
# node/bio/__init__.py
def make_bio_source(mode: str, settings) -> "BioSource": ...
#   mode: "live" | "replay:rest" | "replay:exertion" | "manual"
class BioUnavailable(Exception): ...      # raised by make_bio_source/start() if the mode can't run

class BioSource:
    kind: str                             # "live" | "replay" | "manual"
    def start(self) -> None: ...
    def window(self) -> dict: ...         # values over the last ~3 s
    def baseline_hr(self) -> int | None: ...
    def stop(self) -> None: ...
# window() returns:
# {"hr": int | None, "spo2": int | None, "hr_delta": int | None,
#  "finger": bool, "source": "live" | "replay" | "manual", "quality": float 0..1}
```
- `live`: reads the MAX30100 (I2C bus 1, `0x57`) through `smbus2`; takes the hardware lock only when run standalone (inside `node.main` the node already holds it); `calibrate_baseline(seconds=60)` sets the baseline. `hr_delta = hr − baseline`.
- `replay:*`: plays `ml/replay/{rest|exertion}.csv` (columns `t_s,hr,spo2`, 1 row per second) in real time, looping; `hr_delta = hr − baseline_hr` from the matching `.json`; restarting the source restarts the file from row 0.
- `manual`: values typed by the operator (used only by the data collector).
- Values are `None` when there is no valid reading (no finger, poor signal).

### B.4 Fusion model (Role B provides) — `ml/fusion_runtime.py` + `ml/models/model.json`
```python
class FusionModel:
    FEATURES = ["gesture_conf", "tremor", "hr_delta", "spo2"]   # fixed order
    CLASSES  = ["routine", "urgent", "critical"]
    @classmethod
    def load(cls, path) -> "FusionModel": ...
    def predict_proba(self, features: dict) -> dict: ...  # {"routine": p, "urgent": p, "critical": p}, sums to 1
```
- NumPy only (no scikit-learn needed on the Pi): `z = (x − mean) / scale`, `logits = W·z + b`, softmax.
- `model.json`: `{"version", "trained_at", "features", "classes", "mean", "scale", "coef" (3×4, rows in "classes" order), "intercept" (3), "n_train", "sklearn_version"}`.
- **Rule baseline** (fixed before data collection, used by both roles): `critical` if `gesture_conf ≥ 0.8 and hr_delta ≥ 15`; `urgent` if `gesture_conf ≥ 0.8`; else `routine`.

### B.5 Hardware lock
`node/hwlock.py`: `with HardwareLock("name"):` takes an exclusive non-blocking `flock` on `/tmp/icu-hw.lock`; raises `HardwareBusy` with the holder's name and PID. Every program that opens the camera or I2C devices uses it.

---

## Appendix C — Wiring and pin map (Raspberry Pi 3 Model B+, 40-pin header; same layout as every 40-pin Pi)

Hold the Pi with the USB/Ethernet ports facing down, the 40-pin header on the right. **Pin 1** is the top-left pin of the header (square solder pad), nearest the corner with the SD card slot on the underside; odd pins are the inner (left) column, even pins the outer (right) column.

| Physical pin | Name | Used for |
| --- | --- | --- |
| 1 | 3.3 V | Breadboard **+ rail** → MAX30100 VIN, OLED VCC |
| 2 | 5 V | Buzzer + (only with the transistor circuit) |
| 3 | GPIO2 / SDA | Breadboard **SDA row** → MAX30100 SDA, OLED SDA |
| 5 | GPIO3 / SCL | Breadboard **SCL row** → MAX30100 SCL, OLED SCL |
| 6 | GND | Breadboard **− rail** → MAX30100 GND, OLED GND, transistor emitter |
| 9 | GND | Buzzer − (only without the transistor) |
| 11 | GPIO17 | Buzzer control (via 1 kΩ to the transistor base, or directly for a 3.3 V buzzer) |

MAX30100 board pins `INT`, `IRD`, `RD` stay **unconnected**. Expected `i2cdetect -y 1` with everything attached: `3c` (OLED) and `57` (MAX30100).

Rules: wire only with the power unplugged; never connect 5 V (pins 2, 4) to the sensor or OLED; keep wires short; rest the sensor finger lightly (pressing hard stops blood flow and ruins the reading).