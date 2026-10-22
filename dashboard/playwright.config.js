import { defineConfig, devices } from "@playwright/test";

// Expects broker (1883/9001), server (5050) and `npm run dev` (5173) to be running.
export default defineConfig({
  testDir: "../tests/e2e",
  timeout: 90_000,
  retries: 0,
  reporter: [["list"]],
  outputDir: "../test-results/playwright",
  use: {
    baseURL: "http://localhost:5173",
    viewport: { width: 1366, height: 768 },
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1366, height: 768 } } }],
});
