import { expect, test } from "@playwright/test";
import path from "node:path";

const screenshotDir = path.resolve("test-results", "screenshots");

test("renders HarnessDiff workbench and captures screenshot", async ({ page }, testInfo) => {
  await page.route("**/api/**", async (route) => {
    await route.abort();
  });

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

  await page.getByRole("button", { name: "Harness settings" }).click();
  await expect(page.getByLabel("Harness module toggles")).toBeVisible();
  await page.getByLabel("Output Contract").uncheck();
  await expect(page.getByLabel("Output Contract")).not.toBeChecked();

  const overflowAfterSettings = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    bodyWidth: document.body.scrollWidth
  }));
  expect(overflowAfterSettings.documentWidth).toBeLessThanOrEqual(
    overflowAfterSettings.viewportWidth
  );
  expect(overflowAfterSettings.bodyWidth).toBeLessThanOrEqual(overflowAfterSettings.viewportWidth);

  await page.screenshot({
    path: path.join(screenshotDir, `${testInfo.project.name}.png`),
    fullPage: true
  });
});

test("renders analysis metrics from streamed API events", async ({ page }) => {
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "proj_e2e" })
    });
  });
  await page.route("**/api/projects/proj_e2e/runs", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "run_e2e" })
    });
  });
  await page.route("**/api/runs/run_e2e/analysis", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockAnalysis)
    });
  });
  await page.route("**/api/runs/run_e2e/stream", async (route) => {
    const lines = [
      { run_id: "run_e2e", pane: "NoHarness", type: "created", sequence: 0 },
      { run_id: "run_e2e", pane: "NoHarness", type: "delta", text: "baseline", sequence: 1 },
      { run_id: "run_e2e", pane: "NoHarness", type: "completed", sequence: 2 },
      { run_id: "run_e2e", pane: "Harness", type: "created", sequence: 0 },
      { run_id: "run_e2e", pane: "Harness", type: "delta", text: "harness", sequence: 1 },
      { run_id: "run_e2e", pane: "Harness", type: "completed", sequence: 2 },
      { run_id: "run_e2e", type: "analysis_ready", analysis: mockAnalysis },
      { run_id: "run_e2e", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  await page.locator("textarea").first().fill("stream with analysis");
  await page.getByRole("button", { name: "送出" }).click();

  await expect(page.getByText("本回合分析已產生")).toBeVisible();
  await expect(page.getByText("Delta +8 tokens")).toBeVisible();
  await expect(page.getByText("NoHarness 42 / 100")).toBeVisible();
  await expect(page.getByText("Harness 50 / 120")).toBeVisible();
  await expect(page.getByText("Context 3/2")).toBeVisible();
});

test("renders assistant Markdown and copies raw Markdown source", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const markdown = [
    "## 回答",
    "",
    "這是**重點**與 `code`。",
    "",
    "- 第一點",
    "- 第二點"
  ].join("\n");

  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "proj_markdown" })
    });
  });
  await page.route("**/api/projects/proj_markdown/runs", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "run_markdown" })
    });
  });
  await page.route("**/api/runs/run_markdown/stream", async (route) => {
    const lines = [
      { run_id: "run_markdown", pane: "NoHarness", type: "created", sequence: 0 },
      { run_id: "run_markdown", pane: "NoHarness", type: "delta", text: markdown, sequence: 1 },
      { run_id: "run_markdown", pane: "NoHarness", type: "completed", sequence: 2 },
      { run_id: "run_markdown", pane: "Harness", type: "created", sequence: 0 },
      { run_id: "run_markdown", pane: "Harness", type: "delta", text: markdown, sequence: 1 },
      { run_id: "run_markdown", pane: "Harness", type: "completed", sequence: 2 },
      { run_id: "run_markdown", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  await page.locator("textarea").first().fill("markdown please");
  await page.getByRole("button", { name: "送出" }).click();

  const assistantMessage = page.locator(".message.assistant").first();
  await expect(assistantMessage.getByRole("heading", { name: "回答" })).toBeVisible();
  await expect(assistantMessage.locator("strong", { hasText: "重點" })).toBeVisible();
  await expect(assistantMessage.locator("code", { hasText: "code" })).toBeVisible();
  await expect(assistantMessage.locator("li", { hasText: "第一點" })).toBeVisible();

  await assistantMessage.getByRole("button", { name: "複製 Markdown 原始碼" }).click();
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText().then((text) => text.replace(/\r\n/g, "\n"))))
    .toBe(markdown);
});

test("creates a named conversation and shows it in history", async ({ page }) => {
  const projects: Array<{ id: string; name: string; created_at: string; updated_at: string }> = [];
  let createdProjectName = "";
  const now = "2026-05-23T00:00:00+00:00";

  await page.route("**/api/projects", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ projects })
      });
      return;
    }
    const body = route.request().postDataJSON() as { name: string };
    createdProjectName = body.name;
    projects.unshift({ id: "proj_history", name: body.name, created_at: now, updated_at: now });
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(projects[0])
    });
  });
  await page.route("**/api/projects/proj_history/runs", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "run_history" })
    });
  });
  await page.route("**/api/runs/run_history/stream", async (route) => {
    const lines = [
      { run_id: "run_history", pane: "NoHarness", type: "created", sequence: 0 },
      { run_id: "run_history", pane: "NoHarness", type: "delta", text: "baseline", sequence: 1 },
      { run_id: "run_history", pane: "NoHarness", type: "completed", sequence: 2 },
      { run_id: "run_history", pane: "Harness", type: "created", sequence: 0 },
      { run_id: "run_history", pane: "Harness", type: "delta", text: "harness", sequence: 1 },
      { run_id: "run_history", pane: "Harness", type: "completed", sequence: 2 },
      { run_id: "run_history", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  await page.locator("textarea").first().fill("這是一段會自動命名的歷史對話");
  await page.getByRole("button", { name: "送出" }).click();

  await expect(page.getByText("baseline")).toBeVisible();
  expect(createdProjectName).toBe("這是一段會自動命名的歷史對話");

  await page.getByRole("button", { name: "歷史" }).click();
  await expect(page.getByLabel("歷史對話紀錄")).toBeVisible();
  await expect(page.getByRole("button", { name: /這是一段會自動命名的歷史對話/ })).toBeVisible();
});

test("pauses a running mock response", async ({ page }) => {
  await page.route("**/api/projects", async (route) => {
    await route.abort();
  });

  await page.goto("/");
  await page.locator("textarea").first().fill("pause this response");
  await page.getByRole("button", { name: "送出" }).click();
  await expect(page.getByRole("button", { name: "暫停執行" })).toBeVisible();
  await page.getByRole("button", { name: "暫停執行" }).click();
  await expect(page.getByRole("button", { name: "暫停執行" })).toHaveCount(0);
});

const mockAnalysis = {
  schema_version: "2026-05-22.1",
  project_id: "proj_e2e",
  run_id: "run_e2e",
  turn_index: 0,
  generated_at: "2026-05-23T00:00:00+00:00",
  panes: {
    NoHarness: {
      pane: "NoHarness",
      current_turn_usage: {
        input_tokens: 30,
        output_tokens: 12,
        reasoning_tokens: 0,
        total_tokens: 42,
        source: "provider_reported"
      },
      cumulative_usage: {
        input_tokens: 72,
        output_tokens: 28,
        reasoning_tokens: 0,
        total_tokens: 100,
        source: "provider_reported"
      },
      context_sections: [
        { key: "system_prompt", label: "System", status: "sent", characters: 20, estimated_tokens: 5 },
        { key: "current_user_turn", label: "Current", status: "sent", characters: 20, estimated_tokens: 5 }
      ],
      output_characters: 8,
      enabled_harness_modules: [],
      provider_context_keys: ["instructions", "prompt"]
    },
    Harness: {
      pane: "Harness",
      current_turn_usage: {
        input_tokens: 35,
        output_tokens: 15,
        reasoning_tokens: 0,
        total_tokens: 50,
        source: "provider_reported"
      },
      cumulative_usage: {
        input_tokens: 85,
        output_tokens: 35,
        reasoning_tokens: 0,
        total_tokens: 120,
        source: "provider_reported"
      },
      context_sections: [
        { key: "system_prompt", label: "System", status: "sent", characters: 20, estimated_tokens: 5 },
        { key: "behavior_preferences", label: "Behavior", status: "sent", characters: 20, estimated_tokens: 5 },
        { key: "current_user_turn", label: "Current", status: "sent", characters: 20, estimated_tokens: 5 }
      ],
      output_characters: 7,
      enabled_harness_modules: ["context_manifest"],
      provider_context_keys: ["instructions", "prompt"]
    }
  },
  comparison: {
    total_token_delta: 8,
    input_token_delta: 5,
    output_token_delta: 3,
    reasoning_token_delta: 0,
    harness_extra_sections: ["behavior_preferences"]
  },
  notes: []
};
