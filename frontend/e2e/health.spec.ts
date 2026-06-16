/**
 * Health + CORS regression E2E.
 *
 * Since Phase 1 the home route renders the Dashboard, with backend health
 * surfaced as a fixed pill widget (bottom-right). This spec asserts that pill
 * reaches "Backend ok" — proving the /health fetch + CORS + cross-service
 * wiring still works from a real browser.
 */
import { test, expect } from "@playwright/test";

const APP_URL = process.env.APP_URL ?? "http://localhost:5173";

test("health pill reports backend ok with no CORS errors", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  await page.goto(APP_URL);

  // App heading renders
  await expect(page.getByRole("heading", { name: "SuoraFlow" })).toBeVisible();

  // The health pill resolves from "Checking..." to "Backend ok" once /health
  // returns — this is the cross-service + CORS proof.
  await expect(page.getByText("Backend ok")).toBeVisible({ timeout: 15_000 });

  // No CORS or other console errors
  const corsErrors = consoleErrors.filter(
    (e) => e.toLowerCase().includes("cors") || e.toLowerCase().includes("blocked")
  );
  expect(corsErrors, `CORS errors in console: ${corsErrors.join("; ")}`).toHaveLength(0);

  await page.screenshot({ path: "e2e/screenshots/health-ok.png", fullPage: true });
});
