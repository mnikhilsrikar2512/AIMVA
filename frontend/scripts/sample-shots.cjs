// Screenshots of the sample pages for the public site (public/samples/*.webp).
// 1) cd backend && python -m scripts.landing_samples   2) cd frontend && node scripts/sample-shots.cjs
// Needs Playwright with Chromium, and Python with Pillow (already a backend requirement) for the WebP step.
const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const DIR = path.join(__dirname, "..", "public", "samples");
const KEYS = ["homes", "dental", "coaching", "cafe"];
// name, viewport, scale, full page (capped), WebP width
const SHOTS = [["m", { width: 390, height: 844 }, 2, false, 560], ["full", { width: 390, height: 844 }, 1.5, true, 480], ["d", { width: 1280, height: 800 }, 1, false, 960]];

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "aimva-shots-"));
  const browser = await chromium.launch();
  const jobs = [];
  for (const key of KEYS) {
    for (const [name, viewport, scale, full, width] of SHOTS) {
      const page = await browser.newPage({ viewport, deviceScaleFactor: scale });
      await page.goto("file://" + path.join(DIR, `${key}.html`), { waitUntil: "networkidle" }).catch(() => {});
      await page.addStyleTag({ content: "#aimva-sample{display:none!important}" });
      // Scroll once so reveal-on-scroll sections are drawn in the full-page shot.
      await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 400) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); } scrollTo(0, 0); });
      await page.waitForTimeout(700);
      const h = await page.evaluate(() => document.documentElement.scrollHeight);
      const png = path.join(tmp, `${key}-${name}.png`);
      await page.screenshot({ path: png, fullPage: full, clip: full ? { x: 0, y: 0, width: 390, height: Math.min(h, 2600) } : undefined });
      jobs.push([png, path.join(DIR, `${key}-${name}.webp`), width]);
      await page.close();
    }
  }
  await browser.close();
  const py = "import sys;from PIL import Image\nfor a,b,w in zip(*[iter(sys.argv[1:])]*3):\n im=Image.open(a).convert('RGB');w=int(w);im=im.resize((w,round(im.height*w/im.width)),Image.LANCZOS);im.save(b,'WEBP',quality=72,method=6);print(b,im.size)";
  console.log(execFileSync("python3", ["-c", py, ...jobs.flat().map(String)]).toString());
  console.log("If a full-page height changed, update `tall` in src/components/marketing/samples.js (height / width).");
})();
