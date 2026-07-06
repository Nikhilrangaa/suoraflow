/**
 * Full-flow E2E — the complete SuoraFlow story against a live stack:
 *
 *   1. Create a project and upload the committed speech fixture.
 *   2. Watch the pipeline drive the status badge to "ready".
 *   3. Open the asset: player, waveform, metadata, transcript render.
 *   4. Semantic search returns a ranked, timestamped result.
 *   5. Add the hit to the timeline and export is offered as JSON/CSV.
 *
 * Requires `docker compose up` (backend + worker + db + redis + frontend).
 * The first run after a volume wipe downloads model weights, so the
 * ready-wait uses a generous timeout.
 */
import * as path from "path";
import { fileURLToPath } from "url";
import { test, expect } from "@playwright/test";

const APP_URL = process.env.APP_URL ?? "http://localhost:5173";
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SPEECH_FIXTURE = path.resolve(__dirname, "../../fixtures/demo_interview.wav");

const PROJECT_NAME = `QA FullFlow ${Date.now()}`;
const READY_TIMEOUT = 5 * 60_000; // tolerate cold model download

test.describe.configure({ mode: "serial" });

test("full flow: upload → pipeline → transcript → search → timeline", async ({ page }) => {
  test.setTimeout(READY_TIMEOUT + 60_000);

  // --- create project ------------------------------------------------------
  await page.goto(APP_URL);
  await page.getByRole("button", { name: "New Project" }).first().click();
  await page.getByPlaceholder("My Documentary Project").fill(PROJECT_NAME);
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByRole("button", { name: new RegExp(PROJECT_NAME) }).click();

  // --- upload the speech fixture ------------------------------------------
  await page.locator("input[type=file]").setInputFiles(SPEECH_FIXTURE);
  const assetRow = page
    .locator("div.bg-white.rounded-xl.border")
    .filter({ hasText: "demo_interview.wav" });
  await expect(assetRow).toBeVisible({ timeout: 30_000 });

  // --- pipeline reaches ready (badge polls live) ---------------------------
  await expect(assetRow.locator("span.rounded").first()).toHaveText("ready", {
    timeout: READY_TIMEOUT,
  });

  // --- asset page: metadata + waveform + transcript ------------------------
  await assetRow.getByRole("button").first().click();
  await expect(page.getByText("Media Info")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("16,000 Hz")).toBeVisible();
  await expect(page.getByText("1 (mono)")).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible(); // waveform
  await expect(page.getByText(/mountain expedition/i).first()).toBeVisible();

  // Transcript click seeks the player
  await page.getByRole("button", { name: /drone footage of the sunrise/i }).click();

  // --- back to project: semantic search ------------------------------------
  await page.getByTitle("Back", { exact: true }).click();
  const searchBox = page.getByPlaceholder(/drone footage/);
  await searchBox.fill("celebration with hot drinks at the camp");
  await searchBox.press("Enter");

  const firstResult = page.locator("li").filter({ hasText: "%" }).first();
  await expect(firstResult).toBeVisible({ timeout: 30_000 });
  await expect(firstResult).toContainText(/base camp|celebrates/i);

  // --- add to timeline + export offered ------------------------------------
  await firstResult.getByRole("button", { name: "+ Timeline" }).click();
  await expect(page.getByText(/Timeline — Rough Cut/)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("link", { name: "Export JSON" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Export CSV" })).toBeVisible();

  // --- cleanup: delete the QA project --------------------------------------
  await page.getByTitle("Back", { exact: true }).click();
  const projectCard = page
    .locator("div.bg-white.rounded-xl.border")
    .filter({ hasText: PROJECT_NAME });
  await projectCard.getByTitle("Delete project").click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(projectCard).not.toBeVisible({ timeout: 10_000 });
});
