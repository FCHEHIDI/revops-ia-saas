import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for RevOps IA E2E tests.
 *
 * Assumes the full stack is running locally:
 *   - Frontend  : http://localhost:3000
 *   - Backend   : http://localhost:18000
 *   - Orchestrator: http://localhost:8003
 *
 * Run:  npx playwright test
 * UI  : npx playwright test --ui
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false, // SSE / streaming tests need serial ordering
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1, // 1 local retry handles transient LLM rate-limits (Groq 429)
  timeout: 60_000, // LLM streaming can take up to ~40s; default 30s is too short
  workers: 1,
  reporter: [["html", { outputFolder: "playwright-report", open: "never" }]],

  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
  },

  projects: [
    // ── Auth setup — creates e2e/.auth/user.json ──────────────────────────
    {
      name: "setup",
      testMatch: "**/auth.setup.ts",
    },

    // ── Main test suite — loads auth state saved by setup ─────────────────
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: "e2e/.auth/user.json",
      },
      dependencies: ["setup"],
    },
  ],
});
