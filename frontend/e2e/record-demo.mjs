/**
 * record-demo.mjs — Record the SuoraFlow demo walkthrough as a video.
 *
 * Drives a project of real NASA footage (public domain) through the UI with
 * deliberate pacing: dashboard → project → spoken search → visual search
 * (CLIP thumbnails) → click a visual hit → asset page seeked to that moment.
 * Output: /tmp/suoraflow-demo/*.webm
 *
 * Usage: node e2e/record-demo.mjs   (stack up; project named in PROJECT below)
 */
import { chromium } from "@playwright/test";

const APP_URL = process.env.APP_URL ?? "http://localhost:5173";
const OUT_DIR = "/tmp/suoraflow-demo";
const PROJECT = process.env.DEMO_PROJECT ?? "Artemis I — Mission Cut";
const SPOKEN_QUERY = process.env.SPOKEN_QUERY ?? "the most powerful rocket in the world";
const VISUAL_QUERY = process.env.VISUAL_QUERY ?? "rocket lifting off with flames and smoke";

const pause = (ms) => new Promise((r) => setTimeout(r, ms));

/** Type like a human so the query is readable in the recording. */
async function typeSlow(locator, text) {
  await locator.click();
  for (const ch of text) {
    await locator.press(ch === " " ? "Space" : ch);
    await pause(30);
  }
}

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: OUT_DIR, size: { width: 1280, height: 800 } },
});
const page = await context.newPage();

// --- 1. Dashboard ----------------------------------------------------------
await page.goto(APP_URL);
await page.getByText(PROJECT).waitFor();
await pause(1600);

// --- 2. Open the project ----------------------------------------------------
await page.getByRole("button", { name: new RegExp(PROJECT) }).click();
const searchBox = page.getByPlaceholder(/drone footage/);
await searchBox.waitFor();
await pause(1400);

// --- 3. Spoken search --------------------------------------------------------
await typeSlow(searchBox, SPOKEN_QUERY);
await pause(400);
await searchBox.press("Enter");
await page.getByText("Spoken matches").waitFor({ timeout: 30_000 });
await pause(2800);

// --- 4. Add the top spoken hit to the timeline -------------------------------
await page.getByRole("button", { name: "+ Timeline" }).first().click();
await page.getByText(/Timeline — Rough Cut/).waitFor({ timeout: 15_000 });
await pause(2000);

// --- 5. Visual search --------------------------------------------------------
await searchBox.click();
await searchBox.fill("");
await typeSlow(searchBox, VISUAL_QUERY);
await pause(400);
await searchBox.press("Enter");
await page.getByText("Visual matches").waitFor({ timeout: 30_000 });
await pause(1500);
// Bring the CLIP thumbnail grid fully into view
await page.getByText("Visual matches").scrollIntoViewIfNeeded();
await page.mouse.wheel(0, 170);
await pause(3200);

// --- 6. Click the top visual thumbnail → asset page at that timestamp --------
await page
  .locator("img[alt^='Frame at']")
  .first()
  .click();
await page.getByText("Media Info").waitFor({ timeout: 15_000 });
await pause(4500); // player seeked to the matched moment; waveform visible

await context.close(); // flushes the video file
await browser.close();
console.log(`Video saved in ${OUT_DIR}`);
