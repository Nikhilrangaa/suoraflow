/**
 * record-demo.mjs — Record the SuoraFlow demo walkthrough as a video.
 *
 * Drives the seeded demo project through the real UI with deliberate pacing:
 * dashboard → project → semantic search → add to timeline → asset page
 * (waveform + transcript click-to-seek). Output: /tmp/suoraflow-demo/*.webm
 *
 * Usage: node e2e/record-demo.mjs   (stack must be up and demo seeded)
 */
import { chromium } from "@playwright/test";

const APP_URL = process.env.APP_URL ?? "http://localhost:5173";
const OUT_DIR = "/tmp/suoraflow-demo";
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

/** Type like a human so the search query is readable in the recording. */
async function typeSlow(locator, text) {
  await locator.click();
  for (const ch of text) {
    await locator.press(ch === " " ? "Space" : ch);
    await pause(35);
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
await page.getByText("Demo — Mountain Documentary").waitFor();
await pause(1800);

// --- 2. Open the demo project ---------------------------------------------
await page.getByRole("button", { name: /Demo — Mountain Documentary/ }).click();
await page.getByPlaceholder(/drone footage/).waitFor();
await pause(1500);

// --- 3. Semantic search -----------------------------------------------------
const searchBox = page.getByPlaceholder(/drone footage/);
await typeSlow(searchBox, "drone footage of the sunrise");
await pause(600);
await searchBox.press("Enter");
await page.locator("li").filter({ hasText: "%" }).first().waitFor({ timeout: 30_000 });
await pause(2500);

// --- 4. Add the top hit to the timeline ------------------------------------
await page.getByRole("button", { name: "+ Timeline" }).first().click();
await page.getByText(/Timeline — Rough Cut/).waitFor({ timeout: 15_000 });
await pause(2200);

// --- 5. Asset page: waveform + transcript -----------------------------------
await page.getByRole("button", { name: /demo_interview\.wav ready/ }).click();
await page.getByText("Media Info").waitFor({ timeout: 15_000 });
await pause(2000);

// Click a transcript segment → player seeks and plays, waveform follows
await page.getByRole("button", { name: /drone footage of the Sunrise/i }).click();
await pause(5000); // let the playhead visibly move across the waveform

await context.close(); // flushes the video file
await browser.close();
console.log(`Video saved in ${OUT_DIR}`);
