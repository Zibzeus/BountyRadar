// Run against a populated local development instance with disposable credentials.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const origin = process.env.RADAR_TEST_ORIGIN || "http://127.0.0.1:8000";
assert.ok(
  process.env.RADAR_TEST_PASSWORD,
  "Set RADAR_TEST_PASSWORD to a disposable account password",
);
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH || undefined,
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 900 },
  });
  const errors = [];
  page.on("pageerror", (err) => errors.push(err.message));
  await page.goto(origin);
  await page
    .getByLabel("Username", { exact: true })
    .fill(process.env.RADAR_TEST_USER || "admin");
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.RADAR_TEST_PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("heading", { name: "Program directory" }).waitFor();
  const first = page.locator("button.program-name").first();
  await first.waitFor();
  await first.click();
  await page.getByRole("heading", { name: "Program scope" }).waitFor();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Export workspace" }).click();
  assert.match((await download).suggestedFilename(), /\.zip$/);
  await page.getByRole("button", { name: "Program directory" }).click();
  const region=page.getByRole("region",{name:"Program directory results"});
  await region.focus();
  assert.equal(await region.evaluate(el=>el===document.activeElement),true);
  if (process.env.RADAR_SCREENSHOT) await page.screenshot({path:process.env.RADAR_SCREENSHOT});
  for (const [tab,heading] of [["Changes","Changes"],["Sources","Source directory"],["Research","Research a program"],["Connections","Add connection"],["Settings","Scoring preferences"]]) {
    await page.getByRole("navigation").getByRole("button",{name:tab,exact:true}).click();
    await page.getByRole("heading",{name:heading,exact:true}).first().waitFor();
  }
  await page.getByRole("navigation").getByRole("button",{name:"Discover",exact:true}).click();
  await region.waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.locator(".scroll tbody tr").first().evaluate(el=>getComputedStyle(el).display),"grid");
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
    "Mobile overflow",
  );
  assert.deepEqual(errors, []);
  console.log(
    "Browser acceptance passed: session, catalog, detail, ZIP download, mobile viewport",
  );
} finally {
  await browser.close();
}
