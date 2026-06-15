/**
 * Phase 0 — Scaffold E2E: health status page.
 *
 * Navigates to http://localhost:5173, waits for the backend health data to
 * render, and asserts that "Overall", "Database", and "Redis" rows all show
 * "ok" badges — proving CORS + cross-service wiring works from a real browser.
 */
import { test, expect } from "@playwright/test";

const APP_URL = process.env.APP_URL ?? "http://localhost:5173";

test("health status page renders all services ok", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  await page.goto(APP_URL);

  // Wait for the status table to appear (fetch completes, not still loading)
  await page.waitForSelector("table", { timeout: 15_000 });

  // Assert the heading
  await expect(page.getByRole("heading", { name: "SuoraFlow" })).toBeVisible();

  // Assert all three rows show "ok"
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(3);

  // Overall row
  const overallBadge = rows.nth(0).locator("td").nth(1).locator("span");
  await expect(overallBadge).toHaveText("ok");

  // Database row
  const dbBadge = rows.nth(1).locator("td").nth(1).locator("span");
  await expect(dbBadge).toHaveText("ok");

  // Redis row
  const redisBadge = rows.nth(2).locator("td").nth(1).locator("span");
  await expect(redisBadge).toHaveText("ok");

  // No CORS or other console errors
  const corsErrors = consoleErrors.filter(
    (e) => e.toLowerCase().includes("cors") || e.toLowerCase().includes("blocked")
  );
  expect(corsErrors, `CORS errors in console: ${corsErrors.join("; ")}`).toHaveLength(0);

  // Screenshot for report
  await page.screenshot({ path: "e2e/screenshots/health-ok.png", fullPage: true });
});
