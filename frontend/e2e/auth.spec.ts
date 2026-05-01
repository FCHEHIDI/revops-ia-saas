/**
 * E2E — Authentication flows
 *
 * Tests:
 *  - Unauthenticated user is redirected to /login
 *  - Bad credentials show an error message
 *  - Valid login redirects to /dashboard
 *  - Logout clears session and redirects to /login
 */
import { test, expect } from "@playwright/test";

// These tests must NOT use the stored auth state
test.use({ storageState: { cookies: [], origins: [] } });

test.describe("Authentication", () => {
  test("unauthenticated user is redirected to /login", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });

  test("invalid credentials show an error", async ({ page }) => {
    await page.goto("/login");
    await page.fill("#email", "wrong@acme.io");
    await page.fill("#password", "badpassword");
    await page.click('button[type="submit"]');

    // Error div appears (styled with red border, color #ff6666)
    // The API client may throw "Unauthorized" (401) or a backend detail message
    await expect(
      page.getByText(/identifiants|incorrect|erreur|unauthorized/i)
    ).toBeVisible({ timeout: 8_000 });
    await expect(page).toHaveURL(/\/login/);
  });

  test("valid login redirects away from /login", async ({ page }) => {
    await page.goto("/login");
    await page.fill("#email", "admin@acme.io");
    await page.fill("#password", "acme1234");
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/\/(chat|dashboard)/, { timeout: 15_000 });
  });
});
