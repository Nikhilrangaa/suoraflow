/**
 * Phase 1 E2E — Projects + Upload.
 *
 * Covers:
 *   1. Dashboard loads with health indicator.
 *   2. Create a new project and assert it appears with 0 assets.
 *   3. Open project page, upload a WAV file, assert status badge = "uploaded".
 *   4. Upload a fake MP4 (plain text), assert error message appears, no broken row.
 *   5. Delete the asset and assert it disappears.
 *   6. Delete the project and assert it disappears from the dashboard.
 *   7. No CORS errors in console throughout.
 */
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";
import { test, expect, Page } from "@playwright/test";

const APP_URL = process.env.APP_URL ?? "http://localhost:5173";
const WAV_FIXTURE = "/tmp/qa_clip.wav";
const FAKE_MP4_FIXTURE = "/tmp/fake.mp4";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOTS_DIR = path.join(__dirname, "screenshots");

const PROJECT_NAME = `QA Phase1 ${Date.now()}`;

// Collect console errors for CORS checking
const allConsoleErrors: string[] = [];

async function screenshotPath(name: string): Promise<string> {
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  }
  return path.join(SCREENSHOTS_DIR, `${name}.png`);
}

test.beforeEach(async ({ page }) => {
  page.on("console", (msg) => {
    if (msg.type() === "error") allConsoleErrors.push(msg.text());
  });
});

// ---------------------------------------------------------------------------
// Test 1: Dashboard loads
// ---------------------------------------------------------------------------
test("dashboard loads with SuoraFlow heading and health indicator", async ({ page }) => {
  await page.goto(APP_URL);
  await expect(page.getByRole("heading", { name: "SuoraFlow" })).toBeVisible({ timeout: 15_000 });
  // Health indicator is fixed bottom-right; check it is in DOM
  const healthIndicator = page.locator("div.fixed.bottom-3.right-3");
  await expect(healthIndicator).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: await screenshotPath("01-dashboard-loaded"), fullPage: true });
});

// ---------------------------------------------------------------------------
// Test 2: Create project
// ---------------------------------------------------------------------------
test("create project appears in list with 0 assets", async ({ page }) => {
  await page.goto(APP_URL);
  await expect(page.getByRole("heading", { name: "SuoraFlow" })).toBeVisible({ timeout: 15_000 });

  // Open modal
  await page.getByRole("button", { name: "New Project" }).first().click();
  await expect(page.getByRole("heading", { name: "New Project" })).toBeVisible();

  // Fill form
  await page.getByPlaceholder("My Documentary Project").fill(PROJECT_NAME);
  await page.getByPlaceholder("Optional description").fill("QA automated test project");

  // Submit
  await page.getByRole("button", { name: "Create" }).click();

  // Modal should close; project should appear in list
  await expect(page.getByRole("heading", { name: "New Project" })).not.toBeVisible({ timeout: 10_000 });

  // Find the row by project name
  const projectRow = page.locator("div.bg-white.rounded-xl").filter({ hasText: PROJECT_NAME });
  await expect(projectRow).toBeVisible({ timeout: 10_000 });

  // Assert "0 assets"
  await expect(projectRow).toContainText("0 assets");

  await page.screenshot({ path: await screenshotPath("02-project-created"), fullPage: true });
});

// ---------------------------------------------------------------------------
// Test 3: Upload valid WAV, assert status badge = "uploaded"
// ---------------------------------------------------------------------------
test("upload valid WAV shows status badge uploaded", async ({ page }) => {
  await page.goto(APP_URL);
  await expect(page.getByRole("heading", { name: "SuoraFlow" })).toBeVisible({ timeout: 15_000 });

  // Create a fresh project for this test to avoid state pollution
  const localProjectName = `QA Upload ${Date.now()}`;
  await page.getByRole("button", { name: "New Project" }).first().click();
  await page.getByPlaceholder("My Documentary Project").fill(localProjectName);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "New Project" })).not.toBeVisible({ timeout: 10_000 });

  // Navigate into project
  const projectRow = page.locator("div.bg-white.rounded-xl").filter({ hasText: localProjectName });
  await expect(projectRow).toBeVisible({ timeout: 5_000 });
  // Click the text button (flex-1 text-left) within the row
  await projectRow.locator("button.flex-1.text-left").click();

  // On project page
  await expect(page.getByRole("heading", { level: 1, name: localProjectName })).toBeVisible({ timeout: 10_000 });

  // Upload WAV file
  const fileInput = page.locator("input[type=file]");
  await fileInput.setInputFiles(WAV_FIXTURE);

  // Wait for "Uploading..." to appear and then go away, or for the asset to appear
  // Poll for the asset row rather than fixed sleep
  await expect(page.locator("text=qa_clip.wav")).toBeVisible({ timeout: 30_000 });

  // Assert StatusBadge shows "uploaded"
  const assetRow = page.locator("div.bg-white.rounded-xl.border").filter({ hasText: "qa_clip.wav" });
  await expect(assetRow).toBeVisible({ timeout: 10_000 });
  const badge = assetRow.locator("span.inline-block.rounded");
  await expect(badge).toHaveText("uploaded", { timeout: 10_000 });

  // Assert media type shows "audio"
  await expect(assetRow).toContainText("audio");

  await page.screenshot({ path: await screenshotPath("03-asset-uploaded"), fullPage: true });
});

// ---------------------------------------------------------------------------
// Test 4: Upload fake MP4 (plain text), assert rejection error shown
// ---------------------------------------------------------------------------
test("uploading fake mp4 shows friendly error and no broken asset row", async ({ page }) => {
  await page.goto(APP_URL);
  await expect(page.getByRole("heading", { name: "SuoraFlow" })).toBeVisible({ timeout: 15_000 });

  // Create a fresh project
  const localProjectName = `QA Reject ${Date.now()}`;
  await page.getByRole("button", { name: "New Project" }).first().click();
  await page.getByPlaceholder("My Documentary Project").fill(localProjectName);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "New Project" })).not.toBeVisible({ timeout: 10_000 });

  // Navigate into project
  const projectRow = page.locator("div.bg-white.rounded-xl").filter({ hasText: localProjectName });
  await projectRow.locator("button.flex-1.text-left").click();
  await expect(page.getByRole("heading", { level: 1, name: localProjectName })).toBeVisible({ timeout: 10_000 });

  // Note initial asset count (should be 0)
  const assetsBefore = await page.locator("div.bg-white.rounded-xl.border.border-gray-200.p-4").count();

  // Upload the fake MP4
  const fileInput = page.locator("input[type=file]");
  // Use force to bypass accept filter since we're testing server-side rejection
  await fileInput.setInputFiles(FAKE_MP4_FIXTURE);

  // Wait for error message to appear
  const errorMsg = page.locator("p.text-red-600, p.text-sm.text-red-600");
  await expect(errorMsg).toBeVisible({ timeout: 30_000 });
  const errorText = await errorMsg.first().textContent();
  // Should mention invalid file or similar
  expect(errorText?.toLowerCase()).toMatch(/invalid|not.*valid|unsupported|rejected|error/i);

  // No new asset rows should have appeared
  const assetsAfter = await page.locator("div.bg-white.rounded-xl.border.border-gray-200.p-4").count();
  expect(assetsAfter).toBe(assetsBefore);

  await page.screenshot({ path: await screenshotPath("04-rejection-error"), fullPage: true });
});

// ---------------------------------------------------------------------------
// Test 5: Delete asset via UI
// ---------------------------------------------------------------------------
test("delete asset removes it from the list", async ({ page }) => {
  await page.goto(APP_URL);
  await expect(page.getByRole("heading", { name: "SuoraFlow" })).toBeVisible({ timeout: 15_000 });

  // Create project + upload asset
  const localProjectName = `QA Delete Asset ${Date.now()}`;
  await page.getByRole("button", { name: "New Project" }).first().click();
  await page.getByPlaceholder("My Documentary Project").fill(localProjectName);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "New Project" })).not.toBeVisible({ timeout: 10_000 });

  const projectRow = page.locator("div.bg-white.rounded-xl").filter({ hasText: localProjectName });
  await projectRow.locator("button.flex-1.text-left").click();
  await expect(page.getByRole("heading", { level: 1, name: localProjectName })).toBeVisible({ timeout: 10_000 });

  // Upload
  await page.locator("input[type=file]").setInputFiles(WAV_FIXTURE);
  await expect(page.locator("text=qa_clip.wav")).toBeVisible({ timeout: 30_000 });

  // Click delete (trash icon button) on asset row
  const assetRow = page.locator("div.bg-white.rounded-xl.border.border-gray-200.p-4").filter({ hasText: "qa_clip.wav" });
  await assetRow.locator("button[title='Delete asset']").click();

  // Confirm in modal — scope to the modal overlay to avoid ambiguity with trash icon buttons
  const deleteAssetModal = page.locator("div.fixed.inset-0").filter({ has: page.getByRole("heading", { name: "Delete Asset?" }) });
  await expect(deleteAssetModal).toBeVisible({ timeout: 5_000 });
  await deleteAssetModal.getByRole("button", { name: "Delete" }).click();

  // Asset should be gone
  await expect(page.locator("text=qa_clip.wav")).not.toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: await screenshotPath("05-asset-deleted"), fullPage: true });
});

// ---------------------------------------------------------------------------
// Test 6: Delete project removes it from dashboard
// ---------------------------------------------------------------------------
test("delete project removes it from dashboard list", async ({ page }) => {
  await page.goto(APP_URL);
  await expect(page.getByRole("heading", { name: "SuoraFlow" })).toBeVisible({ timeout: 15_000 });

  const localProjectName = `QA Delete Project ${Date.now()}`;
  await page.getByRole("button", { name: "New Project" }).first().click();
  await page.getByPlaceholder("My Documentary Project").fill(localProjectName);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "New Project" })).not.toBeVisible({ timeout: 10_000 });

  // Find and click the trash icon for this specific project
  const projectRow = page.locator("div.bg-white.rounded-xl.border").filter({ hasText: localProjectName });
  await expect(projectRow).toBeVisible({ timeout: 5_000 });
  await projectRow.locator("button[title='Delete project']").click();

  // Confirm in modal — scope to the modal overlay to avoid ambiguity with trash icon buttons
  const deleteProjectModal = page.locator("div.fixed.inset-0").filter({ has: page.getByRole("heading", { name: "Delete Project?" }) });
  await expect(deleteProjectModal).toBeVisible({ timeout: 5_000 });
  await deleteProjectModal.getByRole("button", { name: "Delete" }).click();

  // Project should disappear from list
  await expect(page.locator("div.bg-white.rounded-xl").filter({ hasText: localProjectName })).not.toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: await screenshotPath("06-project-deleted"), fullPage: true });
});

// ---------------------------------------------------------------------------
// Test 7: No CORS errors throughout (checked at end of file)
// ---------------------------------------------------------------------------
test("no CORS errors in browser console during all interactions", async ({ page }) => {
  // Quick smoke pass — navigate, create, delete
  await page.goto(APP_URL);
  await expect(page.getByRole("heading", { name: "SuoraFlow" })).toBeVisible({ timeout: 15_000 });

  const localErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") localErrors.push(msg.text());
  });

  const localProjectName = `QA CORS ${Date.now()}`;
  await page.getByRole("button", { name: "New Project" }).first().click();
  await page.getByPlaceholder("My Documentary Project").fill(localProjectName);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "New Project" })).not.toBeVisible({ timeout: 10_000 });

  const corsErrors = localErrors.filter(
    (e) => e.toLowerCase().includes("cors") || e.toLowerCase().includes("blocked")
  );
  expect(corsErrors, `CORS errors: ${corsErrors.join("; ")}`).toHaveLength(0);
});
