# HarnessDiff Product Spec

## 目標

HarnessDiff 是一個本機教學工作台，用同一個任務並排比較「無 Harness」與「有 Harness」的 Chat 回應差異，協助教學與示範 Harness Engineering 的價值。

目前只實作 Chat 版本。Workflow、Agent、MultiAgents 是保留的 surface type。

## 目標使用者

- Harness Engineering 教學者
- 想觀察 prompt / context / guardrail / output contract 差異的開發者
- 需要用實際 token 與上下文結構展示差異的 demo 製作者

## 核心體驗

1. 使用者進入 localhost web app。
2. 左側是 `NoHarness`，右側是 `Harness`。
3. 第一回合預設使用「整合單一輸入」，同一 prompt 一鍵送到兩側。
4. 回合完成後，輸入模式可切為左右獨立，因為兩側上下文可能逐步分歧。
5. 兩側 provider task 在 backend 使用獨立 async task 執行。
6. 每回合輸入、輸出、事件、usage 與 analysis 都保存在本機 JSON。
7. 分析列顯示本回合與累計 token/context 差異。

## Chat Surface Scope

已完成：

- dual-pane Chat UI
- integrated / independent input mode
- attachment preview UI
- image attachments sent to OpenAI Responses API vision input
- press-and-hold voice input
- model and reasoning effort controls
- Harness module settings disclosure
- OpenAI Responses API streaming
- local JSON storage
- deterministic token/context analysis
- desktop/mobile Playwright smoke and regression tests

未完成或保留：

- real file upload to provider
- non-image binary file upload to provider
- replaying full stored conversation history into provider context
- Workflow / Agent / MultiAgents surfaces
- external database
- multi-user auth

## Context Model

HarnessDiff tracks these conceptual context sections:

- system prompt / instructions
- tool definitions
- behavior preferences
- personal memory
- current user turn
- stored conversation history

Stage 5 analysis distinguishes between:

- context actually sent to provider: current `instructions` and `prompt`
- context stored locally but not yet sent: prior input/output artifacts

## Harness Modules

Current Harness modules:

- `context_summary`
- `source_map`
- `guardrails`
- `output_contract`
- `planning_preamble`
- `tool_policy`
- `memory_selection`
- `post_answer_critique`
- `token_budgeter`

Project default config lives at:

```text
data/projects/{project_id}/config/harness.default.json
```

Per-run overrides are saved on `run.json` and repeated in `Harness/input.json`.

## Token Analysis Policy

Provider-reported usage is the source of truth for:

- input tokens
- output tokens
- reasoning tokens
- total tokens

Context section estimated tokens are derived from saved character counts. They are for structural comparison only and must not be treated as billing numbers.

## Failure Policy

If any pane provider task fails:

- the failing pane writes an error event
- `run.json` status becomes `failed`
- SSE emits `run_failed`
- analysis is not generated

This avoids presenting partial output as a complete comparison.

## Release Readiness Criteria

The Chat MVP is considered ready for a local GitHub handoff when:

- README quick start works
- backend tests pass
- frontend TypeScript, Vitest, Vite build, and Playwright pass
- local JSON artifacts are documented
- OpenAI live streaming has been verified with a local key
- known limitations are documented
