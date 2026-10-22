// Dashboard end-to-end tests, driven by the fake node bed2.
// Run from dashboard/: npx playwright test   (broker, server and `npm run dev` must be running)
// CommonJS on purpose: this file lives outside dashboard/ (an ES module package), so
// @playwright/test is loaded explicitly from dashboard/node_modules.
const { spawn } = require("node:child_process");
const path = require("node:path");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const { expect, test } = require(path.join(REPO_ROOT, "dashboard", "node_modules", "@playwright", "test"));

const API = /:5050\/api\//;

// The tests share one fake node and run in order; the last one hard-kills it.
test.describe.configure({ mode: "serial" });

let node;
const send = (cmd) => node.stdin.write(cmd + "\n");

test.beforeAll(() => {
  node = spawn(path.join(REPO_ROOT, ".venv/bin/python"), ["-u", "sim/fake_node.py", "--node", "bed2"], {
    cwd: REPO_ROOT,
    stdio: ["pipe", "ignore", "ignore"],
  });
});

test.afterAll(async () => {
  if (node && node.exitCode === null) {
    send("q");
    await new Promise((resolve) => {
      const t = setTimeout(() => { node.kill(); resolve(); }, 5000);
      node.on("exit", () => { clearTimeout(t); resolve(); });
    });
  }
});

/** Open the dashboard and wait for a calm, connected bed2 (acknowledging any alert left over). */
async function openCalm(page) {
  send("1");
  await page.goto("/");
  const tile = page.getByTestId("bed-tile-bed2");
  await expect(tile).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("broker-status")).toContainText("Live");
  await expect(tile.getByTestId("connection-state")).toHaveText("Online", { timeout: 15_000 });
  const leftover = tile.getByTestId("ack-button");
  if (await leftover.count()) await leftover.click();
  await expect(tile.getByTestId("ack-button")).toHaveCount(0, { timeout: 10_000 });
  return tile;
}

test("theme toggle persists after reload", async ({ page }) => {
  await page.goto("/");
  const html = page.locator("html");
  const before = await html.getAttribute("data-theme");
  const after = before === "dark" ? "light" : "dark";
  await page.getByTestId("theme-toggle").click();
  await expect(html).toHaveAttribute("data-theme", after);
  await page.reload();
  await expect(html).toHaveAttribute("data-theme", after);
  await page.getByTestId("theme-toggle").click();
  await expect(html).toHaveAttribute("data-theme", before);
});

test("critical alert: alert strip, keyboard acknowledge, response time, gone after reload", async ({ page }) => {
  const tile = await openCalm(page);

  send("3");
  await expect(tile.getByTestId("tile-level")).toHaveText("CRITICAL", { timeout: 10_000 });
  await expect(tile.getByTestId("tile-alert-age")).toHaveText(/Critical for \d{2}:\d{2}/);
  const row = page.getByTestId("alert-row-bed2");
  await expect(row).toContainText("Bed 2");
  await expect(row).toContainText("CRITICAL");
  await expect(page.getByTestId("live-region")).toHaveText("Critical alert: Bed 2");
  // The critical bed is sorted first.
  await expect(page.locator("[data-testid^='bed-tile-']").first()).toHaveAttribute("data-testid", "bed-tile-bed2");

  // Keyboard: focus the tile's Acknowledge button and press Enter.
  const ack = tile.getByTestId("ack-button");
  await ack.focus();
  await page.keyboard.press("Enter");
  await expect(tile.getByTestId("ack-done")).toHaveText(/Acknowledged · response \d+\.\d s/, { timeout: 10_000 });
  await expect(page.getByTestId("alert-strip")).toHaveCount(0);
  const historyRow = page.getByTestId("history-row").filter({ hasText: "Bed 2" }).first();
  await expect(historyRow.getByTestId("history-response")).toHaveText(/^\d+\.\d s$/, { timeout: 10_000 });
  await expect(page.getByTestId("activity-feed")).toContainText(/Bed 2 · Critical alert acknowledged · response \d+\.\d s/);

  send("1");
  await page.reload();
  await expect(tile).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(3_000); // time for any retained alert to arrive
  await expect(tile.getByTestId("ack-button")).toHaveCount(0);
  await expect(page.getByTestId("alert-strip")).toHaveCount(0);
});

test("server down: history unavailable while live tiles keep updating", async ({ page }) => {
  await page.route(API, (route) => route.abort("connectionrefused"));
  const tile = await openCalm(page);
  await expect(page.getByTestId("history-unavailable")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("server-status")).toContainText("Unreachable");

  send("2");
  await expect(tile.getByTestId("tile-level")).toHaveText("URGENT", { timeout: 10_000 });
  await expect(page.getByTestId("history-unavailable")).toBeVisible();

  // Server back: acknowledge to leave a clean state.
  await page.unroute(API);
  await tile.getByTestId("ack-button").click();
  await expect(tile.getByTestId("ack-button")).toHaveCount(0, { timeout: 10_000 });
  send("1");
});

test("broker unreachable: connection banner", async ({ page }) => {
  // Hold the WebSocket open without connecting it to the broker: MQTT never connects.
  await page.routeWebSocket(/:9001/, () => {});
  await page.goto("/");
  await expect(page.getByTestId("connection-banner")).toContainText("Live data paused — reconnecting…", {
    timeout: 20_000,
  });
});

test("hard-killed node shows Offline via Last Will", async ({ page }) => {
  const tile = await openCalm(page);
  send("k");
  await expect(tile.getByTestId("connection-state")).toHaveText("Offline", { timeout: 20_000 });
  await expect(tile.getByTestId("offline-notice")).toContainText("device disconnected");
  await expect(page.getByTestId("activity-feed")).toContainText("Bed 2 · went offline");
});
