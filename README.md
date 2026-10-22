# ICU Fusion

ICU Fusion is a student IoT monitoring system designed for real-time intensive care patient telemetry and status classification. Edge sensor nodes aggregate patient vitals and alert states, publishing updates over MQTT to a centralized logging server and a real-time web dashboard with acknowledgment workflows.

## How to run

### Broker
1. Ensure `.env` is created with the required passwords (see `.env.example`).
2. Generate the broker credentials:
   ```bash
   ./broker/make_passwd.sh
   ```
3. Start the Mosquitto broker:
   ```bash
   ./broker/start.sh
   ```

### Fake Node
1. Install Python dependencies:
   ```bash
   pip install -r sim/requirements.txt
   ```
2. Run the simulated node (defaults to `bed1` using credentials from `.env`):
   ```bash
   python sim/fake_node.py
   ```
   Command-line overrides are available:
   ```bash
   python sim/fake_node.py --node bed2 --user bed2 --password <password>
   ```
3. Interactive keyboard controls (type a character and press Enter):
   - `1`: Switch status level to **routine**
   - `2`: Switch status level to **urgent**
   - `3`: Switch status level to **critical**
   - `r`: Toggle `bio_source` between `live` and `replay`
   - `q`: Clean quit (publishes `"offline"` retained and disconnects cleanly)
   - `k`: Hard kill (`os._exit(1)` without disconnecting, triggering the broker's Last Will)

