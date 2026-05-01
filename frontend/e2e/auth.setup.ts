/**
 * Auth setup — runs once before all tests.
 *
 * Logs in as admin@acme.io and saves browser storage state to
 * e2e/.auth/user.json so subsequent tests skip the login flow.
 */
import { test as setup, expect } from "@playwright/test";
import path from "path";

const AUTH_FILE = path.join(__dirname, ".auth/user.json");

setup("authenticate as admin", async ({ page }) => {
  await page.goto("/login");

  await page.fill("#email", "admin@acme.io");
  await page.fill("#password", "acme1234");
  await page.click('button[type="submit"]');

  // After login the app redirects to /chat (default landing)
  await page.waitForURL(/\/(chat|dashboard)/, { timeout: 15_000 });

  await page.context().storageState({ path: AUTH_FILE });
});
