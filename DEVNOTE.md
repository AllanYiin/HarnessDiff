# DEVNOTE — HarnessDiff

> 累加式開發筆記，取代 `/compact`。
> **檔頂 SNAPSHOT**：當前最新狀態（覆寫式，想知道「現在」就看這裡）。
> **檔尾 HISTORY**：時間順序的歷史區塊（累加式，想知道「為什麼」就往下讀）。

---

## 📌 SNAPSHOT — 當前狀態
<!-- 這一整段每次 /devnote 會被覆寫，只反映「到目前為止的最新狀態」 -->

**最後更新**：2026-05-23 00:01

### 需求狀態
- [x] Stage 0：localhost web app / FastAPI skeleton、README、env 樣板、storage/provider docs。
- [x] Stage 1：本機 JSON project CRUD、schema version、atomic write、corrupt JSON repair report。
- [x] Stage 2：雙 Pane Chat UI、整合/個別輸入模式、附件預覽、mock streaming、Playwright desktop/mobile 視覺 smoke。
- [x] Stage 3：OpenAI Responses API streaming provider、run orchestration、SSE routes、前端串接已通過 fake provider、default model live provider、雙 pane route/SSE live 驗證。
- [x] Stage 4：Harness Engine 與組態開關第一版完成；project config、run-level overrides、Harness-only instructions、UI toggles、input artifact traceability 均已接上。
- [ ] Stage 5：本回合與累計分析器。
- [ ] Stage 6：整合/回歸/邊界測試。
- [ ] Stage 7：文件化與交付。

### 未解問題
- `specs/` 目錄尚未建立；前一次使用者要求切規格時被後續截圖驗證任務中斷。
- 本機 `npm` shim 壞掉，已改用 Corepack pnpm 的實際路徑或 `corepack pnpm`。

### 關鍵技術決策（當前有效）
> 歷史上做過的、目前仍然成立的決策摘要。被推翻的決策不列。
- **Repo root**：GitHub 上傳目錄是 `D:\PycharmProjects\HarnessDiff\github_repo`，外層殘留已刪除（詳見 HISTORY `[2026-05-22 23:37]`）。
- **Storage source of truth**：MVP 以本機 JSON 為準，保留 `schema_version` 與 repair report。
- **Provider boundary**：第一版只接 OpenAI Responses API，但必須經 provider adapter，避免 route 直接綁死 OpenAI。
- **Streaming first**：所有 LLM 輸出必須 streaming；Responses API 需處理 semantic events，如 `response.output_text.delta`、`response.completed`、`error`。
- **API-first fallback**：前端送出會先呼叫 FastAPI run endpoint；若後端未啟動或 API 失敗，才 fallback 到既有 mock streaming，讓 Stage 2 e2e 不需後端也能通過。
- **Harness Engine boundary**：Harness 技巧只在 `context_builder` 轉成 Harness pane instructions；provider 只看最終 `LLMRequest`，不理解 Harness 模組細節。
- **Stage 2 visual gate**：獨立 Playwright Chromium 已取代 Codex in-app browser 截圖，desktop/mobile e2e 會輸出 screenshots。

### 已知地雷（仍需注意）
> 踩過且未來仍可能重踩的坑的一句話提醒。已徹底不可能重現的不列。
- **Codex Browser 截圖 timeout**：in-app browser 的 `Page.captureScreenshot` 曾 timeout；視覺驗證改用獨立 Playwright Chromium。
- **Mobile overflow**：Playwright 曾抓到 393px viewport 下 14px horizontal overflow；已用 global `box-sizing` 與 mobile controls 收縮修正。
- **Vitest / Playwright 掃檔衝突**：Vitest 必須限定 `src`，否則會把 `e2e/*.spec.ts` 當 Vitest 測試。
- **Sandbox 啟動 Chromium**：Playwright Chromium 在 sandbox 內會 `spawn EPERM`；本機驗證需 escalated 執行。
- **E2E proxy ECONNREFUSED**：只有 Vite 前端啟動、FastAPI 未啟動時，Playwright 會看到 `/api/projects` proxy error；目前是預期 fallback 行為，不代表 UI smoke 失敗。
- **OpenAI stream helper 參數**：`client.responses.stream(...)` 不接受 `stream=True`；只有 `responses.create(..., stream=True)` 需要該參數。
- **SDK raw event 序列化**：OpenAI SDK event 的 `model_dump()` 可能在本機環境丟 TypeError；raw artifact logging 必須容錯降級。
- **PowerShell 文字讀寫**：讀寫文字檔需顯式 `-Encoding UTF8`，不可裸用 `Get-Content` / `Set-Content`。

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
