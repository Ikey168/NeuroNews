// Driver for the NeuroNews Streamlit app (apps/streamlit).
//
// Drives an already-running Streamlit server with headless Chromium
// (Playwright), screenshots the Home page and the "Ask the News" page, and
// reports page console errors. Streamlit renders async (a "Running…" spinner),
// so we wait for the spinner to clear / network to settle before shooting.
//
// Streamlit must be started separately — spawning long-running servers from
// inside the driver is unreliable in restrictive sandboxes. Launch it with:
//   cd apps/streamlit && streamlit run Home.py --server.port 8502 --server.headless true
// then run this with --url http://localhost:8502.
//
// Playwright is not a project dependency. We resolve it from wherever it lives
// (the global n8n install ships v1.57) and hand launch() the Chromium already
// downloaded under ~/.cache/ms-playwright/. Overrides: PLAYWRIGHT_PATH (dir with
// the playwright package), CHROMIUM_PATH (explicit chrome binary).
//
// Usage:
//   node driver.mjs --url http://localhost:8502
//
// Screenshots land in ./screenshots/<page>.png (next to this file).

import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { mkdirSync, existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SHOT_DIR = join(__dirname, "screenshots");

function loadPlaywright() {
  const candidates = [
    process.env.PLAYWRIGHT_PATH,
    "/usr/local/lib/node_modules/n8n/node_modules",
  ].filter(Boolean);
  for (const base of candidates) {
    try {
      return createRequire(join(base, "noop.js"))("playwright");
    } catch {}
  }
  try {
    return createRequire(import.meta.url)("playwright");
  } catch {}
  console.error(
    "Could not load Playwright. Set PLAYWRIGHT_PATH to a node_modules dir " +
      "that contains it (e.g. /usr/local/lib/node_modules/n8n/node_modules).",
  );
  process.exit(1);
}

// Hand launch() an explicit Chromium — the loaded Playwright's expected browser
// build may not match what's actually downloaded. Newest chromium-<rev> wins.
function findChromium() {
  if (process.env.CHROMIUM_PATH) return process.env.CHROMIUM_PATH;
  const cache = join(homedir(), ".cache", "ms-playwright");
  if (!existsSync(cache)) return null;
  const dirs = readdirSync(cache)
    .filter((d) => d.startsWith("chromium-"))
    .sort()
    .reverse();
  for (const d of dirs) {
    for (const sub of ["chrome-linux64", "chrome-linux"]) {
      const bin = join(cache, d, sub, "chrome");
      if (existsSync(bin)) return bin;
    }
  }
  return null;
}

function parseArgs(argv) {
  const out = { url: "http://localhost:8502" };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--url") out.url = argv[++i];
  }
  return out;
}

// Wait for Streamlit's "Running" status widget to disappear, then for the
// network to go idle. Streamlit keeps a websocket open, so networkidle alone
// isn't enough — the status indicator is the reliable signal.
async function waitForRender(page) {
  try {
    await page.waitForSelector('[data-testid="stStatusWidget"]', {
      state: "detached",
      timeout: 15000,
    });
  } catch {}
  await page.waitForTimeout(1200);
}

async function main() {
  const { url } = parseArgs(process.argv.slice(2));
  const { chromium } = loadPlaywright();
  mkdirSync(SHOT_DIR, { recursive: true });

  const executablePath = findChromium();
  if (executablePath) console.log(`Using Chromium: ${executablePath}`);
  const browser = await chromium.launch({
    headless: true,
    executablePath: executablePath || undefined,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  const consoleErrors = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(String(e)));

  console.log(`Navigating to ${url}`);
  await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
  await waitForRender(page);

  let ok = 0;
  // Home page.
  await page.screenshot({ path: join(SHOT_DIR, "home.png") });
  console.log(`✓ home      -> ${join(SHOT_DIR, "home.png")}`);
  ok++;

  // Try the "Ask the News" page. It imports the full RAG/ML stack
  // (transformers → torchvision, mlflow); if those aren't installed the page
  // wedges on import and never paints its heading. We give it a bounded window
  // and move on — Home is the guaranteed deliverable. Set ASK_TIMEOUT_MS to
  // wait longer if you DO have the ML stack installed.
  const askTimeout = Number(process.env.ASK_TIMEOUT_MS || 20000);
  try {
    await page
      .getByRole("link", { name: /Ask the News/i })
      .first()
      .click({ timeout: 8000 });
    await page
      .getByRole("heading", { name: /Ask the News/i })
      .first()
      .waitFor({ timeout: askTimeout });
    await waitForRender(page);
    await page.screenshot({ path: join(SHOT_DIR, "ask-the-news.png"), fullPage: true });
    console.log(`✓ ask-the-news -> ${join(SHOT_DIR, "ask-the-news.png")}`);
    ok++;
  } catch (e) {
    console.error(
      `! "Ask the News" did not render within ${askTimeout}ms — expected ` +
        `without the ML stack (transformers/torchvision/mlflow). Home is captured.`,
    );
  }

  console.log(`\nPage title: ${await page.title()}`);
  console.log(`Screens captured: ${ok}`);
  if (consoleErrors.length) {
    console.log(`\nConsole errors (${consoleErrors.length}):`);
    for (const e of consoleErrors.slice(0, 10)) console.log(`  - ${e}`);
  } else {
    console.log("No console errors.");
  }

  await browser.close();
  process.exit(ok >= 1 ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
