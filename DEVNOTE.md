# DEVNOTE — HarnessDiff

> 累加式開發筆記，取代 `/compact`。
> **檔頂 SNAPSHOT**：當前最新狀態（覆寫式，想知道「現在」就看這裡）。
> **檔尾 HISTORY**：時間順序的歷史區塊（累加式，想知道「為什麼」就往下讀）。

---

## 📌 SNAPSHOT — 當前狀態
<!-- 這一整段每次 /devnote 會被覆寫，只反映「到目前為止的最新狀態」 -->

**最後更新**：2026-05-23 02:43

### 需求狀態
- [x] Stage 0：localhost web app / FastAPI skeleton、README、env 樣板、storage/provider docs。
- [x] Stage 1：本機 JSON project CRUD、schema version、atomic write、corrupt JSON repair report。
- [x] Stage 2：雙 Pane Chat UI、整合/個別輸入模式、附件預覽、mock streaming、Playwright desktop/mobile 視覺 smoke。
- [x] Stage 3：OpenAI Responses API streaming provider、run orchestration、SSE routes、前端串接已通過 fake provider、default model live provider、雙 pane route/SSE live 驗證。
- [x] Stage 4：Harness Engine 與組態開關第一版完成；project config、run-level overrides、Harness-only instructions、UI toggles、input artifact traceability 均已接上。
- [x] Stage 5：本回合與累計分析器第一版完成；analysis artifact、SSE `analysis_ready`、API retrieval、前端 summary metrics、current/cumulative usage 與 context sections 均已接上。
- [x] Stage 6：整合/回歸/邊界測試完成；provider failure、invalid ids、lazy analysis rebuild、single-pane analysis、settings disclosure、analysis_ready e2e 均已納入。
- [x] Stage 7：文件化與交付完成；README quick start、API reference、troubleshooting、specs/product-spec、specs/stage-plan、release checklist 與 docs audit 均已收尾。
- [x] 一鍵安裝啟動機制：依 `vibe-coding-guidelines` 補 `project.config.json`、`AGENTS.md`、`specs/requirements.md`、`todo.md`、launcher generator、APSM validator、`run_app.*` 與 runtime metadata。

### 未解問題
- 本機 `npm` shim 壞掉，已改用 Corepack pnpm 的實際路徑或 `corepack pnpm`。

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
