# DEVNOTE — HarnessDiff

> 累加式開發筆記，取代 `/compact`。
> **檔頂 SNAPSHOT**：當前最新狀態（覆寫式，想知道「現在」就看這裡）。
> **檔尾 HISTORY**：時間順序的歷史區塊（累加式，想知道「為什麼」就往下讀）。

---

## 📌 SNAPSHOT — 當前狀態
<!-- 這一整段每次 /devnote 會被覆寫，只反映「到目前為止的最新狀態」 -->

**最後更新**：2026-06-05 23:29

### 需求狀態
- [x] Stage 0：localhost web app / FastAPI skeleton、README、env 樣板、storage/provider docs。
- [x] Stage 1：本機 JSON project CRUD、schema version、atomic write、corrupt JSON repair report。
- [x] Stage 2：雙 Pane Chat UI、整合/個別輸入模式、附件預覽、附件讀取摘要、語音輸入、mock streaming、Playwright desktop/mobile 視覺 smoke。
- [x] Stage 3：OpenAI Responses API streaming provider、tool/function-call round loop、run orchestration、SSE routes、前端串接已通過 fake provider、default model live provider、雙 pane route/SSE live 驗證。
- [x] Stage 4：Harness Engine 與組態開關第一版完成；project config、run-level overrides、Harness-only instructions、UI toggles、input artifact traceability 均已接上。
- [x] Stage 5：本回合與累計分析器第一版完成；analysis artifact、SSE `analysis_ready`、API retrieval、前端 summary metrics、current/cumulative usage 與 context sections 均已接上。
- [x] Stage 6：整合/回歸/邊界測試完成；provider failure、invalid ids、lazy analysis rebuild、single-pane analysis、settings disclosure、analysis_ready e2e 均已納入。
- [x] Stage 7：文件化與交付完成；README quick start、API reference、troubleshooting、specs/product-spec、specs/stage-plan、release checklist 與 docs audit 均已收尾。
- [x] 一鍵安裝啟動機制：依 `vibe-coding-guidelines` 補 `project.config.json`、`AGENTS.md`、`specs/requirements.md`、`todo.md`、launcher generator、APSM validator、`run_app.*` 與 runtime metadata。
- [x] Conversation controls：新增新對話、歷史對話 drawer、自動命名、transcript API、暫停執行，以及 Markdown render/copy raw Markdown。
- [x] Harness tools：`tool_policy` profile 會取得 ToolAnything 標準 web/fs/data/read-only shell tools 與 `harness.subagent.run`；OpenAI provider 會執行 function calls 並把 outputs 回塞續跑。
- [x] Web source citations：Harness web tool output 會自動帶 `citation_sources` / `citation_guidance`，`source_map` 指令要求 inline Markdown links 與 `Sources` 區塊。
- [x] Composer input：迴紋針整合檔案/圖片匯入；支援 Ctrl+V 貼上檔案、txt/md 讀文字、csv 產生 DataFrame-style preview、Office/PDF metadata 摘要、圖片 browser preview、麥克風 Web Speech API 轉文字。
- [x] Skill system：啟動/技能 API 會建立 `~/.harnessdiff`、`CLAUDE.md`、`AGENTS.md`、`agents.md`、`skills/`；UI 可檢視技能、匯入 zip/skill/folder、逐步揭露完整 `SKILL.md`。
- [x] Skill context：新對話第一回合自動放入已安裝技能第一層 `name/description`；輸入框支援 `/skill-id` slash command，送出時載入對應完整 `SKILL.md` 作為本回合上下文。
- [x] Skill pane independence：NoHarness/Harness skill selection 已從 run-level 改成 profile-level；NoHarness 採 LLM-only，Harness 保留 LLM + deterministic fallback，Agent surface 同步套用。
- [x] Debug reporting handoff：已用 `/prompts:debug_report skill兩個pane未獨立` 產出 `debugs/2026-06-05_skill_two_pane_not_independent_debug_report.md` 與 archive README。
- [x] Vision input：PNG/JPEG/WEBP/GIF 圖片附件會以 base64 data URL 傳入 OpenAI Responses API `input_image`，兩側 profile 都能真正讀圖。
- [x] Voice input UX：麥克風改成按下即開始、放開/取消自動停止，並支援 Space/Enter 鍵盤按住行為。
- [x] Skill slash token UI：Composer 內已安裝 skill slash command 會顯示成 teal chip，`contenteditable=false`，Backspace/Delete 會整塊刪除。
- [x] Harness consequence gate：Harness pane 新增 `consequence_gate` module；對外發布/社群/公告/行銷/客戶可見 prompt 會在 provider 前產生 Consequence Gate preflight `harness_decision`，記錄缺失情境、風險假設與審查需求，NoHarness 不套用。
- [x] Publishing risk harness preview：`consequence_gate` 進一步記錄 required scanner coverage gaps、scanner findings、similarity matches、claim evidence gaps、offer disclosure gaps、provenance/rights findings/gaps、rollback readiness gaps；分析列會顯示 Harness risk chips，NoHarness 仍維持 baseline。
- [ ] User message image rendering：使用者訊息 bubble 顯示圖片縮圖的程式已加入，但本次 `/devnote` 前尚未完成 TypeScript / Vitest / Playwright 驗證。

### 未解問題
- 本機 `npm` shim 壞掉，已改用 Corepack pnpm 的實際路徑或 `corepack pnpm`。
- Office/PDF 深度文字抽取、CSV 真正 pandas DataFrame、非圖片 binary provider upload 仍未實作；若要完整解析需新增後端 upload/parse endpoint。
- Web Speech API 瀏覽器支援不一致，且會受麥克風權限影響；目前以前端 Web Speech API + Playwright mock 驗證互動。
- 新的 contenteditable prompt editor 取代 textarea；後續測試或 selector 不應再假設 composer 是 `textarea`。
- HarnessDiff 目前沒有實作 Codex custom prompts subsystem：`~/.codex/prompts/*.md` 在官方 Codex CLI/IDE extension 可用 `/prompts:name` 明確呼叫，但本 repo 前端 slash menu 只支援 skills，後端 `SkillStore` 也未掃 `~/.codex/prompts`。
- 工作樹仍混有本次 skill-pane 修正以外的未提交變更：`pdf_attachments.py`、`styles.css`、`tests/api/test_tool_runtime.py`、`tests/api/test_runs.py` 內 PDF surrogate 測試片段與三張 `skill-panel-*.png`，不可未確認就清理或回退。

### 關鍵技術決策（當前有效）
> 歷史上做過的、目前仍然成立的決策摘要。被推翻的決策不列。
- **Repo root**：GitHub 上傳目錄是 `D:\PycharmProjects\HarnessDiff\github_repo`，外層殘留已刪除（詳見 HISTORY `[2026-05-22 23:37]`）。
- **Storage source of truth**：MVP 以本機 JSON 為準，保留 `schema_version` 與 repair report。
- **Provider boundary**：第一版只接 OpenAI Responses API，但必須經 provider adapter，避免 route 直接綁死 OpenAI。
- **Streaming first**：所有 LLM 輸出必須 streaming；Responses API 需處理 semantic events，如 `response.output_text.delta`、`response.completed`、`error`。
- **API-first fallback**：前端送出會先呼叫 FastAPI run endpoint；若後端未啟動或 API 失敗，才 fallback 到既有 mock streaming，讓 Stage 2 e2e 不需後端也能通過。
- **Harness Engine boundary**：Harness 技巧只在 `context_builder` 轉成 Harness pane instructions；provider 只看最終 `LLMRequest`，不理解 Harness 模組細節。
- **Deterministic analysis**：Stage 5 分析器只讀本機 JSON artifacts，不呼叫 LLM；provider usage 是 token 真實來源，context section token 只是字元數估算。
- **Failed run semantics**：任一 pane provider error 時 run 會標記 `failed`、送出 `run_failed`，不產生 analysis，避免 partial output 被誤認為完整比較。
- **Documentation handoff**：Stage 7 文件分工為 README 入口、`docs/` 操作/參考、`specs/` 規格/階段驗收、`DEVNOTE.md` session handoff。
- **Stage 2 visual gate**：獨立 Playwright Chromium 已取代 Codex in-app browser 截圖，desktop/mobile e2e 會輸出 screenshots。
- **One-click launcher boundary**：`run_app.bat` / `run_app.command` / `run_app.sh` 皆由 `scripts/project_launcher.py` 生成；若啟動行為要改，先改 generator 再重產 wrapper。
- **APSM source of truth**：`project.config.json` 宣告 `scene_b_shared_tool` + `web_app/separated/node_spa/python_api`，並以 `layout_variant=apps` 對齊既有 `apps/api`、`apps/web` 目錄。
- **Project as conversation**：Chat MVP 不另建 conversation storage；Project metadata 是對話 metadata，runs/pane outputs 是 transcript 來源。
- **Harness tool loop**：只有啟用 `tool_policy` 的 profile 會拿到 tools；provider 負責 function-call loop，route/orchestrator 保持 provider-neutral（詳見 HISTORY `[2026-05-25 06:37]`）。
- **Web citation enrichment**：來源引用不改 API/schema，改在 web function output 回塞時附加 `citation_sources` 與 citation guidance（詳見 HISTORY `[2026-05-25 06:37]`）。
- **Attachment context first**：附件目前不新增後端 binary upload schema；前端先將可讀摘要併入 prompt，保留後端解析擴充點（詳見 HISTORY `[2026-05-25 06:37]`）。
- **User-level skill home**：技能存放在 `~/.harnessdiff/skills`，可用 `HARNESSDIFF_HOME` 覆寫；新對話只自動放第一層清單，完整 `SKILL.md` 只在 UI 選取或 slash command 時載入（詳見 HISTORY `[2026-05-25 06:37]`）。
- **Skill imports use JSON base64**：zip/skill/folder 匯入走 JSON base64，避免新增 multipart 依賴；zip/folder import 必須 path traversal 防護（詳見 HISTORY `[2026-05-25 06:37]`）。
- **Responses vision input**：支援圖片附件時，前端產生 data URL，後端以 provider-neutral `LLMImageAttachment` 傳給 OpenAI Responses `input_image`（詳見 HISTORY `[2026-05-25 22:21]`）。
- **Press-and-hold voice input**：語音輸入控制採 Pointer Events + pointer capture，按下開始、放開/取消停止；鍵盤 Space/Enter 同步支援（詳見 HISTORY `[2026-05-25 22:21]`）。
- **Skill command as atomic token**：Composer 由 textarea 改為 ARIA `textbox` contenteditable，已安裝 `/skill-id` 渲染為不可編輯 chip，但送出 payload 仍是普通文字（詳見 HISTORY `[2026-05-25 22:21]`）。
- **Message attachments are display-only**：對話 bubble 圖片顯示使用 `Message.attachments`，不改 provider prompt；provider input 和 UI preview 是兩條資料路徑（詳見 HISTORY `[2026-05-25 22:21]`）。
- **Consequence Gate 只作用於 Harness pane**：`consequence_gate` 由 `context_builder` 轉成 Harness instructions，並由 `HarnessableControlPlane` 在 provider 前對 publication-like prompt 記錄 `FINAL_OUTPUT_PROPOSED` preflight decision；NoHarness 保持 baseline（詳見 HISTORY `[2026-05-28 19:48]`）。
- **Publishing risk preview 不做 production 黑名單**：HarnessDiff 只在 Harness pane provider 前產生 preview `harness_decision` 與 UI chips；scanner coverage、similarity/provenance finding、claim/offer/rollback 都走結構化 finding，不在 core 內建 OCR/CV/embedding 或特定事故黑名單（詳見 HISTORY `[2026-05-28 21:12]`）。
- **Skill routing 以 profile 為 state boundary**：integrated run 可以共享 prompt/attachments/run artifact，但 skill selection、skill invocation、tool availability、AGENTS context 與 fallback policy 必須以 profile/pane 為界（詳見 HISTORY `[2026-06-05 23:29]`）。
- **Codex custom prompts 不混入 skills**：`~/.codex/prompts` 是官方 Codex CLI/IDE extension 的 deprecated slash-command surface；若 HarnessDiff 要支援，應新增 PromptStore/API/frontend namespace，不要硬塞進 `SkillStore`（詳見 HISTORY `[2026-06-05 23:29]`）。

### 已知地雷（仍需注意）
> 踩過且未來仍可能重踩的坑的一句話提醒。已徹底不可能重現的不列。
- **Codex Browser 截圖 timeout**：in-app browser 的 `Page.captureScreenshot` 曾 timeout；視覺驗證改用獨立 Playwright Chromium。
- **Mobile overflow**：Playwright 曾抓到 393px viewport 下 14px horizontal overflow；已用 global `box-sizing` 與 mobile controls 收縮修正。
- **Vitest / Playwright 掃檔衝突**：Vitest 必須限定 `src`，否則會把 `e2e/*.spec.ts` 當 Vitest 測試。
- **Sandbox 啟動 Chromium**：Playwright Chromium 在 sandbox 內會 `spawn EPERM`；本機驗證需 escalated 執行。
- **E2E proxy ECONNREFUSED**：只有 Vite 前端啟動、FastAPI 未啟動時，Playwright 會看到 `/api/projects` proxy error；目前是預期 fallback 行為，不代表 UI smoke 失敗。
- **OpenAI stream helper 參數**：`client.responses.stream(...)` 不接受 `stream=True`；只有 `responses.create(..., stream=True)` 需要該參數。
- **SDK raw event 序列化**：OpenAI SDK event 的 `model_dump()` 可能在本機環境丟 TypeError；raw artifact logging 必須容錯降級。
- **Frontend-design audit scripts missing**：此 repo 目前沒有 `audit:frontend-runtime` 或 `audit_frontend_principles.py`；UI gate 暫以獨立 Playwright desktop/mobile 替代。
- **PowerShell 文字讀寫**：讀寫文字檔需顯式 `-Encoding UTF8`，不可裸用 `Get-Content` / `Set-Content`。
- **Launcher install 需網路**：`project_launcher.py --ensure-only` 會安裝 Python/Node 依賴；在 Codex sandbox 內可能因網路被擋，需要 escalated 執行。
- **Windows launcher 前端路徑**：曾產生相對路徑二次 `cd apps\web` 的風險；目前 generator 已改用 `%~dp0apps\web` 絕對路徑。
- **Windows cmd quoting**：`cmd /k """%PYEXE%"" ..."` 會把 venv `python.exe` 誤當 Python 腳本讀入；Windows launcher 目前改用 `scripts\launch_backend.bat` / `scripts\launch_frontend.bat` helper，避免巢狀 `cmd /k` 引號。
- **E2E backend leakage**：若本機 8000 有真實 backend，原本 fallback smoke 會拿到 live output；離線 smoke 需明確 abort `/api/**`。
- **PowerShell `date` alias**：`date "+%Y-%m-%d %H:%M"` 在 PowerShell 會被當成 `Get-Date -Date` 而失敗；用 `Get-Date -Format "yyyy-MM-dd HH:mm"`。
- **compileall / tsbuildinfo sandbox writes**：預設 `__pycache__`、`C:\tmp`、`apps/web/tsconfig.tsbuildinfo` 或 Vite temp 寫入可能被 sandbox 擋；Python 可用 repo 內 `.compile_pycache`，前端檢查通常需 escalated。
- **Import-time home writes**：`app = create_app()` 不可在 import 階段立即寫 `~/.harnessdiff`，否則測試 collection 會因 sandbox 權限炸掉；home 初始化需 lazy ensure。
- **Zip/folder skill import path traversal**：匯入相對路徑不可信任，必須拒絕絕對路徑、空 path parts 與 `..`。
- **Prompt editor selector change**：Composer 不再是 `textarea`，e2e 與 UI 操作要改用 `.promptEditor` 或 ARIA textbox。
- **Blob URL lifecycle**：送出後 `clearAttachments()` 會 revoke browser `blob:` URL；需要在對話中持續顯示圖片時，必須先複製 `dataUrl` 到 display-only message attachment。
- **Skill selection regression risk**：看到 NoHarness/Harness skill 又完全相同時，先查是否有人把 `_select_skills_for_profile(run, profile)` 移回 run 外層，或讓 deterministic fallback 套到 baseline。
- **Pytest log write sandbox**：`python -m pytest` collection 可能因 `toolanything` 初始化寫 `logs/toolanything.log` 被 sandbox 擋住；必要時按 policy 升權重跑測試。
- **Custom prompts invocation mismatch**：官方 Codex prompts 呼叫格式是 `/prompts:name` 且需 restart/new chat；在 HarnessDiff 目前不會載入，`/debug_report`、`/devnote` 也不會自動展開。

---

# 📜 HISTORY

---

## [2026-05-22 23:37] 首次建立開發筆記

### 本次做了什麼（增量）
建立 `DEVNOTE.md`，把目前 repo 狀態、Stage 0-2 完成狀態、Stage 3 待辦、已知工具鏈地雷與目前有效技術決策整理成可接手快照。

### 本次重大技術決策
- **用 DEVNOTE 取代黑箱 compact**
  - 內容：在 repo root 建立覆寫式 SNAPSHOT + 累加式 HISTORY。
  - 理由：讓下一個 session 能直接讀取可維護筆記，而不是依賴對話壓縮。
  - 影響：後續重大開發節點應更新此檔。

### 本次失敗經驗與填坑
- （本次無新增；此區回填已知歷史地雷。）

### 備註
- 使用者貼入 `/devnote` 規則後，本檔以首次建立模式產生。

---

## [2026-05-22 23:46] Stage 3 streaming slice

### 本次做了什麼（增量）
補上 Stage 3 的 backend/frontend 串接骨架：新增 OpenAI Responses provider adapter、run document schema、run orchestration、SSE streaming route、本機 JSON run artifacts，以及前端 API-first streaming 串接。測試補上 fake provider 的端到端 run streaming、OpenAI provider 缺少 API key 的錯誤路徑、TypeScript build、Vitest、Vite build 與 Playwright desktop/mobile smoke。

### 本次重大技術決策
- **Provider adapter 先行**
  - 內容：route 只依賴 `LLMProvider` 介面，OpenAI Responses 實作放在 `providers/openai_responses.py`。
  - 理由：目前指定 OpenAI Responses API，但未來一定會擴充 provider；直接把 SDK 寫進 route 會讓 Stage 4 以後難以演進。
  - 影響：新增 provider 時要實作 `stream(request)` 並輸出統一 `ProviderEvent`。
- **Run artifacts 以 pane 分層保存**
  - 內容：每次 run 會在 `data/projects/{project_id}/runs/{run_id}/{Harness|NoHarness}/` 保存 `input.json`、`events.jsonl`、`output.json`、`usage.json`。
  - 理由：Harness 與 NoHarness 需要完整上下文、輸入輸出與 token 分析分開追蹤，之後才能做回合與累計分析。
  - 影響：Stage 5 分析器應優先讀這些 artifact，不要重新從 UI 狀態推測。
- **Stage 3 不直接進 Stage 4**
  - 內容：雖然 fake provider 與 SDK shape 檢查通過，但尚未用真實 `OPENAI_API_KEY` 驗證 live streaming。
  - 理由：使用者要求檢查階段是否完成；live OpenAI streaming 是 Stage 3 的核心風險，未驗證前不應宣稱完全完成。
  - 影響：下一步應先提供 API key 後跑 backend + frontend live smoke，再決定進 Stage 4。

### 本次失敗經驗與填坑
- **Playwright 前端 smoke 會觸發 Vite proxy error**
  - 試過無效：只跑前端 dev server 時，`/api/projects` 仍會嘗試 proxy 到 FastAPI。
  - 最終解法：保留 API-first，但在前端 catch API 失敗後 fallback 到 mock streaming，讓 UI e2e 與後端 live 測試解耦。
  - 根因：Stage 2 的視覺 smoke 驗證 UI 可用性，不應被 Stage 3 後端是否啟動綁死。

### 備註
- 驗證結果：`python -m pytest`、`python -m compileall apps\api`、TypeScript build、Vitest、Vite build、Playwright desktop/mobile 均已通過。

## [2026-05-23 02:19] Stage 6 regression and boundary tests

### 本次做了什麼（增量）
完成 Stage 6 測試防線。後端新增 provider 單 pane 失敗、invalid/missing run id、analysis lazy rebuild、single-pane analysis 邊界測試；前端 Playwright 新增 Harness settings disclosure/toggle overflow 回歸，以及 mock SSE `analysis_ready` metrics 渲染測試。文件同步補上 `run_failed` 行為與 Stage 6 regression boundary。

### 本次重大技術決策
- **provider failure 不再標記 completed**
  - 內容：若任一 pane provider error，`RunOrchestrator` 寫入 error event、標記 run `failed`、送出 `run_failed`，並跳過 analysis 產生。
  - 理由：部分 pane 成功不等於比較完成；若仍標記 completed，Stage 5 分析會誤導教學判讀。
  - 影響：前端型別新增 `run_failed` event；未來 UI 可針對 failed run 做更明確的錯誤恢復。
- **Stage 6 優先測邊界，不新增功能**
  - 內容：本階段只補回歸和邊界測試，以及必要的失敗狀態語意修正。
  - 理由：Stage 7 前需要先穩定已完成功能，不應在測試階段擴大產品範圍。
  - 影響：下一階段可聚焦文件化與交付，而不是繼續補底層風險。

### 本次失敗經驗與填坑
- **partial provider success 的狀態語意不完整**
  - 試過無效：原本所有 pane task 結束後直接標記 completed，即使其中一側 error。
  - 最終解法：收集 pane errors；有錯就 `failed` + `run_failed` + 不寫 analysis。
  - 根因：async task lifecycle 的「都結束」不等於業務語意的「比較完成」。

### 備註
- 驗證結果：`python -m pytest` 13 passed、`python -m compileall apps\api`、TypeScript build、Vitest、Vite build、Playwright desktop/mobile 4 tests 均已通過。

---

## [2026-05-23 02:25] Stage 7 documentation handoff

### 本次做了什麼（增量）
完成 Stage 7 文件化與交付收尾。README 改成可執行 quick start 與 docs map；新增 `docs/api-reference.md`、`docs/troubleshooting.md`、`specs/product-spec.md`、`specs/stage-plan.md`；更新 architecture、release checklist、CHANGELOG 與 DEVNOTE。先前 `specs/` 未建立的缺口已排除。

### 本次重大技術決策
- **文件分層，不把所有內容塞進 README**
  - 內容：README 只做 overview、quick start、verification、docs map；API/storage/provider/troubleshooting/spec 分別放到對應文件。
  - 理由：README 要讓新讀者快速成功一次，reference 細節留在可查詢文件中。
  - 影響：後續更新 endpoint 或 storage schema 時，優先改 `docs/api-reference.md` / `docs/storage-format.md`，README 只保留入口。
- **specs 作為產品與階段驗收真相來源**
  - 內容：`specs/product-spec.md` 記錄 Chat MVP 產品範圍；`specs/stage-plan.md` 記錄 Stage 0-7 驗收狀態。
  - 理由：符合先前使用者要求把規格章節切到 `github_repo/specs`，也讓 release handoff 更清楚。
  - 影響：未來 Workflow/Agent/MultiAgents 應先更新 specs，再進實作。

### 本次失敗經驗與填坑
- **README audit 初次分數不足**
  - 試過無效：以 README 內容直接跑 technical doc audit，缺少明確 `overview` signal。
  - 最終解法：補 `Overview` heading；README audit 達 100/100。
  - 根因：文件內容可讀不代表符合 automated doc quality gate 的結構訊號。

### 備註
- 文件 audit：README `readme` 100/100、API reference `reference` 100/100、troubleshooting `runbook` 100/100。
- 驗證結果：`python -m pytest` 13 passed、`python -m compileall apps\api`、TypeScript build、Vitest、Vite build、Playwright desktop/mobile 4 tests 均已通過。
- 尚未驗證：真實 OpenAI Responses API streaming，因本機未提供 `OPENAI_API_KEY`。

---

## [2026-05-23 00:01] Stage 3 live 驗證與 Stage 4 Harness Engine

### 本次做了什麼（增量）
使用本機 `OPENAI_API_KEY` 跑通 OpenAI Responses API streaming live smoke，並補齊 Stage 4 第一版 Harness Engine。現在 project config 的 `harness.default.json` 會在 run 建立時與 UI/API overrides 合併，effective `harness_modules` 會保存到 `run.json`，Harness pane 的 `input.json` 會保存最終 instructions 與模組狀態，NoHarness 仍維持 baseline instruction。

### 本次重大技術決策
- **Harness 模組不進 provider**
  - 內容：Harness 技巧在 `context_builder.build_instructions()` 轉成 instructions；provider adapter 只處理 provider-neutral `LLMRequest`。
  - 理由：保持 provider 可替換，避免 OpenAI provider 直接理解 Harness 概念。
  - 影響：後續 Stage 5 分析器可讀 run/input artifacts 還原「當回合用了哪些 Harness 技巧」。
- **run-level overrides 覆蓋 project config**
  - 內容：`config/harness.default.json` 是預設值，前端逐項開關送出 `harness_modules` 作為當回合 overrides。
  - 理由：符合使用者「可逐項開關，也可透過組態檔切換」的要求。
  - 影響：修改 config 檔會影響新 run；既有 run 因已保存 effective modules，不受後續 config 漂移影響。

### 本次失敗經驗與填坑
- **OpenAI stream helper 不接受 `stream=True`**
  - 試過無效：`client.responses.stream(**kwargs)` 內仍帶 `stream=True`，SDK 回 `unexpected keyword argument 'stream'`。
  - 最終解法：把 stream kwargs 集中到 `_build_stream_kwargs()`，移除 `stream`，並加測試避免回歸。
  - 根因：Responses API 有兩種呼叫形態；`responses.create(..., stream=True)` 需要 stream flag，但 SDK 的 `responses.stream(...)` helper 本身已代表 streaming。
- **raw event logging 不能假設 `model_dump()` 永遠成功**
  - 試過無效：直接 `event.model_dump(mode="json")`，live SDK event 在本機丟出 `MockValSer` serializer TypeError。
  - 最終解法：`_to_dict()` 對 `model_dump()` / `to_dict()` 加容錯，失敗時降級保存 `repr`。
  - 根因：raw artifact 是診斷資料，不能讓非核心序列化失敗中斷主要 streaming。

### 備註
- live 驗證結果：`gpt-4.1-mini` provider smoke 通過；`gpt-5.4-mini` + `reasoning_effort=medium` default smoke 通過；FastAPI run route + SSE 雙 pane live smoke 通過。
- 回歸驗證結果：`python -m pytest tests\api`、`python -m compileall apps\api`、TypeScript build、Vitest、Vite build、Playwright desktop/mobile 均已通過。

---

## [2026-05-23 02:13] Stage 5 deterministic analysis

### 本次做了什麼（增量）
完成 Stage 5 第一版分析器：run streaming 完成後會建立 `analysis/analysis.json`，SSE 會先送 `analysis_ready` 再送 `run_completed`，並新增 `GET /api/runs/{run_id}/analysis`。分析內容包含各 pane 的本回合 usage、累計 usage、context section 結構、Harness 額外模組、左右 token delta；前端分析列會顯示目前回合與累計 token 摘要。

### 本次重大技術決策
- **分析器 deterministic，不呼叫 LLM**
  - 內容：`analysis_builder` 只讀 `run.json`、`input.json`、`output.json`、`usage.json` 與同 project 既有 run artifacts。
  - 理由：分析器若再呼叫 LLM 會新增成本與不確定性，且會污染「token 花在哪」的教學目的。
  - 影響：Stage 5 可穩定測試；未來若需要語意分析，可另加 optional analyzer provider。
- **usage 與 context section token 分離**
  - 內容：provider-reported usage 是真實 token 數；context section 只用字元數估算，並在 notes 標示。
  - 理由：OpenAI usage 只提供整體 input/output/reasoning，不提供每個自定 section 的精確 token 分攤。
  - 影響：UI 與 docs 不能把 `estimated_tokens` 當作 billing token。

### 本次失敗經驗與填坑
- **frontend-design 指定 audit scripts 不存在**
  - 試過無效：在 repo 搜尋 `audit:frontend-runtime` 與 `audit_frontend_principles.py`，目前沒有可執行目標。
  - 最終解法：保留現有獨立 Playwright desktop/mobile gate，並在 DEVNOTE 記錄此限制。
  - 根因：專案目前還沒有引入 frontend-design skill 內建 audit toolchain。

### 備註
- 驗證結果：`python -m pytest`、`python -m compileall apps\api`、TypeScript build、Vitest、Vite build、Playwright desktop/mobile 均已通過。

---

## [2026-05-23 02:43] 一鍵安裝啟動機制

### 本次做了什麼（增量）
依 `vibe-coding-guidelines` 將 repo 補成可一鍵安裝啟動的交付形態：新增 `project.config.json`、根目錄 `AGENTS.md`、`specs/requirements.md`、`todo.md`，導入 `scripts/project_launcher.py`、`scripts/project_launcher_posix.py`、`scripts/apsm_validate.py`，並新增 `scripts/start_backend.py` 作為 `apps/api` 的啟動橋接。已生成 `run_app.bat`、`run_app.command`、`run_app.sh`，並產出 `.runtime/ports.json`、`.runtime/launcher_state.json` 與 `logs/*.log` metadata。

### 本次重大技術決策
- **沿用 skill launcher 生成鏈**
  - 內容：`run_app.*` 不手寫主流程，所有 wrapper 由 `scripts/project_launcher.py` 生成。
  - 理由：符合 skill 的一鍵交付規範，也避免 Windows/macOS/Linux wrapper 行為分裂。
  - 影響：未來要調整啟動、安裝、port 或 logs 行為時，先改 generator 並重跑 `python scripts/project_launcher.py --package`。
- **APSM 採 apps layout variant**
  - 內容：在 `project.config.json` 保留 `web_app/separated/node_spa/python_api`，另加 `layout_variant=apps`，validator 也認得 `apps/api` + `apps/web`。
  - 理由：既有 repo 已是 `apps/` 結構，為了符合 APSM 又不重搬穩定目錄，需要顯式宣告 layout 變體。
  - 影響：APSM strict validation 以 `apps/api/app/main.py`、`apps/web/package.json`、`apps/web/index.html` 為必要檔案。

### 本次失敗經驗與填坑
- **Windows frontend launcher 相對路徑會重複 cd**
  - 試過無效：原生成結果先在父 cmd `cd apps\web`，再在新 frontend cmd 內 `cd apps\web`。
  - 最終解法：改 generator 以 `%~dp0apps\web` 組出絕對 `FRONTEND_DIR`，重產 `run_app.bat`。
  - 根因：Windows `start cmd /k` 的子程序繼承目前目錄；父程序先切目錄後，子程序再用相同相對路徑會變成二次巢狀。
- **sandbox 內安裝依賴會被網路限制擋住**
  - 試過無效：直接跑 `python scripts\project_launcher.py --ensure-only`，pip 查 PyPI 時回 WinError 10013。
  - 最終解法：依 sandbox escalation 流程重跑同一指令。
  - 根因：launcher 的首次安裝是必要網路操作，不能假設受限 sandbox 可直接連 registry。

### 備註
- 官方概念核對：Python `venv` 用於專案隔離環境；Node Corepack 可代理 pnpm 這類 package manager，與目前一鍵啟動設計一致。
- 驗證結果：`python scripts\apsm_validate.py --project . --strict`、`python scripts\project_launcher.py --ensure-only`、`python -m pytest`、`python -m compileall apps\api scripts`、TypeScript build、Vitest、Vite build、Playwright desktop/mobile 4 tests 均已通過；`python scripts\project_launcher.py --package --package-out release\HarnessDiff-launcher-smoke.zip` 已產出測試 ZIP。

---

## [2026-05-23 04:35] Windows launcher quoting fix

### 本次做了什麼（增量）
修正 `run_app.bat` 產生出的 backend/frontend 啟動命令。backend 由容易誤解析的 `cmd /k """%PYEXE%"" ..."` 改為 `start /d "%~dp0" cmd /k "call ""%PYEXE%"" ..."`；frontend 改為 `start /d "%FRONTEND_DIR%" cmd /k "call corepack ..."`，避免目前目錄繼承與 batch/cmd 呼叫中斷。

### 本次重大技術決策
- **Windows wrapper 繼續由 generator 修正**
  - 內容：只改 `scripts/project_launcher.py` 後重跑 `python scripts\project_launcher.py --package ...`，不直接手修 `run_app.bat`。
  - 理由：`run_app.*` 是 skill 規範要求的 generator 產物，手修 wrapper 會讓下一次產生又回歸。
  - 影響：後續所有 Windows launcher quoting 修正都應落在 generator。

### 本次失敗經驗與填坑
- **venv python.exe 被當成 Python 腳本**
  - 試過無效：原本 `cmd /k """%PYEXE%"" "scripts\start_backend.py" ..."` 在 Windows 下會讓 Python 嘗試讀入 `.venv\Scripts\python.exe` bytes，導致 `SyntaxError: Non-UTF-8 code starting with '\x90'`。
  - 最終解法：改成 `call ""%PYEXE%"" ""%~dp0scripts\start_backend.py""`，並以 `start /d "%~dp0"` 固定 backend 工作目錄。
  - 根因：`start` 與 `cmd /k` 各自處理引號；第一層 command string 不是一般 shell quote，EXE 路徑前後多餘引號會改變 argv 解析。
- **frontend log 顯示找不到路徑**
  - 試過無效：在子 `cmd /k` 內用 `cd /d "%FRONTEND_DIR%" && ...`。
  - 最終解法：改用 `start "Frontend" /d "%FRONTEND_DIR%" cmd /k ...`，讓 Windows `start` 直接設定子程序工作目錄。
  - 根因：子 cmd 的起始目錄與 batch 變數/引號展開互相耦合，`/d` 比在 command string 裡再 `cd` 穩定。

### 備註
- 驗證結果：重產 `run_app.*` 與 ZIP；`cmd /c call ""...\python.exe"" -c ...` 可正確使用 venv Python；`cmd /c pushd apps\web && call corepack pnpm --version` 回傳 `11.2.2`；`python scripts\apsm_validate.py --project . --strict` 通過。

---

## [2026-05-23 05:02] Windows helper launcher fix

### 本次做了什麼（增量）
確認使用者實際雙擊 `run_app.bat` 時，上一版 `start ... cmd /k "call ""%PYEXE%"" ..."` 仍會把 `.venv\Scripts\python.exe` 當成腳本讀取。改為由 `project_launcher.py` 產生 `scripts\launch_backend.bat` 與 `scripts\launch_frontend.bat`，`run_app.bat` 只用 `start` 開啟這兩個 helper。

### 本次重大技術決策
- **Windows 子服務啟動改走 helper batch**
  - 內容：backend/frontend 的實際 command、log redirection、working directory 都放到 helper batch。
  - 理由：Windows `cmd /k` 的巢狀引號行為和雙擊 batch 情境不穩定；helper batch 讓每一層只處理一個簡單命令。
  - 影響：後續調整 Windows 啟動流程時，仍應改 generator，並重產 `run_app.bat` 與 helper batch。

### 本次失敗經驗與填坑
- **`call ""%PYEXE%""` 在最小重現仍失敗**
  - 試過無效：`start "Backend" /d "%~dp0" cmd /k "call ""%PYEXE%"" ..."`。
  - 最終解法：`run_app.bat` 改成 `start "Backend" /d "%~dp0" "%~dp0scripts\launch_backend.bat"`；helper 內直接執行 `"%PYEXE%" "%PROJECT_ROOT%\scripts\start_backend.py"`。
  - 根因：`cmd /k` 對 `<string>` 的引號處理會剝離外層 quote 且保留內層 quote 的規則很容易造成 argv 混淆。

### 備註
- 驗證結果：直接執行 `scripts\launch_backend.bat` 後 `127.0.0.1:8000` 可連，log 顯示 Uvicorn started；直接執行 `scripts\launch_frontend.bat` 後 `127.0.0.1:5173` 可連，Vite 正常監聽；測試後已關閉兩個驗證 server。

---

## [2026-05-23 12:28] Conversation controls and Markdown UX

### 本次做了什麼（增量）
補齊使用者指出的 Chat workbench 缺口：新增 TopBar「新對話」與「歷史」入口、歷史對話 drawer、自動用第一個 prompt 命名 project、`GET /projects/{project_id}/transcript` 供前端重建左右 pane 訊息、Composer「暫停執行」按鈕，以及 assistant/user 訊息 Markdown 排版與複製原始 Markdown。

### 本次重大技術決策
- **Project 即 Conversation**
  - 內容：不新增第二套 conversation storage；沿用 Project 作為對話紀錄單位，run artifacts 作為 transcript。
  - 理由：既有本機 JSON 已以 project/runs 分層保存完整上下文；重複建 conversation 層會增加遷移和一致性成本。
  - 影響：歷史列表讀 `GET /projects`，歷史內容讀 `GET /projects/{project_id}/transcript`。
- **暫停先取消前端 stream**
  - 內容：前端用 `AbortController` 中止 SSE fetch，並將當前 streaming message 收尾為 done。
  - 理由：Fetch/stream 的標準取消方式是 AbortController；後端已在 stream CancelledError 路徑標記 run cancelled。
  - 影響：未來若要顯示更細的取消原因，可補 `run_cancelled` SSE event 或專用 cancel route。

### 本次失敗經驗與填坑
- **Playwright smoke 連到真實 backend**
  - 試過無效：沿用原本期待 mock fallback 文案的 smoke test。
  - 最終解法：在 smoke test 明確 abort `/api/**`，讓測試只驗證離線 UI fallback，不受本機 8000 是否正在跑影響。
  - 根因：一鍵 launcher 讓 backend 更容易常駐，e2e 測試不能假設 API 一定 unavailable。

### 備註
- 驗證結果：`python -m pytest` 14 passed、TypeScript build、Vitest、Vite build、Playwright desktop/mobile 10 tests passed。

---

## [2026-05-25 06:37] Harness tools, source citations, attachments, skills, and slash commands

### 本次做了什麼（增量）
補齊 Harness 端對話核心能力：`tool_policy` 可啟用 ToolAnything 風格工具、web/fs/data/read-only shell 與 `harness.subagent.run`；OpenAI Responses provider 可把 function-call 結果回送模型並完成多輪 tool loop。前端 Composer 新增夾檔、貼上檔案/圖片、文字與表格預覽、Office/PDF metadata preview、圖片 data URL preview、麥克風語音輸入；技能系統新增 `~/.harnessdiff` 初始化、`CLAUDE.md`、`AGENTS.md`、`agents.md`、`skills/`、技能列表/匯入 API、UI 技能面板、新對話第一層技能 context 注入，以及文字方塊內 `/skill-id` 斜線指令載入完整 `SKILL.md`。同時修正 Harness 上網查資料未自動來源引述：web 工具輸出會附 `citation_sources` 與 `citation_guidance`，最終回答被要求輸出 inline Markdown links 與 Sources 區塊。

### 本次重大技術決策
- **Harness 工具迴圈只由 `tool_policy` 顯式開啟**
  - 內容：OpenAI provider 負責 function-call loop；`ChatToolRuntime`/`SubagentToolRuntime` 只在 backend policy 允許時註冊工具。
  - 理由：避免一般對話無意暴露 filesystem/shell/subagent 能力，也讓不同模式可控制工具面。
  - 影響：未來新增工具要先定義 policy、schema、runtime handler 與測試，不應直接在 prompt 內假裝可用。
- **來源引述由 web 工具輸出補強，不改 artifact schema**
  - 內容：web search 結果整理成 `citation_sources`、`citation_guidance`，由 provider 指示模型在回答中使用 Markdown 連結和 Sources。
  - 理由：變更面小，能先解決「有查資料但沒有引述」；不需要立刻重設 run/artifact 資料模型。
  - 影響：引用品質仍依賴模型遵循 guidance；若未來要強制驗證，可再加 response post-check。
- **附件先進入對話 context，不先設計 binary upload contract**
  - 內容：前端先用 `FileReader` 解析文字、CSV preview、Office/PDF metadata、image data URL，送入 message context。
  - 理由：可快速支援 Ctrl+V 與迴紋針的基礎體驗，並保持現有 chat API 向前相容。
  - 影響：大型檔案、真正 pandas DataFrame、PIL Image 物件與 Office/PDF 深度抽取仍需後端 upload/parse endpoint。
- **技能採 user home store，分成第一層 context 與完整揭露**
  - 內容：`~/.harnessdiff/skills` 保存技能；新對話只放 `name/description`，使用 slash command 或技能操作時才取完整 `SKILL.md`。
  - 理由：符合 progressive disclosure，避免每次新對話塞入所有技能全文。
  - 影響：技能匯入與讀取都要防 path traversal，前端需要區分摘要列表與 full skill payload。
- **技能匯入用 JSON base64，不先導入 multipart**
  - 內容：zip/skill 檔和資料夾匯入都經由 JSON request，資料夾以 `{path, contentBase64}` entries 表示。
  - 理由：沿用既有 `fetchJson` 風格，減少 frontend/backend 同時新增 multipart parser 的成本。
  - 影響：大技能包未來可能需要 multipart 或 streaming upload；目前適合中小型 skill。

### 本次失敗經驗與填坑
- **PowerShell `date "+%Y-%m-%d %H:%M"` 不是 GNU date**
  - 試過無效：直接執行使用者流程中的 `date "+%Y-%m-%d %H:%M"`，PowerShell 把 `date` 當 `Get-Date` alias，導致 positional parameter 錯誤。
  - 最終解法：改用 `Get-Date -Format "yyyy-MM-dd HH:mm"` 取得本地時間戳。
  - 根因：同名命令在 PowerShell 與 Bash 語意不同，跨 shell 指令不能假設 GNU coreutils 行為。
- **import-time 寫入 `~/.harnessdiff` 會讓測試污染使用者 home**
  - 試過無效：在 module import 階段立即初始化 HarnessDiff home。
  - 最終解法：改為 lazy ensure，只在 API/store 實際需要時建立目錄與預設檔。
  - 根因：import side effect 會破壞測試隔離，也讓單純匯入模組變成有狀態的 filesystem operation。
- **frontend build/test 會寫 sandbox 外 cache 或 tsbuildinfo**
  - 試過無效：部分 TypeScript/Vite/Playwright 指令在受限 sandbox 直接執行。
  - 最終解法：依流程對必要 build/test 指令申請 escalation；Python compileall 改用 `-X pycache_prefix=.compile_pycache`。
  - 根因：工具鏈預設輸出不一定落在 repo 可寫範圍，尤其是 node/vite cache 與 Python pycache。
- **zip/folder skill 匯入必須顯式防 path traversal**
  - 試過無效：不能只信任 zip entry 或 folder entry 的相對路徑。
  - 最終解法：backend 檢查 entry path、拒絕絕對路徑與 `..` 跳脫，並驗證技能根需要可辨識 manifest/`SKILL.md`。
  - 根因：匯入功能本質上是使用者提供壓縮檔/資料夾寫入 home 目錄，必須先限制寫入邊界。

### 備註
- 主要驗證結果：`python -m pytest` 42 passed；`python -X pycache_prefix=.compile_pycache -m compileall apps\api` 通過；TypeScript build 通過；Vitest 12 passed；Vite build 通過；Playwright 26 passed；`python scripts\apsm_validate.py --project .` valid。
- 仍需補強：Office/PDF 深度解析、真正 pandas DataFrame/PIL 物件、後端 binary upload contract、Web Speech API 權限/瀏覽器支援提示，以及 web citation 的強制 post-check。

---

## [2026-05-25 22:21] Vision input, press-and-hold voice, skill chips, and image bubble display

### 本次做了什麼（增量）
本次 session 先修正語音輸入互動，將「點一下開始、再點一下結束」改為「按下開始、放開/取消停止」。接著接入 OpenAI Responses API 視覺輸入：前端圖片附件會產生 data URL，建立 run 時帶 `attachments`，後端以 `LLMImageAttachment` 傳入 provider，OpenAI payload 會組成 `input_text` + `input_image`。之後把 skill slash command 從普通文字改成 teal chip token，避免和一般 prompt 混淆，並支援整塊刪除。最後開始處理「圖片應顯示在對話中」：已新增 display-only `Message.attachments`、ChatPane 圖片縮圖 render 與 e2e 斷言，但在使用者要求 `/devnote` 時尚未跑完驗證。

### 本次重大技術決策
- **圖片能力分成 provider input 與 UI display 兩條路徑**
  - 內容：provider 讀圖走 `RunCreate.attachments` / `LLMImageAttachment` / Responses `input_image`；對話中顯示走 `Message.attachments`，只作為 display-only UI metadata。
  - 理由：provider payload 需要穩定、可保存、可重播；UI 預覽需要避免被送出後 `URL.revokeObjectURL()` 破壞，兩者生命週期不同。
  - 影響：後續若要歷史 transcript 也顯示圖片，需要在 storage/transcript 裡保存可顯示的 attachment metadata 或 artifact，而不是只依賴前端 runtime state。
- **圖片用 data URL 先接 Responses vision**
  - 內容：前端只對 PNG/JPEG/WEBP/GIF 產生 base64 data URL，後端驗證 MIME 與 URL scheme，再傳給 OpenAI Responses `input_image`。
  - 理由：避免先設計 multipart upload/binary artifact contract，也能保持既有 run API 向前相容。
  - 影響：大型圖片會增加 JSON payload；若未來支援大檔/多圖/歷史重放，應改為後端 upload artifact + URL/file reference。
- **語音按住互動用 Pointer Events**
  - 內容：`pointerdown` start、`pointerup`/`pointercancel` stop，並用 pointer capture 提高滑鼠/觸控拖出按鈕時的結束可靠性；Space/Enter 也做 keydown/keyup。
  - 理由：長按是 press lifecycle，不是 click toggle；只靠 click 無法表達放開停止。
  - 影響：未來若改成真正錄音或 Realtime API，也應沿用 press lifecycle。
- **Skill slash command 以 contenteditable atomic token 呈現**
  - 內容：Composer 輸入從 textarea 改成 `role="textbox" aria-multiline="true"` 的 contenteditable；已安裝 skill slash command 渲染為 `contenteditable=false` chip，但底層 value 仍是 `/skill-id ` 文字。
  - 理由：textarea 不能局部上色或做不可逐字編輯 token；contenteditable 才能提供 chip 視覺和原子刪除。
  - 影響：測試、Playwright selector、外部操作不應再找 `textarea`；要用 `.promptEditor` 或 ARIA textbox。

### 本次失敗經驗與填坑
- **圖片送進模型但對話中看不到**
  - 試過無效：只把圖片轉成 provider attachment；user bubble 仍只 render prompt markdown，因此畫面只有 metadata 文字。
  - 最終解法：新增 `Message.attachments` 與 ChatPane `.messageAttachmentGrid`，用 display-only data URL 顯示 `<img>`。
  - 根因：LLM provider input 與 UI message render 是兩條不同資料流；前者成功不會自動讓後者顯示圖片。
- **清附件會讓 blob URL 失效**
  - 試過無效：若 user message 只保存 `attachment.url` 的 blob URL，送出後 `clearAttachments()` 會 revoke，對話圖片可能失效。
  - 最終解法：message display attachment 優先保存 `attachment.dataUrl`，只有非圖片或沒有 data URL 時才 fallback 到 `url`。
  - 根因：blob URL 是 browser runtime resource，不是可長期保存的 message artifact。
- **textarea 無法滿足 skill token 需求**
  - 試過無效：只改 slash command 文字顏色；textarea 只能整體樣式，不能局部 token 化，也不能禁止部分文字被逐字編輯。
  - 最終解法：改成 contenteditable editor，自己做 plain text extraction、selection offset、token render 與 Backspace/Delete 整塊刪除。
  - 根因：原生 textarea 是 plain text control，不支援內嵌不可編輯元素。
- **本地驗證常被 Windows 權限與 sandbox 寫入擋住**
  - 試過無效：直接跑 TypeScript/Vitest/Vite/Playwright 時多次遇到 `EPERM` 寫 `tsconfig.tsbuildinfo`、`.vite-temp` 或 `test-results`。
  - 最終解法：必要驗證命令用 sandbox escalation；後端 compileall 也可能需要寫 `__pycache__` 權限。
  - 根因：工具鏈會寫入 build cache / report artifact，而這些路徑不一定在預設 sandbox 可寫範圍內。

### 備註
- 已完成驗證：OpenAI provider / run API tests 28 passed；TypeScript build 通過；Vitest 14 passed；語音 e2e desktop/mobile passed；skill slash command e2e desktop/mobile passed；完整 Playwright 26 passed；Vite production build 通過。
- 尚未完成驗證：`Message.attachments` 圖片 bubble 顯示改動是在 `/devnote` 前剛加入，需接續跑 TypeScript、Vitest、相關 Playwright attachment case 與 build。

---

## [2026-05-28 19:48] Harness consequence gate

### 本次做了什麼（增量）
將 Harnessable 本次新增的泛用 Consequence Gate 思路導入 HarnessDiff。Harness pane 預設多一個 `consequence_gate` module；當 prompt 看起來是對外發布、社群貼文、公告、行銷活動或客戶可見內容時，`HarnessableControlPlane` 會在 provider 前發出 `FINAL_OUTPUT_PROPOSED` preflight event，並把缺失 release context、風險假設與 review needs 寫成 `harness_decision` artifact。NoHarness 不套用此 gate，仍維持 baseline。

### 本次重大技術決策
- **不把 consequence gate 寫進 provider**
  - 內容：`context_builder` 只把 `consequence_gate` 轉成 Harness pane instructions；實際 preflight 仍走 `HarnessableControlPlane` 與 Harnessable rule decision。
  - 理由：維持原本 provider-neutral 邊界，讓 OpenAI provider 只接收最終 `LLMRequest`。
  - 影響：未來擴充 Anthropic/local provider 不需要理解 consequence gate，只要讀 `LLMRequest.instructions` 與既有 gate artifacts。
- **只對 publication-like prompt 產生 gate decision**
  - 內容：先用保守關鍵詞判斷是否涉及對外發布/社群/公告/行銷/客戶可見，再發出 preflight。
  - 理由：避免所有一般 coding/analysis prompt 都被標成缺少 release context，造成教學噪音。
  - 影響：未知型態仍靠 prompt instruction 逼模型自我檢查；真正強制攔截可在未來接上明確 publication/action tool。

### 本次失敗經驗與填坑
- **舊版 Harnessable 不能讓整個 control plane 失效**
  - 試過無效：直接從 `harnessable` 匯入 `ConsequenceGate`。
  - 最終解法：`HarnessKernel` / `HarnessRule` 維持必須可用，`ConsequenceGate` 採 optional import；沒有新版 Harnessable 時仍保留既有 guardrails。
  - 根因：HarnessDiff 可在不同本機開發狀態下啟動，不能假設 sibling Harnessable 一定已升級。
- **前端新增 toggle 需要 mobile gate**
  - 試過無效：只跑 TypeScript/Vitest 不足以證明 settings menu 沒破版。
  - 最終解法：補跑完整 Playwright desktop/mobile，確認新增 `Consequence Gate` toggle 沒造成 overflow 或設定面板回歸。
  - 根因：Harness settings 是 disclosure UI，新增一列最容易在 mobile 寬度暴露排版問題。

### 備註
- 驗證結果：`python -m pytest -q` 74 passed、1 skipped；`python -X pycache_prefix=.compile_pycache -m compileall apps\api` 通過；`corepack pnpm --dir apps\web test` 17 passed；`corepack pnpm --dir apps\web build` 通過；`corepack pnpm --dir apps\web test:e2e` 26 passed。

---

## [2026-05-28 20:25] Publishing risk harness preview

### 本次做了什麼（增量）
將 Harnessable 新增的 publishing risk harness 能力導入 HarnessDiff 的 Harness pane preview：`consequence_gate` 現在會在 provider 前建立更完整的 `risk_context`，並透過 Harnessable preview rules 記錄 missing context、scanner findings、claim evidence gaps、offer disclosure gaps、provenance/rights gaps 與 rollback readiness gaps。前端分析列新增緊湊的 Harness risk chips，讓使用者看見本回合命中的治理缺口，但不把 HarnessDiff 變成真正發布閘門。

### 本次重大技術決策
- **Preview 而非 blocking publication gateway**
  - 內容：HarnessDiff 仍只在 `FINAL_OUTPUT_PROPOSED` 階段記錄 `WARN` 型 `harness_decision`，不阻斷 provider 產生比較答案。
  - 理由：HarnessDiff 是 NoHarness/Harness 教學比較 workbench，不是企業 CMS/CRM 的實際發布管線；真正發布阻擋應交由 Harnessable `PublicationGateway`。
  - 影響：NoHarness 保持 baseline；Harness pane 顯示治理差異與風險缺口。
- **Scanner adapter 不引入重依賴**
  - 內容：不在 HarnessDiff core 內建 OCR/CV/embedding/claim extraction；只用結構化 scanner finding 形狀與 prompt metadata preview。
  - 理由：符合不新增不必要依賴與不維護禁忌黑名單的設計精神。
  - 影響：未來若接真實 scanner，只要把結果放進 `scanner_results` 形狀即可。

### 本次失敗經驗與填坑
- **只記錄缺 context 不足以展示新版 Harnessable 能力**
  - 試過無效：前一版 `consequence_gate` 只讓 prompt-like public content 產生缺情境與誤讀假設。
  - 最終解法：新增 HarnessDiff preview rules，讓 claim/offer/provenance/scanner/rollback detector 在 `FINAL_OUTPUT_PROPOSED` 也能以 `WARN` 形式留下 trace。
  - 根因：Harnessable 的新版 publishing detectors 主要設計給 `PUBLICATION_REQUESTED`；HarnessDiff 若不加 preview rules，UI 看不到新增能力。

### 備註
- 驗證結果：`python -m pytest tests\api\test_runs.py -q` 24 passed；`python -m pytest -q` 75 passed、1 skipped；`python -X pycache_prefix=.compile_pycache -m compileall apps\api` 通過；`corepack pnpm --dir apps\web test` 17 passed；`corepack pnpm --dir apps\web build` 通過；`corepack pnpm --dir apps\web test:e2e` 26 passed。
---

## [2026-05-28 21:12] Scanner coverage and provenance contract sync

### 本次做了什麼（增量）
同步 Harnessable 新增的 scanner coverage 與 similarity/provenance scanner result contract 到 HarnessDiff。Harness pane 的 `consequence_gate` preview 現在會從 publication-like prompt 推斷 `asset_kind`、建立 `scanner_coverage.required_scanners`，並在 prompt 暗示抄襲/相似/來源/文化/授權風險時輸出 `similarity.match` 與 `provenance.review` 形狀的 structured findings。前端 analysis chips 也會顯示 coverage、similarity、provenance finding 訊號。

### 本次重大技術決策
- **HarnessDiff 只做 preview contract，不做 scanner engine**
  - 內容：新增 prompt metadata scanner 形狀與 coverage gap 顯示，但不宣稱已跑 OCR/CV/embedding/similarity model。
  - 理由：HarnessDiff 是教學比較 workbench；真正 scanner 仍應由 Harnessable adapter 或外部 CMS/DAM 接入。
  - 影響：UI 可展示未知風險如何浮現，但不會把 prompt keyword preview 誤包裝成 production release gate。
- **Coverage gap 即風險納入 Harness pane**
  - 內容：高風險 asset kind 會要求 OCR/CV/ASR/similarity/provenance/rights 等 coverage；缺少時寫入 `scanner_coverage_gaps`。
  - 理由：避免只有 scanner 回報 finding 才有風險，沒有 scanner result 反而被誤解為安全。
  - 影響：NoHarness 仍是 baseline；Harness pane analysis 會多顯示 coverage 類 risk chip。

### 本次失敗經驗與填坑
- **測試 prompt 沒有 similarity 語彙卻期待 similarity finding**
  - 試過無效：直接斷言 `similarity_matches`。
  - 最終解法：測試 prompt 明確加入「相似參考素材」，讓 fixture 和 detector trigger 對齊。
  - 根因：prompt metadata preview 是保守觸發，不應憑空產生相似度 finding。

### 備註
- 驗證結果：`python -m pytest tests\api\test_runs.py -q` 24 passed；`python -m pytest -q` 75 passed、1 skipped；`python -X pycache_prefix=.compile_pycache -m compileall apps\api` 通過；`corepack pnpm --dir apps\web test` 17 passed；`corepack pnpm --dir apps\web build` 通過。

---

## [2026-06-05 23:29] Skill pane independence and custom prompt diagnosis

### 本次做了什麼（增量）
修正 NoHarness/Harness pane skill 永遠相同的問題：一般 chat 與 Agent surface 的 skill selection 都從 run-level 移到 profile-level，並明確區分 NoHarness `llm_only` 與 Harness `llm_with_deterministic_fallback`。同時診斷 `~/.codex/prompts` 未載入問題：官方 Codex custom prompts 已 deprecated，但仍可在 Codex CLI/IDE extension 用 `/prompts:name` 呼叫；HarnessDiff 目前沒有 prompts subsystem，前端 slash menu 與後端 `SkillStore` 都只支援 skills。最後依 `/prompts:debug_report skill兩個pane未獨立` 產出 debug report 與 archive README。

### 本次重大技術決策
- **Skill selection state boundary 改為 profile**
  - 內容：`RunOrchestrator` 與 `AgentRunOrchestrator` 都在 `run_profile(profile)` 內呼叫 `_select_skills_for_profile(run, profile)`。
  - 理由：NoHarness/Harness 的差異來自 profile capability 與 policy；若 selector 在 run 外層執行，就不可能讓兩 pane 獨立判斷。
  - 影響：integrated run 仍共享 prompt、attachments 與 run artifact，但 skill context、skill invocation event、fallback policy 均以 profile 為界。
- **NoHarness 不套 deterministic fallback**
  - 內容：`_skill_selection_policy_for_profile(profile)` 對 baseline/NoHarness 回傳 `llm_only`；Harness profile 回傳 `llm_with_deterministic_fallback`。
  - 理由：使用者明確要求 NoHarness 是 LLM-only，Harness 才是完整 LLM 判斷加 deterministic guard/fallback。
  - 影響：當 LLM selector 回空時，baseline 不會被 deterministic skill match 污染；Harness 仍能用 fallback 保守啟用。
- **Prompt metadata 不混進 SkillStore**
  - 內容：本次只診斷 `~/.codex/prompts` 未載入，不把 deprecated custom prompts 硬塞進現有 skill 管線。
  - 理由：官方 custom prompts 是 slash command expansion surface，和 skills 的 implicit/explicit reusable workflow 不同；混用會讓 auto selection 與 prompt expansion 語意混亂。
  - 影響：若未來要支援，建議新增 `PromptStore`、`/api/prompts` 與前端 `prompts:` namespace。

### 本次失敗經驗與填坑
- **把 pane 問題誤判成 UI 顯示會漏掉真正根因**
  - 試過無效：只看前端 streaming message update。
  - 最終解法：追到 `run_orchestrator.py` 與 `agent_orchestrator.py`，確認舊版是在 profile 外先選一次 skill，再把同一組 `selected_skill_ids` 寫入每個 profile。
  - 根因：UI 是照 `profile_id` 正確顯示；錯的是後端 selection state 放在 run-level。
- **只修一般 chat 會留下 Agent surface 回歸**
  - 試過無效：只改 `RunOrchestrator`。
  - 最終解法：`AgentRunOrchestrator` 同步移除 run-level selected skill cache，改在 agent profile execution 內選 skill。
  - 根因：Agent mode 繼承同一組 routing helper，但有獨立 stream path；兩條 orchestrator 都要維護相同 state boundary。
- **`~/.codex/prompts` 存在不代表 HarnessDiff 會載入**
  - 試過無效：只檢查 `C:\Users\allan\.codex\prompts\debug_report.md` 與 `devnote.md` 存在且 front matter 有效。
  - 最終解法：查官方 Codex manual 與 HarnessDiff code path，確認官方要求 `/prompts:name`、restart/new chat、top-level Markdown；HarnessDiff 則沒有任何 prompts 掃描或展開邏輯。
  - 根因：這是 product surface 差異，不是檔案格式錯誤。
- **測試 collection 會被 log 寫入權限擋住**
  - 試過無效：直接在 sandbox 跑 `python -m pytest tests\api\test_runs.py tests\api\test_openai_provider.py`。
  - 最終解法：依 policy 升權重跑同一組 pytest。
  - 根因：`toolanything` import 初始化會寫 `logs/toolanything.log`，sandbox 內 collection 階段就可能失敗。

### 備註
- 驗證結果：`python -m pytest tests\api\test_runs.py tests\api\test_openai_provider.py` 45 passed；`python -m pytest tests\api\test_agent_runtime.py` 10 passed。
- 本次新增 debug report：`debugs/2026-06-05_skill_two_pane_not_independent_debug_report.md`。
- 本次新增 archive README：`debugs/archive/2026-06-05_skill_two_pane_not_independent/README.md`。
- 仍需注意：工作樹內存在非本次 skill-pane 修正核心的既有變更與未追蹤圖片，未經使用者確認不要清理或回退。

