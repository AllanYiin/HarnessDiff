# HarnessDiff Requirements

## 功能範圍

- 以 localhost web app 形式提供 HarnessDiff Chat / Agent workbench。
- 左側 `NoHarness` 使用 baseline instructions；右側 `Harness` 套用可開關 Harness modules。
- 支援 OpenAI Responses API streaming。
- 支援 PNG/JPEG/WEBP/GIF 圖片附件進入 OpenAI Responses API vision input；非圖片附件目前仍以 prompt metadata/文字摘要進入上下文。
- 前端與測試不得用假串流、route fixture 或 mock 成功回應掩蓋 backend/API/provider 契約失敗；測試替身只可用於隔離外部不可控依賴，且不得取代整合驗證。
- 支援本機 JSON 保存 project/run/input/output/events/usage/analysis。
- 支援 deterministic current-turn 與 cumulative token/context analysis。
- 支援一鍵安裝啟動：`run_app.bat`、`run_app.command`、`run_app.sh`。
- 支援新對話、歷史對話紀錄檢視、自動對話命名與暫停執行。
- 支援 independent mode 中各 pane 獨立送出與串流；單一 pane 執行中不得鎖住另一個 pane。
- 支援 TopBar surface segmented control 在 Chat / Agent 間切換；執行中不得切換，需先完成或取消前景串流。
- Agent mode 第一版以 `NoHarness Agent` vs `Harness Agent` 比較同一任務，支援前景 streaming、可取消、artifact 可追溯。
- Agent mode 不支援背景續跑、durable checkpoint、跨重啟 resume 或任務排程。
- Harness pane 啟用 `source_map` 與 `tool_policy` 且使用 web tools 時，web tool output 必須把可引用 URL 帶入最終回答合成脈絡，讓 web-supported claims 可產生 inline Markdown links 與簡短 `Sources` 區塊。
- Harness pane 啟用 `tool_policy` 時，必須可使用 container-based code interpreter，在暫存 repo 副本中以 Docker 執行 Python、Node.js、pnpm、React/Vite、測試與 build 命令；NoHarness 不得取得此工具。
- Harness Agent 啟用 `tool_policy` 時，必須可使用 shell/container/code tools、`harness.subagent.run` 與 `multi_tool_use.parallel`；NoHarness Agent 不得取得這些高風險或 Harness 專屬工具。
- Harness pane 啟用 `consequence_gate` 時，凡 prompt 看起來會產生對外發布、社群貼文、公告、行銷活動或客戶可見內容，必須在 provider 前產生 Consequence Gate preflight decision，記錄缺失情境、required scanner coverage gap、scanner finding、similarity match、claim evidence gap、offer disclosure gap、provenance/rights finding 與 gap、rollback readiness gap、潛在誤讀與審查需求；NoHarness 不得套用此 gate。
- Consequence Gate 不得以品牌、國家事件或敏感詞黑名單作為主防線；HarnessDiff core 不得新增 OCR/CV/embedding 重依賴，只能接收或產生結構化 preflight/scanner adapter findings；相似度與來源追溯以 `similarity.match`、`provenance.review` 類 finding contract 呈現。
- 自動建立 `~/.harnessdiff`、`CLAUDE.md`、`AGENTS.md`、`agents.md` 與 `skills/`；技能可由 UI 檢視與匯入 `.zip`、`.skill`/Markdown 單檔或資料夾。
- 開啟新對話後的第一個 run 必須將已安裝技能第一層清單放入 provider 上文，內容限 `name` 與 `description`，完整 `SKILL.md` 僅在使用者選取或匯入時漸進式揭露。
- 對話輸入框支援技能 slash command：輸入 `/` 顯示已安裝技能候選，插入或手打 `/skill-id` 後送出，該 run 必須載入對應完整 `SKILL.md` 作為本回合技能上下文。

## 輸入與輸出

輸入：

- 使用者 chat prompt
- model
- reasoning effort
- input mode：`integrated` / `independent`
- target panes：`NoHarness` / `Harness`
- per-run `harness_modules`
- supported image attachments
- installed skills first-layer context on a new conversation's first run

輸出：

- 左右 pane streaming assistant response
- per-pane JSON artifacts
- `analysis/analysis.json`
- frontend analysis summary metrics
- Harness pane risk preflight chips for consequence findings
- conversation history list and transcript reconstruction
- logs under `logs/` during launcher runs
- user-level skill files under `~/.harnessdiff/skills`
- Agent `steps.jsonl`、subagent artifacts 與 `analysis/agent-analysis.json`

## UI / 互動

Primary task: compare one chat task across `NoHarness` and `Harness`.

Agent primary task: compare one agent task across `NoHarness Agent` and `Harness Agent`.

Task model:

- primary: submit prompt and compare two streamed responses
- secondary: start a new conversation, inspect history, adjust model/reasoning/Harness modules, inspect/import skills
- low-frequency: inspect local artifacts and docs
- rare: package release ZIP

State model:

- empty: no run yet; composer prompts first integrated send
- drafting: user edits integrated or independent prompt
- streaming: one or both panes receive deltas
- independent streaming: one pane can keep running while another pane remains editable/submittable
- paused: user cancelled the active fetch/stream and panes stop receiving deltas
- resolved: run completed and analysis is available
- blocked: provider or API error occurred
- agent running: foreground Agent SSE is active; final text and step trace update incrementally
- agent cancelled: user aborts foreground stream; partial output and trace remain available, but no full comparison is presented

Information-role classification:

- `action-critical`: composer, send buttons, target panes
- `decision-supporting`: model, reasoning effort, Harness toggles
- `status-feedback`: analysis summary, streaming state
- `reference`: docs, specs, storage/API details, historical conversation list
- `exception-handling`: run failed, provider error, corrupt JSON
- `audit/history`: local JSON artifacts, DEVNOTE

Content audit:

| Content | Category | Visibility |
|---|---|---|
| dual chat panes | must-see-now | main workspace |
| composer | must-see-now | bottom |
| model/reasoning controls | must-see-now | top bar |
| new conversation / history actions | next-step-only | top bar buttons |
| Harness module toggles | next-step-only | settings disclosure |
| token/context metrics | status-feedback | compact analysis strip |
| history conversation list | on-demand-reference | history drawer |
| API/storage reference | on-demand-reference | docs |
| corrupt JSON details | error-only | API response / troubleshooting |
| historical artifacts | keep-off-first-viewport | local files / future inspector |

Deferred blocks:

| Block | hidden_now_because | reveal_trigger | container |
|---|---|---|---|
| Harness module list | not needed for every prompt | click settings button | popover disclosure |
| history conversation list | not needed during focused comparison | click history button | drawer |
| API reference | not needed for normal chat comparison | user opens docs | Markdown doc |
| raw JSON artifacts | audit/history only | developer inspects local data | filesystem |
| troubleshooting | exception only | failure or release verification | Markdown doc |

## 資料保存

- Runtime data root: `data/projects`
- Project config: `config/harness.default.json`
- Run artifacts: `run.json`, `{pane}/input.json`, `{pane}/output.json`, `{pane}/events.jsonl`, `{pane}/usage.json`
- Analysis artifact: `analysis/analysis.json`
- Agent trace artifacts: `{profile_id}/steps.jsonl`, `{profile_id}/subagents/{subagent_id}/...`, `analysis/agent-analysis.json`
- Project metadata acts as conversation metadata; project name is auto-generated from the first prompt unless the user created an empty new conversation.
- Transcript retrieval reconstructs UI messages from `run.json` plus pane `output.json`.
- Launcher runtime metadata: `.runtime/ports.json`, `.runtime/launcher_state.json`
- Launcher logs: `logs/launcher.log`, `logs/backend.log`, `logs/frontend.log`

## 外部依賴

- Python 3.10+
- Node.js 22+
- Corepack/pnpm
- Docker for container code execution
- OpenAI API key for live streaming

## 使用情境判定

`project_profile`:

- `user_type`: `small_team`
- `usage_duration`: `long_term`
- `change_frequency`: `occasional`
- `failure_cost`: `multi_user_disruption`

Decision result: `scene_b_shared_tool`.

Reason: this is a shared teaching/demo tool that should be low-friction and stable, but it is not yet a formal internal workflow blocker.

## APSM 技術選型

- `archetype`: `web_app`
- `architecture`: `separated`
- `frontend`: `node_spa`
- `backend`: `python_api`
- `layout_variant`: `apps`

## 驗收條件

- `python scripts/apsm_validate.py --project .` passes.
- `run_app.bat`, `run_app.command`, and `run_app.sh` exist and are generated by `scripts/project_launcher.py`.
- `python -m pytest` passes.
- frontend TypeScript, Vitest, Vite build, and Playwright pass.
- Playwright verifies history auto naming, Markdown rendering/copy, and pause execution.
- Playwright verifies independent pane submission remains available while another pane is running.
- Agent runtime tests verify streaming, trace persistence, analysis artifact, transcript reconstruction, and Harness-only tool access.
- Playwright backend-contract coverage must use the real local backend or an explicitly labeled fixture-only test that is not counted as backend integration.
- README documents one-click startup and troubleshooting.
- Generated runtime data/logs are not committed.

