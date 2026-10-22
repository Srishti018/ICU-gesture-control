# Dashboard redesign: screenshots and review

`before/` shows the original UI and `after/` shows the redesigned nurse-station UI. Both were captured by `capture.mjs`, which runs the same scripted demo for each.

## Re-shooting

```bash
# broker running, port 5050 free (the script starts its own server on a throwaway DB)
cd dashboard && npm run dev            # in one terminal
node design/capture.mjs after          # in another
```

The script clears retained bed1/bed2 state and drives fake nodes `bed1` and `bed2` through these states: empty → all routine → one urgent → one critical → acknowledged → replay → offline (`k`, Last Will) → Flask down. It never touches `server/icu.db`. In `after` mode it also captures the light theme, the Statistics and Legend tabs, and 768 px wide shots. It fails if any state scrolls horizontally.

File names: `<nn>-<state>-<width>x<height>.png`.

## Self-review (FINISH_PLAN §6.7), after-screenshots

| Check | Result |
| --- | --- |
| 1366×768, one critical bed: bed, level and alert age are the most prominent things on screen | Yes. The red alert strip at the top shows "Bed 2 CRITICAL for 00:01". The critical tile is sorted first and has a solid red severity block with a 36 px word and "Critical for 00:01" (`04-one-critical-1366x768.png`) |
| Every state looks intentional | Yes. Covers empty, routine, urgent, critical, acknowledged, replay, offline, Flask down, light theme, and the Statistics and Legend tabs |
| Nothing relies on colour alone; AA text contrast in both themes | Every level has an icon and a word. Every token pair was checked: the lowest ratio is 4.96:1 (dark theme, surface on the critical fill). Typical text is 7–18:1 |
| No placeholder, lorem ipsum or debug output | Yes |
| 768, 1366 and 1920 px wide with no horizontal scroll | Checked automatically by `capture.mjs` in every state |
| Light theme readable on a projector | Near-black ink on white, secondary text #263445 (12.6:1), no thin grey text (`*-light-*.png`) |

## Structure

- `src/state/nodesReducer.js` is the single source of live state. It holds the MQTT messages plus a per-bed HR history (2 min), alert start times, the last acknowledgement, and the activity feed (50 events). A once-a-second `TICK` action detects a lost heartbeat.
- `src/lib/severity.js` sorts the grid (critical → urgent → offline → routine, then by bed number). `src/lib/modelOutput.js` detects rule-fallback output.
- Data behaviour hasn't changed: same subscription (`icu/+/#`), same ack payload, same Flask endpoints (`/api/health`, `/api/alerts`, `/api/stats`). The live view never depends on Flask.
- The Inter font is bundled through `@fontsource-variable/inter` and icons come from `lucide-react`, so nothing loads from the internet.
