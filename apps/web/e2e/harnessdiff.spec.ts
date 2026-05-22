import { expect, test } from "@playwright/test";
import path from "node:path";

const screenshotDir = path.resolve("test-results", "screenshots");

test("renders HarnessDiff workbench and captures screenshot", async ({ page }, testInfo) => {
  await page.goto("/");

  await expect(page).toHaveTitle("HarnessDiff");
  await expect(page.getByText("HarnessDiff")).toBeVisible();
  await expect(page.getByRole("heading", { name: "NoHarness", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Harness", exact: true })).toBeVisible();

  const composer = page.locator(".composer");
  await expect(composer).toBeVisible();
  await expect(page.getByRole("button", { name: "送出" })).toBeVisible();

  const overflow = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    bodyWidth: document.body.scrollWidth
  }));
  expect(overflow.documentWidth).toBeLessThanOrEqual(overflow.viewportWidth);
  expect(overflow.bodyWidth).toBeLessThanOrEqual(overflow.viewportWidth);

  await page
    .locator("textarea")
    .first()
    .fill("請比較沒有 Harness 與有 Harness 的差異");
  await page.getByRole("button", { name: "送出" }).click();

  await expect(page.getByText("不額外加入 Harness 控制")).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText("Context Manifest")).toBeVisible({ timeout: 5_000 });
  await expect(page.getByRole("button", { name: "送左側" })).toBeVisible({ timeout: 5_000 });
  await expect(page.getByRole("button", { name: "送右側" })).toBeVisible({ timeout: 5_000 });

  await page.screenshot({
    path: path.join(screenshotDir, `${testInfo.project.name}.png`),
    fullPage: true
  });
});
