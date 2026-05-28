import { expect, test } from "@playwright/test";
import path from "node:path";

const screenshotDir = path.resolve("test-results", "screenshots");

test("renders HarnessDiff workbench and captures screenshot", async ({ page }, testInfo) => {
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ projects: [] })
    });
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

  await page.getByRole("button", { name: "個別獨立輸入" }).click();
  await expect(page.getByRole("button", { name: "送 NoHarness" })).toBeVisible({ timeout: 5_000 });
  await expect(page.getByRole("button", { name: "送 Harness" })).toBeVisible({ timeout: 5_000 });

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
  await page.route("**/api/runs/run_e2e/stream", async (route) => {
    const lines = [
      { run_id: "run_e2e", profile_id: "baseline", profile_label: "NoHarness", type: "created", sequence: 0 },
      { run_id: "run_e2e", profile_id: "baseline", profile_label: "NoHarness", type: "delta", text: "baseline", sequence: 1 },
      { run_id: "run_e2e", profile_id: "baseline", profile_label: "NoHarness", type: "completed", sequence: 2 },
      { run_id: "run_e2e", profile_id: "harness", profile_label: "Harness", type: "created", sequence: 0 },
      { run_id: "run_e2e", profile_id: "harness", profile_label: "Harness", type: "delta", text: "harness", sequence: 1 },
      { run_id: "run_e2e", profile_id: "harness", profile_label: "Harness", type: "completed", sequence: 2 },
      { run_id: "run_e2e", type: "analysis_ready", analysis: analysisFixture },
      { run_id: "run_e2e", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  await page.locator(".promptEditor").first().fill("stream with analysis");
  await page.getByRole("button", { name: "送出" }).click();

  await expect(page.getByText("本回合分析已產生")).toBeVisible();
  await expect(page.getByText("Delta +8 tokens")).toBeVisible();
  await expect(
    page.getByText("NoHarness input tokens 30 (cached input 10) · output tokens 12 · reasoning 0 · total 42 · Σ 100")
  ).toBeVisible();
  await expect(
    page.getByText("Harness input tokens 35 (cached input 15) · output tokens 15 · reasoning 0 · total 50 · Σ 120")
  ).toBeVisible();
  await expect(page.getByText(/^Turn 1$/)).toBeVisible();
});

test("attaches readable files and sends their context with the prompt", async ({ page }) => {
  let submittedPrompt = "";
  let submittedAttachments: unknown[] = [];

  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "proj_attach" })
    });
  });
  await page.route("**/api/projects/proj_attach/runs", async (route) => {
    const payload = route.request().postDataJSON() as { prompt: string; attachments?: unknown[] };
    submittedPrompt = payload.prompt;
    submittedAttachments = payload.attachments ?? [];
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "run_attach" })
    });
  });
  await page.route("**/api/runs/run_attach/stream", async (route) => {
    const lines = [
      { run_id: "run_attach", profile_id: "baseline", profile_label: "NoHarness", type: "completed", sequence: 1 },
      { run_id: "run_attach", profile_id: "harness", profile_label: "Harness", type: "completed", sequence: 1 },
      { run_id: "run_attach", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });
  await page.goto("/");
  await page.getByLabel("Attach file").setInputFiles({
    name: "scores.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("name,score\nAda,10")
  });
  await page.getByLabel("Attach file").setInputFiles({
    name: "diagram.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/l1ExWQAAAABJRU5ErkJggg==",
      "base64"
    )
  });
  await expect(page.getByRole("button", { name: /scores.csv/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /diagram.png/ })).toBeVisible();
  await page.locator(".promptEditor").first().fill("請看附件");
  await page.getByRole("button", { name: "送出" }).click();

  await expect.poll(() => submittedPrompt).toContain("User-provided attachments");
  expect(submittedPrompt).toContain("Attachment 1: scores.csv");
  expect(submittedPrompt).toContain("Attachment 2: diagram.png");
  expect(submittedPrompt).toContain("pandas.DataFrame preview");
  expect(submittedPrompt).toContain("Ada | 10");
  expect(submittedAttachments).toHaveLength(1);
  const userMessage = page.locator(".message.user").first();
  await expect(userMessage).toContainText("請看附件");
  await expect(userMessage).not.toContainText("User-provided attachments");
  await expect(userMessage.getByRole("img", { name: "diagram.png" })).toBeVisible();
});

test("uses browser speech recognition output as voice input", async ({ page }) => {
  await page.addInitScript(() => {
    class MockSpeechRecognition {
      continuous = false;
      interimResults = false;
      lang = "";
      onresult: ((event: { results: Array<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null = null;
      onerror: (() => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        this.onresult?.({ results: [{ 0: { transcript: "語音輸入文字" }, isFinal: true }] });
        this.onend?.();
      }
      stop() {
        this.onend?.();
      }
    }
    window.SpeechRecognition = MockSpeechRecognition as typeof window.SpeechRecognition;
  });
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ projects: [] })
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Hold to voice input" }).hover();
  await page.mouse.down();
  await expect(page.locator(".promptEditor").first()).toHaveText("語音輸入文字");
  await page.mouse.up();
});

test("lists skills and imports a skill file", async ({ page }) => {
  const skills: Array<{ id: string; name: string; description: string; version: string; path: string }> = [];
  let importPayload: { mode: string; filename: string; data_base64: string } | null = null;

  await page.route("**/api/skills/import", async (route) => {
    importPayload = route.request().postDataJSON();
    skills.push({
      id: "demo-skill",
      name: "demo-skill",
      description: "Demo skill description",
      version: "",
      path: "C:\\Users\\demo\\.harnessdiff\\skills\\demo-skill"
    });
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ skill: skills[0] })
    });
  });
  await page.route("**/api/skills/demo-skill", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "demo-skill",
        path: "C:\\Users\\demo\\.harnessdiff\\skills\\demo-skill\\SKILL.md",
        content: "---\nname: demo-skill\ndescription: Demo skill description\n---\n# Demo"
      })
    });
  });
  await page.route("**/api/skills", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        home_dir: "C:\\Users\\demo\\.harnessdiff",
        skills_dir: "C:\\Users\\demo\\.harnessdiff\\skills",
        skills
      })
    });
  });
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ projects: [] })
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "技能" }).click();
  await expect(page.getByLabel("技能管理")).toBeVisible();
  await page.locator('input[accept=".zip,.skill,.md"]').setInputFiles({
    name: "demo.skill",
    mimeType: "text/markdown",
    buffer: Buffer.from("---\nname: demo-skill\ndescription: Demo skill description\n---\n")
  });

  await expect(page.getByRole("button", { name: /demo-skill/ })).toBeVisible();
  await page.getByRole("button", { name: /demo-skill/ }).click();
  await expect(page.getByLabel("完整 SKILL.md")).toContainText("Demo skill description");
  expect(importPayload?.mode).toBe("skill");
  expect(importPayload?.filename).toBe("demo.skill");
  expect(importPayload?.data_base64).toBeTruthy();
});

test("uses skill slash commands in the composer", async ({ page }) => {
  let submittedPrompt = "";
  const skill = {
    id: "demo-skill",
    name: "demo-skill",
    description: "Demo skill description",
    version: "",
    path: "C:\\Users\\demo\\.harnessdiff\\skills\\demo-skill"
  };

  await page.route("**/api/skills/demo-skill", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "demo-skill",
        path: "C:\\Users\\demo\\.harnessdiff\\skills\\demo-skill\\SKILL.md",
        content: "---\nname: demo-skill\ndescription: Demo skill description\n---\n# Demo workflow"
      })
    });
  });
  await page.route("**/api/skills", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        home_dir: "C:\\Users\\demo\\.harnessdiff",
        skills_dir: "C:\\Users\\demo\\.harnessdiff\\skills",
        skills: [skill]
      })
    });
  });
  await page.route("**/api/projects", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ projects: [] })
      });
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "proj_slash", name: "Slash command" })
    });
  });
  await page.route("**/api/projects/proj_slash/runs", async (route) => {
    submittedPrompt = (route.request().postDataJSON() as { prompt: string }).prompt;
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "run_slash" })
    });
  });
  await page.route("**/api/runs/run_slash/stream", async (route) => {
    const lines = [
      { run_id: "run_slash", profile_id: "baseline", profile_label: "NoHarness", type: "completed", sequence: 1 },
      { run_id: "run_slash", profile_id: "harness", profile_label: "Harness", type: "completed", sequence: 1 },
      { run_id: "run_slash", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  const editor = page.locator(".promptEditor").first();
  await editor.fill("/");
  await expect(page.getByRole("option", { name: /demo-skill/ })).toBeVisible();
  await page.getByRole("option", { name: /demo-skill/ }).click();
  const token = editor.locator(".skillCommandToken");
  await expect(token).toHaveText("/demo-skill");
  await expect(token).toHaveCSS("color", "rgb(15, 118, 110)");
  await expect(token).toHaveAttribute("contenteditable", "false");
  await page.keyboard.press("Backspace");
  await expect(token).toHaveCount(0);
  await expect(editor).toHaveText("");
  await editor.fill("/demo-skill 請照這個技能回答");
  await expect(editor.locator(".skillCommandToken")).toHaveText("/demo-skill");
  await page.getByRole("button", { name: "送出" }).click();

  await expect.poll(() => submittedPrompt).toContain("Requested skill details");
  expect(submittedPrompt).toContain("Requested skill 1: demo-skill");
  expect(submittedPrompt).toContain("# Demo workflow");
});

test("allows independent panes to submit while the other pane is still running", async ({ page }) => {
  let releaseBaseline: () => void = () => undefined;
  const baselineGate = new Promise<void>((resolve) => {
    releaseBaseline = resolve;
  });

  await page.route("**/api/projects", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ projects: [] })
      });
      return;
    }
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "proj_independent", name: "Independent" })
    });
  });
  await page.route("**/api/projects/proj_independent/runs", async (route) => {
    const body = route.request().postDataJSON() as { profiles: Array<{ id: string }> };
    const profileId = body.profiles[0]?.id ?? "unknown";
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: `run_${profileId}` })
    });
  });
  await page.route("**/api/runs/run_baseline/stream", async (route) => {
    await baselineGate;
    const lines = [
      { run_id: "run_baseline", profile_id: "baseline", profile_label: "NoHarness", type: "delta", text: "baseline done", sequence: 1 },
      { run_id: "run_baseline", profile_id: "baseline", profile_label: "NoHarness", type: "completed", sequence: 2 },
      { run_id: "run_baseline", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });
  await page.route("**/api/runs/run_harness/stream", async (route) => {
    const lines = [
      { run_id: "run_harness", profile_id: "harness", profile_label: "Harness", type: "delta", text: "harness done", sequence: 1 },
      { run_id: "run_harness", profile_id: "harness", profile_label: "Harness", type: "completed", sequence: 2 },
      { run_id: "run_harness", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "個別獨立輸入" }).click();
  const editors = page.locator(".splitInputRow .promptEditor");
  await editors.nth(0).fill("baseline prompt");
  await editors.nth(1).fill("harness prompt");

  await page.getByRole("button", { name: "送 NoHarness" }).click();
  await expect(page.getByRole("button", { name: "送 NoHarness" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "送 Harness" })).toBeEnabled();

  await page.getByRole("button", { name: "送 Harness" }).click();
  await expect(page.getByText("harness done")).toBeVisible();
  releaseBaseline();
  await expect(page.getByText("baseline done")).toBeVisible();
});

test("renders each tool call as a collapsible control with subagent styling", async ({ page }) => {
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "proj_tools" })
    });
  });
  await page.route("**/api/projects/proj_tools/runs", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "run_tools" })
    });
  });
  await page.route("**/api/runs/run_tools/stream", async (route) => {
    const lines = [
      { run_id: "run_tools", profile_id: "baseline", profile_label: "NoHarness", type: "created", sequence: 0 },
      { run_id: "run_tools", profile_id: "baseline", profile_label: "NoHarness", type: "delta", text: "baseline", sequence: 1 },
      { run_id: "run_tools", profile_id: "baseline", profile_label: "NoHarness", type: "completed", sequence: 2 },
      { run_id: "run_tools", profile_id: "harness", profile_label: "Harness", type: "created", sequence: 0 },
      {
        run_id: "run_tools",
        profile_id: "harness",
        profile_label: "Harness",
        type: "tool_call",
        sequence: 1,
        tool_call: {
          ok: true,
          tool_name: "standard.web.search",
          openai_name: "standard_web_search",
          arguments: { query: "TAIEX 最近 10 個交易日" },
          elapsed_ms: 120,
          result_summary: JSON.stringify({ results: [{ title: "TWSE" }] })
        }
      },
      {
        run_id: "run_tools",
        profile_id: "harness",
        profile_label: "Harness",
        type: "tool_call",
        sequence: 2,
        tool_call: {
          ok: true,
          tool_name: "standard.web.fetch",
          openai_name: "standard_web_fetch",
          arguments: { url: "https://example.com" },
          elapsed_ms: 88,
          result_summary: JSON.stringify({ status: 200 })
        }
      },
      {
        run_id: "run_tools",
        profile_id: "harness",
        profile_label: "Harness",
        type: "tool_call",
        sequence: 3,
        tool_call: {
          ok: true,
          tool_name: "harness.subagent.run",
          openai_name: "harness_subagent_run",
          arguments: { subagent_id: "researcher", task: "verify sources", context: "TAIEX query" },
          elapsed_ms: 640,
          subagent_id: "researcher",
          subagent_label: "Researcher",
          result_summary: JSON.stringify({ text: "research notes" })
        }
      },
      { run_id: "run_tools", profile_id: "harness", profile_label: "Harness", type: "delta", text: "done", sequence: 4 },
      { run_id: "run_tools", profile_id: "harness", profile_label: "Harness", type: "completed", sequence: 5 },
      { run_id: "run_tools", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  await page.locator(".promptEditor").first().fill("show tools");
  await page.getByRole("button", { name: "送出" }).click();

  const harnessPane = page.locator(".controlledProfile");
  const toolControls = harnessPane.locator(".toolCallDisclosure");
  await expect(toolControls).toHaveCount(3);
  await expect(toolControls.nth(0).locator("summary")).toContainText("standard.web.search");
  await expect(toolControls.nth(1).locator("summary")).toContainText("standard.web.fetch");
  await expect(toolControls.nth(2).locator("summary")).toContainText("harness.subagent.run");
  await expect(toolControls.nth(2)).toHaveClass(/subagentToolCall/);

  await toolControls.nth(0).locator("summary").click();
  await expect(toolControls.nth(0).getByText("輸入引數")).toBeVisible();
  await expect(toolControls.nth(0).locator("pre").first()).toContainText("TAIEX 最近 10 個交易日");
  await expect(toolControls.nth(0).locator("pre").nth(1)).toContainText("TWSE");
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
      { run_id: "run_markdown", profile_id: "baseline", profile_label: "NoHarness", type: "created", sequence: 0 },
      { run_id: "run_markdown", profile_id: "baseline", profile_label: "NoHarness", type: "delta", text: markdown, sequence: 1 },
      { run_id: "run_markdown", profile_id: "baseline", profile_label: "NoHarness", type: "completed", sequence: 2 },
      { run_id: "run_markdown", profile_id: "harness", profile_label: "Harness", type: "created", sequence: 0 },
      { run_id: "run_markdown", profile_id: "harness", profile_label: "Harness", type: "delta", text: markdown, sequence: 1 },
      { run_id: "run_markdown", profile_id: "harness", profile_label: "Harness", type: "completed", sequence: 2 },
      { run_id: "run_markdown", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  await page.locator(".promptEditor").first().fill("markdown please");
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

test("renders GitHub-style Markdown tables", async ({ page }) => {
  const markdown = [
    "以下是表格：",
    "",
    "| 支持先做 SSO | 反對先做 SSO |",
    "|---|---|",
    "| 客戶 A 要求 SSO | 本週先評估 audit log |",
    "| Sales 認為 SSO 影響續約 | 客戶 B 也有 audit log 需求 |"
  ].join("\n");

  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "proj_table" })
    });
  });
  await page.route("**/api/projects/proj_table/runs", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "run_table" })
    });
  });
  await page.route("**/api/runs/run_table/stream", async (route) => {
    const lines = [
      { run_id: "run_table", profile_id: "baseline", profile_label: "NoHarness", type: "created", sequence: 0 },
      { run_id: "run_table", profile_id: "baseline", profile_label: "NoHarness", type: "delta", text: markdown, sequence: 1 },
      { run_id: "run_table", profile_id: "baseline", profile_label: "NoHarness", type: "completed", sequence: 2 },
      { run_id: "run_table", profile_id: "harness", profile_label: "Harness", type: "created", sequence: 0 },
      { run_id: "run_table", profile_id: "harness", profile_label: "Harness", type: "delta", text: markdown, sequence: 1 },
      { run_id: "run_table", profile_id: "harness", profile_label: "Harness", type: "completed", sequence: 2 },
      { run_id: "run_table", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  await page.locator(".promptEditor").first().fill("table please");
  await page.getByRole("button", { name: "送出" }).click();

  const table = page.locator(".message.assistant table").first();
  await expect(table).toBeVisible();
  await expect(table.locator("th")).toHaveText(["支持先做 SSO", "反對先做 SSO"]);
  await expect(table.locator("td").first()).toHaveText("客戶 A 要求 SSO");
  await expect(page.locator(".message.assistant").first()).not.toContainText("|---|---|");
});

test("keeps long conversations inside the viewport and scrolls message lists", async ({ page }) => {
  const longText = Array.from({ length: 120 }, (_, index) => `第 ${index + 1} 行內容`).join("\n");

  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "proj_long" })
    });
  });
  await page.route("**/api/projects/proj_long/runs", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "run_long" })
    });
  });
  await page.route("**/api/runs/run_long/stream", async (route) => {
    const lines = [
      { run_id: "run_long", profile_id: "baseline", profile_label: "NoHarness", type: "created", sequence: 0 },
      { run_id: "run_long", profile_id: "baseline", profile_label: "NoHarness", type: "delta", text: longText, sequence: 1 },
      { run_id: "run_long", profile_id: "baseline", profile_label: "NoHarness", type: "completed", sequence: 2 },
      { run_id: "run_long", profile_id: "harness", profile_label: "Harness", type: "created", sequence: 0 },
      { run_id: "run_long", profile_id: "harness", profile_label: "Harness", type: "delta", text: longText, sequence: 1 },
      { run_id: "run_long", profile_id: "harness", profile_label: "Harness", type: "completed", sequence: 2 },
      { run_id: "run_long", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  await page.locator(".promptEditor").first().fill("long response");
  await page.getByRole("button", { name: "送出" }).click();
  await expect(page.getByText("第 120 行內容").first()).toBeVisible();

  const layout = await page.evaluate(() => {
    const root = document.getElementById("root") as HTMLElement;
    const shell = document.querySelector(".shell") as HTMLElement;
    const messageLists = Array.from(document.querySelectorAll(".messageList")) as HTMLElement[];
    return {
      viewportHeight: document.documentElement.clientHeight,
      bodyScrollHeight: document.body.scrollHeight,
      rootScrollHeight: root.scrollHeight,
      shellClientHeight: shell.clientHeight,
      shellScrollHeight: shell.scrollHeight,
      messageLists: messageLists.map((list) => ({
        clientHeight: list.clientHeight,
        scrollHeight: list.scrollHeight
      }))
    };
  });

  expect(layout.bodyScrollHeight).toBeLessThanOrEqual(layout.viewportHeight + 1);
  expect(layout.rootScrollHeight).toBeLessThanOrEqual(layout.viewportHeight + 1);
  expect(layout.shellScrollHeight).toBeLessThanOrEqual(layout.shellClientHeight + 1);
  expect(layout.messageLists.every((list) => list.scrollHeight > list.clientHeight)).toBe(true);
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
      { run_id: "run_history", profile_id: "baseline", profile_label: "NoHarness", type: "created", sequence: 0 },
      { run_id: "run_history", profile_id: "baseline", profile_label: "NoHarness", type: "delta", text: "baseline", sequence: 1 },
      { run_id: "run_history", profile_id: "baseline", profile_label: "NoHarness", type: "completed", sequence: 2 },
      { run_id: "run_history", profile_id: "harness", profile_label: "Harness", type: "created", sequence: 0 },
      { run_id: "run_history", profile_id: "harness", profile_label: "Harness", type: "delta", text: "harness", sequence: 1 },
      { run_id: "run_history", profile_id: "harness", profile_label: "Harness", type: "completed", sequence: 2 },
      { run_id: "run_history", type: "run_completed" }
    ];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: lines.map((line) => `data: ${JSON.stringify(line)}\n\n`).join("")
    });
  });

  await page.goto("/");
  await page.locator(".promptEditor").first().fill("這是一段會自動命名的歷史對話");
  await page.getByRole("button", { name: "送出" }).dblclick();

  await expect(page.getByText("baseline")).toBeVisible();
  expect(createdProjectName).toBe("這是一段會自動命名的歷史對話");
  expect(projects).toHaveLength(1);

  await page.getByRole("button", { name: "歷史" }).click();
  await expect(page.getByLabel("歷史對話紀錄")).toBeVisible();
  await expect(page.getByRole("button", { name: /這是一段會自動命名的歷史對話/ })).toBeVisible();
});

test("pauses a running streamed response", async ({ page }) => {
  await page.route("**/api/projects", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "proj_pause" })
    });
  });
  await page.route("**/api/projects/proj_pause/runs", async (route) => {
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({ id: "run_pause" })
    });
  });
  await page.route("**/api/runs/run_pause/stream", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 10_000));
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: ""
    });
  });

  await page.goto("/");
  await page.locator(".promptEditor").first().fill("pause this response");
  await page.getByRole("button", { name: "送出" }).click();
  await expect(page.getByRole("button", { name: "暫停執行" })).toBeVisible();
  await page.getByRole("button", { name: "暫停執行" }).click();
  await expect(page.getByRole("button", { name: "暫停執行" })).toHaveCount(0);
});

const analysisFixture = {
  schema_version: "2026-05-22.1",
  project_id: "proj_e2e",
  run_id: "run_e2e",
  turn_index: 0,
  generated_at: "2026-05-23T00:00:00+00:00",
  profiles: {
    baseline: {
      profile_id: "baseline",
      profile_label: "NoHarness",
      current_turn_usage: {
        input_tokens: 30,
        cached_tokens: 10,
        output_tokens: 12,
        reasoning_tokens: 0,
        total_tokens: 42,
        source: "provider_reported"
      },
      cumulative_usage: {
        input_tokens: 72,
        cached_tokens: 20,
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
    harness: {
      profile_id: "harness",
      profile_label: "Harness",
      current_turn_usage: {
        input_tokens: 35,
        cached_tokens: 15,
        output_tokens: 15,
        reasoning_tokens: 0,
        total_tokens: 50,
        source: "provider_reported"
      },
      cumulative_usage: {
        input_tokens: 85,
        cached_tokens: 30,
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
      enabled_harness_modules: ["context_summary"],
      provider_context_keys: ["instructions", "prompt"]
    }
  },
  comparison: {
    total_token_delta: 8,
    input_token_delta: 5,
    output_token_delta: 3,
    reasoning_token_delta: 0,
    controlled_profile_extra_sections: ["behavior_preferences"]
  },
  notes: []
};
