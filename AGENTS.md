# AGENTS.md

## 1. 專案定位

- HarnessDiff 是本機 localhost 教學工作台，用來比較同一個 Chat 任務在 `NoHarness` 與 `Harness` 兩側的差異。
- 使用者是 Harness Engineering 教學者、小團隊 demo 製作者與需要低摩擦啟動的非程式使用者。
- 使用情境是 `scene_b_shared_tool`：少量人共用、長期保存、不能要求使用者理解命令列。
- 技術型態是 `web_app + separated + node_spa + python_api`，現有 layout 使用 `apps/api` 與 `apps/web`。

## 2. 本專案最高原則

- 交付目標是解壓後點一下啟動：Windows 用 `run_app.bat`，macOS 用 `run_app.command`，Linux 用 `run_app.sh`。
- 啟動器必須由 `scripts/project_launcher.py` 生成或維護；不要手寫另一套平行主入口。
- 優先保留向前相容與現有資料格式；不要任意改 local JSON schema、endpoint 或檔案路徑。
- OpenAI key 只能從環境變數或 `.env` 讀取，不得寫入程式、logs 或文件範例中的真實值。
- 修改後同步更新 `specs/requirements.md`、`todo.md`、README 或 docs 中受影響內容。

## 3. 目錄與檔案規範

- `apps/api`：FastAPI backend、provider adapter、storage、analysis。
- `apps/web`：React/Vite frontend、components、domain tests、Playwright tests。
- `scripts/project_launcher.py`：唯一 launcher 生成與一鍵啟動維護入口。
- `scripts/apsm_validate.py`：APSM 結構檢核。
- `specs/requirements.md`：可執行需求真相來源。
- `project.config.json`：usage scene 與 APSM 技術選型真相來源。
- `data/projects`：本機 runtime data；不得把使用者資料提交到 git。

## 4. 實作規範

- 後端 route 不直接寫 OpenAI SDK 細節；provider 專屬邏輯放在 `apps/api/app/providers`。
- Harness 技巧先在 `context_builder` 轉成 Harness pane instructions；provider 只接收最終 `LLMRequest`。
- Stage 5 analysis 必須 deterministic，預設只讀 local JSON artifacts，不呼叫 LLM。
- 任一 pane provider error 時，run 必須標記 `failed` 並送出 `run_failed`，不得產生完整 comparison analysis。
- PowerShell 讀寫文字檔必須顯式指定 `-Encoding UTF8`。

## 5. UI / UX 規範

- 這是 workbench，不是 dashboard；唯一主任務是比較左右兩側 Chat 輸出與上下文/token 差異。
- 主畫面保持左右 pane 為最大、最中央、最先被看的區域。
- 首屏主要視覺群組維持在 2-3 個：top controls、dual pane workspace、composer/analysis status。
- reference 資訊退到 docs、settings disclosure 或後續 tab，不做 stacked cards 首頁。
- exception-handling 只在錯誤 state 顯示；空狀態要說明下一步。
- 每次 UI 改動都要檢查 desktop/mobile horizontal overflow、composer 可見與 pane 可用。

## 6. 修改規範

- 小改保持最小範圍；不要順手重構無關模組。
- 修改 API schema 時同步更新 `docs/api-reference.md`、`docs/storage-format.md` 與 tests。
- 修改 launcher 行為時同步跑 `python scripts/apsm_validate.py --project .`。
- 修改前端 layout 時同步跑 Playwright desktop/mobile。

## 7. 測試與打包規範

交付前至少執行：

```powershell
python -m pytest
python -m compileall apps\api
node apps\web\node_modules\typescript\bin\tsc -b apps\web
node apps\web\node_modules\vitest\vitest.mjs run src --root apps\web
node apps\web\node_modules\vite\bin\vite.js build apps\web
node apps\web\node_modules\@playwright\test\cli.js test --config apps\web\playwright.config.ts
python scripts\apsm_validate.py --project .
```

打包 ZIP 前執行：

```powershell
python scripts\project_launcher.py --package
```

## 8. 專案特例

- 前端 dev server 是 Vite `127.0.0.1:5173`。
- 後端預設是 FastAPI `127.0.0.1:8000`。
- Vite 在後端未啟動時出現 `/api/projects` proxy ECONNREFUSED 是預期 fallback 行為，不代表 UI smoke 失敗。
- `OPENAI_API_KEY` 不存在時，UI 可以 fallback 到 mock streaming；live provider 驗證必須另外確認 key。
