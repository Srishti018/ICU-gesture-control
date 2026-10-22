// UI smoke test: fake node bed2 -> CRITICAL card -> Acknowledge -> log shows response time.
// Run from dashboard/: npx playwright test   (broker, server and `npm run dev` must be running)
// CommonJS on purpose: this file lives outside dashboard/ (an ES module package), so
// @playwright/test is loaded explicitly from dashboard/node_modules.
const { spawn } = require("node:child_process");
const path = require("node:path");

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const { expect, test } = require(path.join(REPO_ROOT, "dashboard", "node_modules", "@playwright", "test"));

let node;

test.beforeAll(() => {
  node = spawn(path.join(REPO_ROOT, ".venv/bin/python"), ["-u", "sim/fake_node.py", "--node", "bed2"], {
    cwd: REPO_ROOT,
    stdio: ["pipe", "ignore", "ignore"],
  });
});

test.afterAll(async () => {
  if (node && node.exitCode === null) {
    node.stdin.write("q\n");
    await new Promise((resolve) => {
      const t = setTimeout(() => { node.kill(); resolve(); }, 5000);
      node.on("exit", () => { clearTimeout(t); resolve(); });
    });
  }
});

test("critical alert can be acknowledged and is logged with a response time", async ({ page }) => {
  await page.goto("/");
  const card = page.getByTestId("card-bed2");
  await expect(card).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("broker-pill")).toHaveText(/Connected/);

  node.stdin.write("3\n");
  await expect(card.locator(".level-label")).toHaveText("CRITICAL", { timeout: 10_000 });
  const ack = card.getByRole("button", { name: "Acknowledge" });
  await expect(ack).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("CRITICAL — bed2");

  await ack.click();
  await expect(card.getByRole("button", { name: /Acknowledg/ })).toHaveCount(0, { timeout: 5_000 });
  const row = page.getByTestId("alert-log").locator("tbody tr").filter({ hasText: "bed2" }).first();
  await expect(row.locator("td.response")).toHaveText(/^\d+(\.\d+)?$/, { timeout: 5_000 });

  await page.screenshot({ path: path.join(REPO_ROOT, "test-results", "dashboard.png"), fullPage: true });

  await page.reload();
  await expect(card).toBeVisible({ timeout: 10_000 });
  await page.waitForTimeout(3_000); // time for any retained alert to arrive
  await expect(card.getByRole("button", { name: /Acknowledg/ })).toHaveCount(0);
  await expect(page.getByRole("alert")).toHaveCount(0);
});
