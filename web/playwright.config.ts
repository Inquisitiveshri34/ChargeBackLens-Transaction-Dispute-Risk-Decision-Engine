import { defineConfig } from "@playwright/test";

// The Python that has the API's dependencies. Override with PYTHON=/path/to/python.
const PYTHON = process.env.PYTHON ?? "python";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e/.results",
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    // Uses the Chrome already installed on the machine. To use Playwright's own
    // browser instead: `npx playwright install chromium` and PW_CHANNEL=chromium.
    channel: process.env.PW_CHANNEL ?? "chrome",
  },
  // Both halves are started if they are not already running.
  webServer: [
    {
      command: `${PYTHON} -m uvicorn api.main:app --port 8000`,
      cwd: "..",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: true,
      // An empty key keeps the reviewer note on its deterministic template path.
      env: { ANTHROPIC_API_KEY: "" },
    },
    {
      command: "npm run build && npm run start",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
});
