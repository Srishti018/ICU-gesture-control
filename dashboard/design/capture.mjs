// Capture the dashboard in every demo state at several screen sizes.
//
//   node design/capture.mjs before|after
//
// Needs: the broker running (1883 + 9001) and `npm run dev` on 5173.
// Port 5050 must be free: this script starts its own server on a throwaway
// database (never server/icu.db) and drives fake nodes bed1 and bed2.
// Screenshots go to dashboard/design/<before|after>/<state>-<width>x<height>.png.
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync } from "node:fs";
import { createConnection } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";
import mqtt from "mqtt";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");
const PYTHON = path.join(REPO, ".venv", "bin", "python");
const URL = "http://localhost:5173/";

const phase = process.argv[2];
if (!["before", "after"].includes(phase)) {
  console.error("usage: node design/capture.mjs before|after");
  process.exit(2);
}
const OUT = path.join(HERE, phase);
mkdirSync(OUT, { recursive: true });

const SIZES =
  phase === "before"
    ? [[1366, 768], [1920, 1080]]
    : [[1366, 768], [1920, 1080], [768, 1024]];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function readEnv(file) {
  const out = {};
  for (const line of readFileSync(file, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  return out;
}

function portOpen(port) {
  return new Promise((resolve) => {
    const s = createConnection({ port, host: "127.0.0.1" });
    s.once("connect", () => { s.end(); resolve(true); });
    s.once("error", () => resolve(false));
  });
}

async function waitPort(port, open, timeoutMs = 15000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    if ((await portOpen(port)) === open) return;
    await sleep(250);
  }
  throw new Error(`port ${port} did not become ${open ? "open" : "free"} in ${timeoutMs} ms`);
}

// --- processes ------------------------------------------------------------------
const dbDir = mkdtempSync(path.join(tmpdir(), "icu-capture-"));
let server = null;

async function startServer() {
  server = spawn(PYTHON, ["-m", "server.app"], {
    cwd: REPO,
    env: { ...process.env, DB_PATH: path.join(dbDir, "capture.db") },
    stdio: "ignore",
  });
  await waitPort(5050, true);
  await sleep(1000); // let the MQTT worker subscribe
}

async function stopServer() {
  if (!server) return;
  server.kill("SIGTERM");
  await waitPort(5050, false);
  server = null;
}

const nodes = {};
function startNode(id) {
  const proc = spawn(PYTHON, ["-u", "sim/fake_node.py", "--node", id], { cwd: REPO, stdio: ["pipe", "ignore", "ignore"] });
  nodes[id] = proc;
}
const send = (id, cmd) => nodes[id].stdin.write(cmd + "\n");

async function stopNode(id) {
  const proc = nodes[id];
  if (!proc || proc.exitCode !== null) return;
  send(id, "q");
  await new Promise((resolve) => {
    const t = setTimeout(() => { proc.kill(); resolve(); }, 5000);
    proc.on("exit", () => { clearTimeout(t); resolve(); });
  });
}

// --- MQTT helper: clear retained state and acknowledge like the dashboard ----------
const env = readEnv(path.join(REPO, ".env"));
const latestAlert = {};
const helper = mqtt.connect(`mqtt://localhost:${env.BROKER_PORT || 1883}`, {
  username: env.LOGGER_USER || "logger",
  password: env.LOGGER_PASS || "",
  clientId: "capture-" + process.pid,
});
await new Promise((resolve, reject) => {
  helper.once("connect", resolve);
  helper.once("error", reject);
});
helper.subscribe("icu/+/status/+", { qos: 1 });
helper.on("message", (topic, buf) => {
  const [, node, , level] = topic.split("/");
  if (level !== "routine" && buf.length) latestAlert[node] = JSON.parse(buf.toString());
});

async function clearRetained() {
  for (const node of ["bed1", "bed2"]) {
    for (const t of ["status/urgent", "status/critical", "online"]) {
      await helper.publishAsync(`icu/${node}/${t}`, "", { qos: 1, retain: true });
    }
  }
}

function localIso(d = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

async function ack(node) {
  const a = latestAlert[node];
  const payload = { node, level: a?.level ?? "critical", alert_ts: a?.ts ?? localIso(), ack_ts: localIso(), by: "dashboard" };
  await helper.publishAsync(`icu/${node}/ack`, JSON.stringify(payload), { qos: 1 });
}

// --- browser ----------------------------------------------------------------------
const browser = await chromium.launch();
const pages = [];
for (const [width, height] of SIZES) {
  const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: "dark" });
  pages.push({ page: await ctx.newPage(), width, height, ctx });
}

const overflow = [];

async function shoot(name, { light = false } = {}) {
  for (const { page, width, height } of pages) {
    if (light) await setTheme(page, "light");
    const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    if (wide > 0) overflow.push(`${name} at ${width}px: ${wide}px horizontal scroll`);
    const file = path.join(OUT, `${name}-${width}x${height}.png`);
    await page.screenshot({ path: file });
    if (light) await setTheme(page, "dark");
  }
  console.log("captured", name);
}

async function setTheme(page, theme) {
  // The redesign stores the theme in localStorage and exposes a toggle; the old UI has neither.
  const toggle = page.getByTestId("theme-toggle");
  if ((await toggle.count()) === 0) return;
  if ((await page.locator("html").getAttribute("data-theme")) !== theme) await toggle.click();
  await sleep(300);
}

async function reloadAll() {
  await Promise.all(pages.map(({ page }) => page.goto(URL)));
}

let failed = false;
try {
  if (await portOpen(5050)) throw new Error("port 5050 is in use; stop the server (./stop_all.sh) before capturing");
  if (!(await portOpen(5173))) throw new Error("dashboard dev server is not running on 5173 (cd dashboard && npm run dev)");

  await clearRetained();
  await startServer();
  await reloadAll();
  await sleep(3000);
  await shoot("01-empty");

  startNode("bed1");
  startNode("bed2");
  await sleep(9000);
  await shoot("02-all-routine");
  if (phase === "after") await shoot("02-all-routine-light", { light: true });

  send("bed2", "2");
  await sleep(5000);
  await shoot("03-one-urgent");
  await ack("bed2");
  send("bed2", "1");
  await sleep(3000);

  send("bed2", "3");
  await sleep(2500);
  await shoot("04-one-critical");
  if (phase === "after") await shoot("04-one-critical-light", { light: true });
  await sleep(6000);
  await ack("bed2");
  send("bed2", "1");
  await sleep(3000);
  if (phase === "after") {
    await shoot("05-acknowledged");
    for (const [tab, name] of [["stats", "09-statistics-tab"], ["about", "10-legend-tab"]]) {
      await Promise.all(pages.map(({ page }) => page.getByTestId(`tab-${tab}`).click()));
      await sleep(500);
      await shoot(name);
    }
    await Promise.all(pages.map(({ page }) => page.getByTestId("tab-activity").click()));
  }

  send("bed1", "r");
  await sleep(4000);
  await shoot("06-replay-badge");

  send("bed1", "k");
  await sleep(11000);
  await shoot("07-one-offline");

  await stopServer();
  await sleep(7000);
  await shoot("08-flask-down");
  if (phase === "after" && overflow.length) throw new Error("horizontal scroll:\n  " + overflow.join("\n  "));
  if (phase === "after") console.log("no horizontal scroll in any state or size");
} catch (err) {
  failed = true;
  console.error("capture failed:", err.message);
} finally {
  await browser.close();
  await Promise.all(Object.keys(nodes).map(stopNode));
  await stopServer().catch(() => {});
  await clearRetained().catch(() => {});
  helper.end();
}
process.exit(failed ? 1 : 0);
