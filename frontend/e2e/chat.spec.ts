/**
 * E2E — Xenito Chat + RAG pipeline
 *
 * Tests:
 *  - Chat page renders the textarea input
 *  - Sending a generic message produces at least one streamed token
 *  - Asking about the NovaTech contract returns the 48 000 EUR figure
 *    (validates the full RAG → orchestrator → LLM pipeline)
 *
 * Requires:
 *  - Auth state (auth.setup.ts)
 *  - RAG service on :18500 with the NovaTech contract already ingested
 *  - Orchestrator on :8003
 */
import { test, expect } from "@playwright/test";

test.describe("Xenito Chat", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/chat");
    // Textarea identified by its placeholder
    await expect(
      page.locator("textarea[placeholder*='question']")
    ).toBeVisible({ timeout: 12_000 });
  });

  test("chat input is present and enabled", async ({ page }) => {
    const textarea = page.locator("textarea[placeholder*='question']");
    await expect(textarea).toBeEnabled();
  });

  test("sending a message streams a response", async ({ page }) => {
    const textarea = page.locator("textarea[placeholder*='question']");
    await textarea.fill("Bonjour");
    await textarea.press("Enter");

    // The assistant message container should appear within 25s (SSE stream).
    // MessageBubble wraps assistant content in a flex-row div; look for any
    // rounded-xl bubble that appears after the user message.
    await expect(
      page.locator(".msg-enter.flex-row .rounded-xl").first()
    ).toBeVisible({ timeout: 25_000 });
  });

  test("RAG pipeline: NovaTech contract amount is retrieved", async ({ page }) => {
    const textarea = page.locator("textarea[placeholder*='question']");
    await textarea.fill("Quel est le montant annuel du contrat NovaTech ?");
    await textarea.press("Enter");

    // Wait for streaming to finish — the "done" event hides the spinner.
    // We match the monetary amount returned by the RAG-augmented response.
    await expect(
      page.locator("text=/48.?000|48 000/").first()
    ).toBeVisible({ timeout: 35_000 });
  });
});
