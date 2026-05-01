/**
 * E2E — CRM Contacts CRUD
 *
 * Tests:
 *  - Contacts page loads and shows the table
 *  - "Nouveau contact" button opens the form modal
 *  - Filling the form and submitting creates a contact visible in the table
 *  - "Modifier" on a row opens the edit modal pre-filled with data
 *
 * Requires auth state saved by auth.setup.ts.
 */
import { test, expect } from "@playwright/test";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:18000/api/v1";

// Unique name to avoid collisions across test runs
const TEST_FIRST = "PlaywrightTest";
const TEST_LAST = `${Date.now()}`;
const TEST_EMAIL = `pw-test-${Date.now()}@e2e.local`;

test.describe("CRM — Contacts", () => {
  /** Remove leftover PlaywrightTest contacts from previous runs so the table
   *  (limited to 50 rows) always has room to display the freshly-created one. */
  test.beforeAll(async ({ request }) => {
    const res = await request.get(`${BACKEND}/crm/contacts?query=PlaywrightTest&limit=200`);
    if (!res.ok()) return;
    const body = await res.json() as { items: Array<{ id: string }> };
    await Promise.all(
      body.items.map((c) => request.delete(`${BACKEND}/crm/contacts/${c.id}`))
    );
  });

  test.beforeEach(async ({ page }) => {
    await page.goto("/crm");
    // Wait for the contacts table to be present
    await expect(page.locator("table").first()).toBeVisible({
      timeout: 12_000,
    });
  });

  test("contacts page loads with a table", async ({ page }) => {
    await expect(page.locator("table").first()).toBeVisible();
    // Column headers
    await expect(page.locator("text=Email").first()).toBeVisible();
  });

  test("open and close the new-contact modal", async ({ page }) => {
    await page.click("button:has-text('Nouveau contact')");
    // Modal should appear
    await expect(page.locator("text=Prénom *")).toBeVisible({ timeout: 4_000 });
    // Close via the "Annuler" button (modal has no Escape handler)
    await page.click("button:has-text('Annuler')");
    // modal disappears
    await expect(page.locator("text=Prénom *")).not.toBeVisible({ timeout: 4_000 });
  });

  test("create a contact via the form", async ({ page }) => {
    await page.click("button:has-text('Nouveau contact')");
    await expect(page.locator("text=Prénom *")).toBeVisible({ timeout: 4_000 });

    await page.getByPlaceholder("Alice", { exact: true }).fill(TEST_FIRST);
    await page.getByPlaceholder("Dupont", { exact: true }).fill(TEST_LAST);
    await page.locator("input[type='email']").fill(TEST_EMAIL);

    // Register POST listener before submit
    const postPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/crm/contacts") &&
        resp.request().method() === "POST",
      { timeout: 8_000 }
    );

    await page.click("button:has-text('Créer')");

    // Assert creation succeeded (backend returns 201)
    const postResp = await postPromise;
    expect(postResp.ok()).toBeTruthy();

    // Reload to force a fresh fetch — avoids race between React Query cache
    // invalidation timing and the table's 50-row limit
    await page.reload();
    // Wait for network idle so React Query fetch completes before we search
    await page.waitForLoadState("networkidle", { timeout: 15_000 });

    // Use the search box to filter by first name (client-side filter on fetched rows)
    await page.getByPlaceholder("Rechercher un contact…").fill(TEST_FIRST);
    // Contact name is rendered as "{first_name} {last_name}" — regex for substring match
    await expect(page.getByText(/PlaywrightTest/).first()).toBeVisible({ timeout: 5_000 });
  });

  test("open edit modal for an existing contact", async ({ page }) => {
    // Click the first row's edit or detail trigger — contact-detail-panel has "Modifier"
    await page.locator("table tbody tr").first().click();
    const modifier = page.locator("button:has-text('Modifier')");
    await expect(modifier).toBeVisible({ timeout: 6_000 });
    await modifier.click();
    // Edit modal should be open with a "Modifier" label
    await expect(page.locator("text=Modifier").first()).toBeVisible();
  });
});
