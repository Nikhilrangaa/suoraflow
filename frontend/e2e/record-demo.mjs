/**
 * record-demo.mjs — Record the SuoraFlow demo walkthrough as a video.
 *
 * Drives a project of real NASA footage (public domain) through the UI with
 * deliberate pacing: dashboard → project → spoken search → visual search
 * (CLIP thumbnails) → click a visual hit → asset page seeked to that moment →
 * back → paste a script → generate a rough cut (per-beat match report,
 * including a silent-b-roll visual match) → the assembled timeline.
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
// Each paragraph is a beat. Wordings are tuned so beat 3 resolves as a CLIP
// visual match on the silent tracking clip — the "search footage with no
// speech" story — while the others land on distinct transcript chunks.
const DEMO_SCRIPT =
  process.env.DEMO_SCRIPT ??
  [
    "Fifty years after we last set foot on the moon, a new mission takes its first bold step back.",
    "The countdown hits zero and the worlds most powerful rocket lifts off.",
    "Bright exhaust flame against a pitch black background.",
    "The spacecraft flies free, beginning its long journey to the moon.",
  ].join("\n\n");
const TIMELINE_NAME = process.env.TIMELINE_NAME ?? "Artemis Story";

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
await pause(1500);

// --- 2. Open the project ----------------------------------------------------
await page.getByRole("button", { name: new RegExp(PROJECT) }).click();
const searchBox = page.getByPlaceholder(/drone footage/);
await searchBox.waitFor();
await pause(1300);

// --- 3. Spoken search --------------------------------------------------------
await typeSlow(searchBox, SPOKEN_QUERY);
await pause(400);
await searchBox.press("Enter");
await page.getByText("Spoken matches").waitFor({ timeout: 30_000 });
await pause(2600);

// --- 4. Visual search --------------------------------------------------------
await searchBox.click();
await searchBox.fill("");
await typeSlow(searchBox, VISUAL_QUERY);
await pause(400);
await searchBox.press("Enter");
await page.getByText("Visual matches").waitFor({ timeout: 30_000 });
await pause(1200);
// Bring the CLIP thumbnail grid fully into view
await page.getByText("Visual matches").scrollIntoViewIfNeeded();
await page.mouse.wheel(0, 170);
await pause(2800);

// --- 5. Click the top visual thumbnail → asset page at that timestamp --------
await page
  .locator("img[alt^='Frame at']")
  .first()
  .click();
await page.getByText("Media Info").waitFor({ timeout: 15_000 });
// Let the transcript load and its follow-along scroll fire first, then bring
// the player into frame (the SPA keeps the previous scroll position)
await pause(1300);
await page.evaluate(() => window.scrollTo({ top: 0, behavior: "auto" }));
await pause(2800); // player seeked to the matched moment; waveform visible

// --- 6. Back to the project → rough cut from a script ------------------------
await page.getByRole("button", { name: "Back" }).first().click();
const scriptBox = page.getByPlaceholder(/Paste your script/);
await scriptBox.waitFor();
await scriptBox.scrollIntoViewIfNeeded();
await pause(900);
// Paste (don't type) — editors paste scripts; keep the recording moving
await scriptBox.fill(DEMO_SCRIPT);
await page.getByPlaceholder("Timeline name (optional)").fill(TIMELINE_NAME);
await pause(1800); // let the viewer read the beats
await page.getByRole("button", { name: "Generate" }).click();
await page.getByText(/beats matched/).waitFor({ timeout: 60_000 });
await pause(3500); // per-beat report: spoken matches + the purple visual beat

// --- 7. The assembled timeline ----------------------------------------------
await page
  .getByText(new RegExp(`Timeline — ${TIMELINE_NAME}`))
  .scrollIntoViewIfNeeded();
await page.mouse.wheel(0, 120);
await pause(3200); // four ordered clips + JSON/CSV export links

await context.close(); // flushes the video file
await browser.close();
console.log(`Video saved in ${OUT_DIR}`);
