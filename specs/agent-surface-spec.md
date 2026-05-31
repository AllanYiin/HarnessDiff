# 規格整理 v 1.2.0

## 技術規格文件

### 假設與前提

- 本規格以 HarnessDiff 現有 Chat MVP 為基準，不推倒既有 `chat` surface、雙 pane streaming、local JSON storage、provider adapter、tool runtime、skill/subagent 管理與 deterministic analysis。
- 使用者已確認 Agent mode 第一版仍採 `NoHarness Agent` vs `Harness Agent` 對照，不做單邊 agent 工作台。
- 第一版 Agent mode 只支援前景 streaming、可取消、artifact 可追溯；不做背景續跑、跨程序 resume、自動排程或 durable checkpoint engine。
- UI 切換放在 TopBar 的 surface segmented control，行為參考 Claude Desktop 類型的模式切換：使用者可清楚看到目前正在 Chat 還是 Agent，但切換不應破壞既有專案歷史。
- 第一版允許 shell/container/code tools，但必須沿用現有 Harness tool policy 與 container sandbox，不得把高風險工具開給 NoHarness Agent。
- 外部研究校準日期為 2026-05-31。參考來源包含 OpenAI Agents SDK result/state surface、LangGraph durable execution / interrupts、OpenTelemetry GenAI metrics、LangSmith complex agent evaluation，以及附件 `deep-research-report (7).md`。

### 背景

HarnessDiff 是本機 localhost 教學工作台，用同一個任務比較 `NoHarness` 與 `Harness` 兩側差異。本規格起草時 repo 只實作 Chat surface，並已在 `SurfaceType` 預留 `workflow / agent / multi_agents`；目前已依本規格完成第一版 Agent surface。

新增 Agent mode 的目的不是把 Chat 變成更複雜的聊天，而是展示同一個任務在「直接 agent」與「有 Harness 控制面的 agent」之間，工具使用、subagent 委派、軌跡可追溯、風險前置檢查、輸出品質與成本的差異。

### 目標

| 目標 | 成功標準 |
|---|---|
| 新增 Agent surface | 使用者可在 TopBar 以 segmented control 切換 Chat / Agent，且建立新 project 時保存 `surface_type`。 |
| 保留 Chat 向前相容 | 既有 Chat 專案、transcript、run streaming、analysis 與 Playwright 測試不需改變使用方式。 |
| Agent 對照體驗 | Agent mode 顯示 `NoHarness Agent` 與 `Harness Agent` 兩側，同一 task 可同時送出並串流比較。 |
| Agent artifact 可追溯 | 每次 agent run 寫入 input、output、events、usage、steps、tool calls、subagent artifacts 與 analysis。 |
| 支援工具與 subagent | Harness Agent 可用 shell/container/code tools、subagent、parallel tools；NoHarness Agent 只能使用低風險標準工具。 |
| 可取消 | 使用者可取消前景執行，UI 顯示 cancelled，local artifacts 保留已完成事件。 |
| 可測試 | 後端 pytest、前端 Vitest、TypeScript build、Playwright desktop/mobile 覆蓋 Chat regression 與 Agent mode smoke。 |

### 範圍

本次要做：

- 新增 `agent` surface 的前後端資料模型、API payload、stream event、artifact layout、analysis 與 UI。
- TopBar 新增 surface segmented control：`Chat` / `Agent`，保留 `Workflow` / `MultiAgents` 為 disabled 或不顯示。
- Agent mode 仍使用兩側 profile：`baseline_agent` / `harness_agent`。
- Agent mode 支援 task objective、optional context、attachments preview、model / reasoning effort、Harness modules、skills、subagents。
- Agent output 一律 streaming，tool/subagent/step events 也應即時顯示。
- Agent 可取消，取消後 run status 為 `cancelled`，不得產生完整 comparison analysis，只能顯示 partial trace summary。

### 不做什麼

- 不在第一版導入完整 LangGraph、任務排隊、背景續跑、跨重啟 resume 或 checkpoint migration。
- 不新增 multi-agent surface；Agent mode 的 subagent 是 manager agent 可使用的工具，不等同 MultiAgents surface。
- 不把 NoHarness Agent 開放 shell/container/code tools。
- 不讓 Agent mode 修改現有 Chat artifact schema 的語意；若需要新增欄位，必須 optional 且有預設。
- 不新增 multi-user auth、外部 database、雲端部署或遠端工作區。

### Persona

| Persona | 需求 | 痛點 |
|---|---|---|
| Harness Engineering 教學者 | 展示有無 Harness 的 agent 執行差異 | 只看最後答案很難教工具軌跡與風險控制 |
| AI app 開發者 | 驗證工具開放、subagent 委派與輸出契約是否有效 | agent 失敗時缺乏可追溯 artifact |
| Demo 製作者 | 快速錄製 Chat vs Agent 的差異 | UI 若把所有資訊攤開，觀眾難以理解重點 |
| 自用研究者 | 比較同一任務在不同控制面下的成本與品質 | 長任務中途取消後仍想保留已發生事件 |

### 系統說明

系統維持現有三層：React UI、FastAPI local API、local JSON storage。新增 Agent mode 時，route layer 仍只呼叫 orchestrator，不解析 provider-specific events；provider adapter 仍維持 `LLMProvider.stream_text()` 的 provider-neutral 邊界。

新增的核心是 `AgentRunOrchestrator` 或 `RunOrchestrator` 的 runtime strategy 分派。Chat run 走現有 profile-per-pane 對話流；Agent run 走 agent profile-per-pane 任務流，會在每個 profile 下額外寫入 `agent_steps.jsonl` 或 `steps/` artifact，並把 tool/subagent events 聚合成可比較的 trajectory。

### 核心流程設計

1. 使用者在 TopBar 選擇 `Agent`。
2. 若目前沒有 project，送出 task 時建立 `surface_type=agent` 的 project；若已有 Chat project，切換到 Agent 時預設建立新的 Agent project，不把不同 surface 的 runs 混在同一 transcript。
3. 使用者輸入 task objective，可附加 context 與檔案；所有附件先在 UI 預覽，圖片維持原始寬高比。
4. 使用者按「執行 Agent 對照」，系統建立 run，profiles 為 `NoHarness Agent` 與 `Harness Agent`。
5. 後端為兩側各啟動一個前景 async task。NoHarness Agent 使用 baseline agent instructions 與受限 tools；Harness Agent 套用 Harness modules、skills/subagent context、tool policy、consequence gate。
6. SSE 串流回傳 `agent_step_started`、`delta`、`tool_call`、`subagent_call`、`agent_step_completed`、`completed`、`error`。
7. UI 左右兩側顯示 final answer streaming，同時用可收合 trace timeline 顯示步驟、工具與 subagent。
8. 兩側完成後寫入 agent analysis；任一側 provider error 則 run `failed` 並不生成完整 analysis。
9. 使用者取消時，前端 abort stream，後端標記 `cancelled`，保留 partial artifacts。

### 開發應注意重點以及應避開誤區

- 不要把 Agent mode 做成第三個 Chat pane。Agent 的核心是 task trajectory 與工具軌跡，不是對話訊息堆疊。
- 不要重建 subagent 系統。既有 `~/.harnessdiff/agents/`、`/api/subagents`、`SubagentToolRuntime`、subagent usage rollup 應被延伸使用。
- 不要讓 Agent run 直接覆用 `input_mode=integrated/independent` 的語意。Agent mode 可保留欄位相容，但應新增 `runtime_type` 或 `surface_type` 判斷。
- 不要在 route handler 寫 provider-specific 邏輯。新增 event type 仍由 orchestrator/provider adapter 轉換後輸出。
- 不要把 shell/container/code tools 開給 baseline profile。NoHarness Agent 是對照組，不應取得 Harness 專屬高能力工具。
- 不要因為第一版不做 durable resume 就忽略 artifact。可追溯 JSON 是後續 durable execution 的前置條件。

### 任務模型與資訊優先級

#### 任務模型表

| 層級 | 內容 | 為何屬於這一層 | 是否必須首屏支援 |
|---|---|---|---|
| 唯一主目標 | 輸入同一個 agent 任務並比較 `NoHarness Agent` 與 `Harness Agent` 的執行結果與軌跡 | Agent mode 的教學價值來自對照，不是單邊完成任務 | 是 |
| 次目標 | 查看步驟、工具、subagent、token/cost、錯誤與 analysis | 使用者需要理解差異原因，但不應搶走主任務焦點 | 部分是 |
| 低頻目標 | 調整 Harness modules、查看完整 skill/subagent 定義、檢查 raw artifact | 只有設定或除錯時需要 | 否 |
| 罕見目標 | 匯出 artifact、查看儲存路徑、檢查 provider raw event | 開發或教學準備時才需要 | 否 |

#### 資訊分類表

| 資訊項目 | 分類 | 使用頻率 | 是否首屏必須 | 不顯示的風險 |
|---|---|---|---|---|
| surface segmented control | action-critical | 高 | 是 | 使用者不知道目前在 Chat 還是 Agent |
| agent task composer | action-critical | 高 | 是 | 無法啟動主任務 |
| NoHarness Agent / Harness Agent panes | action-critical | 高 | 是 | 無法比較兩側差異 |
| streaming status | status-feedback | 高 | 是 | 使用者不知道任務是否仍在跑 |
| compact analysis strip | status-feedback | 中 | 是，完成後顯示 | 完成後缺少成本與軌跡摘要 |
| trace timeline summary | decision-supporting | 中 | 否，預設收合 | 首屏會過度擁擠 |
| full tool arguments | reference | 低 | 否 | 常駐會造成資訊噪音 |
| subagent details | audit/history | 中 | 否，trace 中展開 | 難以追查委派原因 |
| raw JSON paths | reference | 低 | 否 | 一般使用者不需要 |
| provider/tool errors | exception-handling | 中 | 只在錯誤時 | 錯誤時無法回復 |

#### 資訊架構表

| 資訊項目 | 使用頻率 | 是否首屏必須 | 所屬任務階段 | 顯示條件 | 建議容器 | 是否可收合 |
|---|---|---|---|---|---|---|
| surface switch | 高 | 是 | empty/drafting/running/resolved/blocked | 永遠顯示 | topbar segmented control | 否 |
| model/reasoning controls | 中 | 是 | empty/drafting | 非 running | topbar compact controls | 否 |
| Harness settings | 中 | 否 | drafting | 點擊 settings | popover/drawer | 是 |
| task objective | 高 | 是 | empty/drafting | Agent surface | composer textarea | 否 |
| attachments preview | 中 | 是，有附件時 | drafting | 檔案加入後 | inline preview strip | 是 |
| agent panes | 高 | 是 | running/resolved/blocked | run 建立後 | split workspace | 否 |
| step timeline | 中 | 否 | running/resolved/blocked | 點擊 trace tab 或 summary | accordion/tabs | 是 |
| tool/subagent detail | 低 | 否 | running/resolved/blocked | 展開特定 step | drawer/modal | 是 |
| analysis summary | 中 | 是，完成後 | resolved | analysis_ready | compact status strip | 否 |
| raw artifacts | 低 | 否 | resolved/blocked | 點擊 artifact link | drawer/doc link | 是 |

### 狀態模型與揭露策略

#### 狀態矩陣

| State | 進入條件 | 使用者此刻目標 | 必顯資訊 | 隱藏資訊 | 主 CTA | 離開條件 |
|---|---|---|---|---|---|---|
| empty | Agent project 尚無 run | 輸入第一個 agent task | surface switch、task composer、model controls | trace、analysis、raw artifact | 執行 Agent 對照 | task 非空並送出 |
| drafting | 使用者正在編輯 task 或附件 | 準備任務與設定 | task composer、attachments preview、兩側 labels | full trace、raw JSON | 執行 Agent 對照 | 送出、清空或切換 project |
| running | run 已建立且 SSE active | 觀察兩側生成與必要時取消 | panes、streaming status、pause/cancel | full tool args、raw artifacts | 取消 | 兩側 completed / failed / cancelled |
| resolved | 兩側完成且 analysis_ready | 比較輸出與軌跡差異 | final outputs、analysis strip、trace summary | raw tool payload 預設收合 | 新任務 | 新 run 或切換 project |
| blocked | provider/tool/API 錯誤 | 理解錯誤並重試 | error banner、已保存 partial trace、retry affordance | irrelevant settings | 重試 | retry、新任務、切換 project |
| submitted | run created 但尚未收到第一個 event | 等待開始 | pending status、cancel | trace detail | 取消 | 第一個 event / error |
| cancelled | 使用者取消前景任務 | 保留已產生內容並決定下一步 | partial outputs、cancelled status、partial artifact note | full analysis | 新任務 | 新 run 或切換 project |

#### Progressive disclosure 規則

- 首屏只保留 1 個主操作區、1 個狀態區、1 個次要摘要。
- Agent mode 首屏主要視覺群組為：TopBar controls、dual agent workspace、bottom composer/status。
- Step timeline 預設只顯示摘要列：step label、status、duration、tool/subagent count。完整參數與 raw result 需展開。
- `reference` 類資訊如 raw JSON path、provider raw event、完整 instructions 預設不顯示。
- `exception-handling` 只在 blocked/cancelled 顯示，且應放在 panes 上方或對應 pane 內，不常駐。
- Harness settings、skills、subagents 管理維持 drawer/panel，不加入 Agent 首屏。

#### Content audit

| Category | Content |
|---|---|
| must-see-now | surface switch、task composer、NoHarness Agent pane、Harness Agent pane、running/completed status |
| next-step-only | model/reasoning、Harness module toggles、attachments remove、new project |
| error-only | provider error、tool error、container timeout、subagent failure、cancelled note |
| on-demand-reference | full step trace、tool arguments、subagent prompt/output、skill details |
| keep-off-first-viewport | raw JSON artifact path、provider raw event、storage docs、API reference |

#### Deferred blocks

| Block | hidden_now_because | reveal_trigger | container |
|---|---|---|---|
| full tool arguments | 只有除錯需要，常駐會干擾比較 | 展開某個 tool event | drawer/modal |
| subagent full prompt | 多數時候只需知道委派結果 | 點擊 subagent trace item | drawer |
| raw JSON artifacts | 只供開發追溯 | 點擊 artifacts action | drawer/doc link |
| Harness module list | 任務執行時不需調整 | 點擊 settings | popover |
| skills full content | 只有選取技能時需要 | 點擊 skill panel item | existing SkillPanel |

### UI 風格定調與色彩策略

介面維持淺色、專業、工具感，偏向教學工作台而不是行銷頁。Agent mode 不應使用大型 hero、卡片堆疊或裝飾背景；資訊密度要高但層級清楚，讓使用者在錄影或教學時能快速指出差異。

色彩策略：

| 顏色 | 用途 |
|---|---|
| Neutral gray / slate | 主文字、邊框、pane 背景、工作台骨架 |
| Blue | Chat / Agent surface active state、主要 CTA、連線中狀態 |
| Green | completed、tool success、analysis ready |
| Amber | running、waiting、needs attention |
| Red | failed、blocked、tool denied、provider error |

Agent mode 的 `NoHarness Agent` 與 `Harness Agent` 不應用強烈對比色造成閱讀干擾；建議只用細邊框、label badge 與 trace chip 區分。主要 CTA 使用 blue；高風險工具與 blocked state 使用 red/amber。

### 專案目錄規劃

```text
github_repo/
  apps/
    api/
      app/
        models/
          project.py              # SurfaceType 已存在，需保持相容
          run.py                  # 延伸 RunCreate/RunDocument，新增 optional agent config
          agent.py                # 新增 AgentTask、AgentStep、AgentAnalysis 等模型
        routes/
          projects.py             # transcript 需依 surface_type 回傳相容資料
          runs.py                 # create/stream run 依 project.surface_type 分派
        services/
          run_orchestrator.py     # 保留 chat orchestrator 或分出 ChatRunOrchestrator
          agent_orchestrator.py   # 新增 agent runtime strategy
          agent_analysis_builder.py
          subagent_runtime.py     # 延伸現有 subagent artifacts
          chat_tool_runtime.py    # 共用工具 allowlist，新增 agent profile policy
        storage/
          project_store.py        # 新增 agent artifacts 讀寫方法
    web/
      src/
        App.tsx                   # surface state、project 切換與 route branching
        types.ts                  # 新增 SurfaceType、Agent state/types
        api.ts                    # createProject/createRun 支援 surface_type 與 agent payload
        components/
          TopBar.tsx              # surface segmented control
          AgentWorkspace.tsx      # Agent mode 主工作區
          AgentPane.tsx           # 單側 agent output + trace summary
          AgentComposer.tsx       # agent task composer
          AgentTraceTimeline.tsx  # steps/tool/subagent timeline
  specs/
    agent-surface-spec.md         # 本規格
  docs/
    provider-adapter.md           # 補 Agent event boundary
    storage-format.md             # 補 Agent artifact layout
  tests/
    api/
      test_agent_runtime.py
      test_agent_storage.py
```

命名原則：Chat 既有檔案不強制改名；Agent 新檔案使用 `agent_*` 或 `Agent*`。若 refactor `RunOrchestrator`，必須保持 public route behavior 不變，避免 Chat regression。

### 前後端模組

| 模組 | 責任 | 備註 |
|---|---|---|
| Surface Controller | 判斷目前 project surface、UI 顯示與 createProject payload | 前端與後端都需支援 |
| Agent Orchestrator | 管理 agent profile task、stream events、cancel、artifact 寫入 | 第一版前景執行 |
| Agent Tool Policy | 決定 NoHarness/Harness Agent 可用工具 | Harness Agent 可 shell/container/code |
| Agent Step Recorder | 將 step/tool/subagent events 寫入 JSONL | 支援 analysis 與 UI trace |
| Agent Analysis Builder | 比較兩側 final output、step count、tool count、usage、failures | deterministic，不呼叫 LLM |
| Agent UI | dual agent panes、trace timeline、composer、status | 避免 card farm |

### 模組架構圖（SVG）

```svg
<svg viewBox="0 0 1200 720" xmlns="http://www.w3.org/2000/svg">
  <rect width="1200" height="720" fill="#f8fafc"/>
  <text x="48" y="54" font-size="28" font-family="Arial" fill="#0f172a">HarnessDiff Agent Surface 架構</text>
  <rect x="48" y="96" width="250" height="500" rx="8" fill="#ffffff" stroke="#cbd5e1"/>
  <text x="72" y="132" font-size="18" font-family="Arial" fill="#0f172a">React UI</text>
  <text x="72" y="172" font-size="14" font-family="Arial" fill="#334155">TopBar Surface Switch</text>
  <text x="72" y="204" font-size="14" font-family="Arial" fill="#334155">AgentWorkspace</text>
  <text x="72" y="236" font-size="14" font-family="Arial" fill="#334155">AgentPane x 2</text>
  <text x="72" y="268" font-size="14" font-family="Arial" fill="#334155">Trace Timeline</text>
  <text x="72" y="300" font-size="14" font-family="Arial" fill="#334155">Agent Composer</text>
  <rect x="360" y="96" width="310" height="500" rx="8" fill="#ffffff" stroke="#93c5fd"/>
  <text x="384" y="132" font-size="18" font-family="Arial" fill="#0f172a">FastAPI Control Plane</text>
  <text x="384" y="172" font-size="14" font-family="Arial" fill="#334155">/projects surface_type</text>
  <text x="384" y="204" font-size="14" font-family="Arial" fill="#334155">/runs create + stream</text>
  <text x="384" y="236" font-size="14" font-family="Arial" fill="#334155">Runtime Strategy Router</text>
  <text x="384" y="268" font-size="14" font-family="Arial" fill="#334155">ChatRunOrchestrator</text>
  <text x="384" y="300" font-size="14" font-family="Arial" fill="#2563eb">AgentRunOrchestrator</text>
  <text x="384" y="332" font-size="14" font-family="Arial" fill="#334155">AgentAnalysisBuilder</text>
  <rect x="730" y="96" width="360" height="220" rx="8" fill="#ffffff" stroke="#86efac"/>
  <text x="754" y="132" font-size="18" font-family="Arial" fill="#0f172a">Provider / Tools</text>
  <text x="754" y="172" font-size="14" font-family="Arial" fill="#334155">LLMProvider.stream_text</text>
  <text x="754" y="204" font-size="14" font-family="Arial" fill="#334155">ChatToolRuntime</text>
  <text x="754" y="236" font-size="14" font-family="Arial" fill="#334155">Container Code Runtime</text>
  <text x="754" y="268" font-size="14" font-family="Arial" fill="#334155">SubagentToolRuntime</text>
  <rect x="730" y="376" width="360" height="220" rx="8" fill="#ffffff" stroke="#fbbf24"/>
  <text x="754" y="412" font-size="18" font-family="Arial" fill="#0f172a">Local JSON Storage</text>
  <text x="754" y="452" font-size="14" font-family="Arial" fill="#334155">project.json</text>
  <text x="754" y="484" font-size="14" font-family="Arial" fill="#334155">run.json</text>
  <text x="754" y="516" font-size="14" font-family="Arial" fill="#334155">NoHarnessAgent / HarnessAgent</text>
  <text x="754" y="548" font-size="14" font-family="Arial" fill="#334155">events.jsonl / steps.jsonl / usage.json</text>
  <path d="M298 240 L360 240" stroke="#2563eb" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M670 240 L730 208" stroke="#16a34a" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M670 332 L730 484" stroke="#d97706" stroke-width="3" marker-end="url(#arrow)"/>
  <path d="M730 548 L670 548 L670 360" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
      <path d="M0,0 L0,6 L9,3 z" fill="#475569"/>
    </marker>
  </defs>
</svg>
```

### 使用流程

Agent mode 使用流程以「同一任務，兩側 agent 對照」為主：

1. 使用者切到 Agent。
2. 輸入 task objective，例如「分析這個 repo 的測試缺口並提出修補計畫」。
3. 可加入附件，系統即時顯示預覽。圖片縮放維持原始比例。
4. 按「執行 Agent 對照」。
5. 左右兩側同時串流輸出，工具/子任務活動以 timeline chip 顯示。
6. 使用者可取消，或等待兩側完成。
7. 完成後看 compact analysis：總步驟、工具次數、subagent 次數、usage、錯誤、Harness 額外控制面。

### 功能清單（含 CRUD 與 state）

| 功能/物件 | Create | Update | Delete | State |
|---|---|---|---|---|
| Agent project | `POST /projects` with `surface_type=agent` | rename、config_profile | delete project | active/archived 目前不做，沿用 existing |
| Agent run | `POST /projects/{id}/runs` with agent payload | status updates | 不刪單一 run | submitted/running/completed/failed/cancelled |
| Agent profile artifact | run 開始時建立 | delta/event/usage append | 不刪 | pending/running/completed/error |
| Agent step | step event 建立 | completed/error/cancelled event 更新邏輯視圖 | 不刪，append-only | started/completed/error/skipped |
| Tool call | provider function call 建立 | result/error 寫入 | 不刪 | requested/running/completed/error/denied |
| Subagent call | tool call 建立 subagent artifact | delta/usage/event append | 不刪 | running/completed/error |
| Attachment | UI 選檔建立 preview | remove before submit | remove before submit | ready/error |
| Surface selection | UI 切換 | local/project context update | 不適用 | chat/agent |

### G3M

| Goal | Guardrail | Metric |
|---|---|---|
| Agent 對照可理解 | 首屏不超過 3 個主要視覺群組 | Playwright screenshot + manual review |
| Artifact 可追溯 | 所有 step/tool/subagent 寫 JSONL | pytest 驗證 artifact 存在與欄位 |
| Chat 不回歸 | 既有 Chat 測試全通過 | pytest/Vitest/Playwright |
| 工具風險可控 | NoHarness 不取得 shell/container/code/subagent/parallel | pytest 驗證 allowlist |
| 可取消 | abort 後 status=cancelled，UI 不卡住 | e2e cancel test |

### UI 設計

Agent mode 採雙欄工作台：左側 `NoHarness Agent`，右側 `Harness Agent`。每側 pane 上半部顯示 final answer 串流，下半部用 compact timeline 顯示 step summary。詳細工具參數與 subagent 內容採 drawer，不在主畫面常駐。

TopBar segmented control 放在 brand 右側或 brand 區塊下方，樣式比 model controls 更顯眼，但不搶過 task composer。當目前 project 有未完成 run 時，切換 surface 需提示「目前執行中，請先取消或等待完成」。

### UI 元件清單

| 元件 | 用途 | 關鍵屬性 | 互動方式 |
|---|---|---|---|
| SurfaceSegmentedControl | 切換 Chat / Agent | value、disabled states | click |
| AgentWorkspace | Agent mode 主版面 | profiles、run state、analysis | render split layout |
| AgentPane | 單側 agent 結果 | profile、messages、steps、streaming | scroll, expand timeline |
| AgentTraceTimeline | step/tool/subagent 軌跡 | events、filter、expandedStepId | accordion/drawer |
| AgentComposer | 任務輸入 | task、attachments、disabled | submit/cancel |
| AgentStatusStrip | 顯示 running/completed/failed/cancelled | counts、usage、duration | compact chips |
| ToolCallDisclosure | 可復用現有工具 disclosure | tool_call | expand detail |
| SkillPanel | 既有技能/子任務管理 | skills/subagents | drawer |

### 分步導覽策略

第一版不使用 wizard，因為 Agent mode 的主任務是一次輸入 task 並觀察兩側執行。採 tabs/accordion 的位置只限於 trace detail：`Answer` 為預設主視圖，`Trace` 是同 pane 內可切換或收合的次視圖。

若後續加入 durable resume、approval queue 或 checkpoint migration，再考慮拆成 `Task / Running / Review / Artifacts` step navigation。

### 主要畫面示意（SVG）

```svg
<svg viewBox="0 0 1440 960" xmlns="http://www.w3.org/2000/svg">
  <rect width="1440" height="960" fill="#f8fafc"/>
  <rect x="0" y="0" width="1440" height="72" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="32" y="44" font-size="22" font-family="Arial" fill="#0f172a">HarnessDiff</text>
  <rect x="190" y="18" width="176" height="36" rx="8" fill="#eff6ff" stroke="#93c5fd"/>
  <rect x="194" y="22" width="78" height="28" rx="6" fill="#ffffff" stroke="#bfdbfe"/>
  <text x="216" y="41" font-size="13" font-family="Arial" fill="#334155">Chat</text>
  <rect x="276" y="22" width="84" height="28" rx="6" fill="#2563eb"/>
  <text x="302" y="41" font-size="13" font-family="Arial" fill="#ffffff">Agent</text>
  <text x="1020" y="41" font-size="13" font-family="Arial" fill="#475569">模型 gpt-5.4-mini</text>
  <rect x="40" y="96" width="660" height="610" rx="8" fill="#ffffff" stroke="#cbd5e1"/>
  <text x="64" y="132" font-size="18" font-family="Arial" fill="#0f172a">NoHarness Agent</text>
  <rect x="64" y="156" width="612" height="300" rx="6" fill="#f8fafc" stroke="#e2e8f0"/>
  <text x="88" y="194" font-size="14" font-family="Arial" fill="#334155">串流回答區</text>
  <rect x="64" y="480" width="612" height="190" rx="6" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="88" y="514" font-size="14" font-family="Arial" fill="#334155">Trace 摘要：step、tool、duration</text>
  <rect x="740" y="96" width="660" height="610" rx="8" fill="#ffffff" stroke="#93c5fd"/>
  <text x="764" y="132" font-size="18" font-family="Arial" fill="#0f172a">Harness Agent</text>
  <rect x="764" y="156" width="612" height="300" rx="6" fill="#f8fafc" stroke="#e2e8f0"/>
  <text x="788" y="194" font-size="14" font-family="Arial" fill="#334155">串流回答區</text>
  <rect x="764" y="480" width="612" height="190" rx="6" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="788" y="514" font-size="14" font-family="Arial" fill="#334155">Trace 摘要：Harness decision、tool、subagent</text>
  <rect x="40" y="728" width="1360" height="64" rx="8" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="64" y="766" font-size="14" font-family="Arial" fill="#334155">狀態列：running / completed / usage / step count / errors</text>
  <rect x="40" y="816" width="1360" height="104" rx="8" fill="#ffffff" stroke="#cbd5e1"/>
  <text x="64" y="856" font-size="15" font-family="Arial" fill="#334155">Agent task composer</text>
  <rect x="1170" y="846" width="190" height="44" rx="8" fill="#2563eb"/>
  <text x="1218" y="874" font-size="15" font-family="Arial" fill="#ffffff">執行 Agent 對照</text>
</svg>
```

### 非功能需求

| 面向 | 需求 |
|---|---|
| 效能 | Agent streaming 首個 UI event 應在後端收到 provider event 後即時傳出；trace detail 大量 events 時 UI 不應明顯卡頓。 |
| 可靠性 | 任一 profile 失敗時 run failed，不產生完整 analysis；取消時保留 partial artifacts。 |
| 安全性 | Shell/container/code tools 僅 Harness Agent 可用；container 沿用 network disabled、CPU/memory/pid limits。 |
| 可用性 | Agent mode 首屏只保留 task、兩側輸出、狀態；trace 與 raw details 延後揭露。 |
| 可維護性 | Agent runtime 以 strategy/adapter 新增，不把 Chat orchestrator 寫成巨型條件式。 |
| 相容性 | 既有 Chat project transcript、run artifacts 與 analysis builder 不需 migration。 |

### 核心資料模型

新增或延伸模型：

```text
SurfaceType = "chat" | "workflow" | "agent" | "multi_agents"

AgentRunConfig:
  objective: string
  context: string
  max_steps: int = 16
  tool_policy_profile: "baseline_agent" | "harness_agent"
  allow_subagents: bool
  allow_container_tools: bool

AgentStepEvent:
  schema_version: string
  run_id: string
  profile_id: string
  step_id: string
  sequence: int
  type: "agent_step_started" | "agent_step_completed" | "agent_step_error"
  label: string
  status: "running" | "completed" | "error" | "cancelled"
  tool_name?: string
  subagent_id?: string
  elapsed_ms?: int
  token_usage?: object
  created_at: string
```

Artifact layout：

```text
data/projects/{project_id}/
  project.json                 # surface_type=agent
  runs/{run_id}/
    run.json
    NoHarnessAgent/
      input.json
      output.json
      usage.json
      events.jsonl
      steps.jsonl
      subagents/{subagent_id}/...
    HarnessAgent/
      input.json
      output.json
      usage.json
      events.jsonl
      steps.jsonl
      subagents/{subagent_id}/...
    analysis/agent-analysis.json
```

### State 管理與持久化

前端互動 state：

- `surfaceType`
- active project id
- agent draft objective/context
- attachments preview
- expanded trace item
- streaming/cancelled flags

持久化 state：

- `project.json.surface_type`
- `run.json.status`
- profile input/output/events/usage
- `steps.jsonl`
- subagent artifacts
- analysis artifact

恢復流程：

- 開啟歷史 project 時先讀 `project.surface_type`。
- `chat` project 使用現有 transcript reconstruction。
- `agent` project 使用 agent transcript reconstruction：每個 run 顯示 objective、final outputs、step summary、status。
- `running` 狀態若 app 重開，第一版不 resume，顯示為需要人工確認的 interrupted/cancelled-like 狀態，並保留 artifacts。

### API 設計

| API | 方法 | 說明 |
|---|---|---|
| `/api/projects` | POST | 接受 `surface_type`，預設仍為 `chat`。 |
| `/api/projects/{project_id}/transcript` | GET | 回傳 project surface；Chat 舊格式保持，Agent 增加 agent runs fields。 |
| `/api/projects/{project_id}/runs` | POST | 依 project surface 驗證 payload；Agent payload 需 objective。 |
| `/api/runs/{run_id}/stream` | GET | 依 run/project surface 分派 Chat 或 Agent streaming。 |
| `/api/runs/{run_id}/analysis` | GET | Chat 回傳既有 analysis；Agent 回傳 agent analysis。 |

Agent create run request：

```json
{
  "prompt": "分析這個 repo 的測試缺口",
  "input_mode": "integrated",
  "model": "gpt-5.4-mini",
  "reasoning_effort": "medium",
  "surface_payload": {
    "type": "agent",
    "objective": "分析這個 repo 的測試缺口",
    "context": "聚焦 apps/api 與 apps/web",
    "max_steps": 16
  },
  "profiles": [
    {"id": "baseline_agent", "label": "NoHarness Agent", "harness_modules": {}},
    {"id": "harness_agent", "label": "Harness Agent", "harness_modules": {"tool_policy": true}}
  ],
  "attachments": []
}
```

Agent SSE events：

```text
created
agent_step_started
delta
tool_call
subagent_call
agent_step_completed
completed
error
analysis_ready
run_completed
run_failed
```

### 錯誤處理 / 回退策略 / 可觀測性

| 錯誤 | 處理 | UI 提示 | Artifact |
|---|---|---|---|
| provider error | profile error event，run failed | 「其中一側執行失敗，已保留目前軌跡。」 | events.jsonl |
| tool denied | tool_call error，不一定 fail run | 「工具未開放給此 Agent。」 | events.jsonl/steps.jsonl |
| container timeout | tool_call error，可由 agent 決定是否繼續 | 「程式執行逾時。」 | tool event |
| subagent error | subagent event error，manager 收到錯誤結果 | 「子任務失敗，已記錄原因。」 | subagents/... |
| user cancel | run cancelled，不生成 full analysis | 「已取消，已保留已產生內容。」 | run.json status |

可觀測性欄位：

- run duration
- profile duration
- step duration
- tool call count / success / error / denied
- subagent count / usage
- provider usage
- first delta elapsed ms
- cancellation count

### 狀態機

| From | Event | To | 條件 |
|---|---|---|---|
| submitted | stream opened | running | SSE 開始 |
| running | profile completed all | completed | 所有 profiles completed |
| running | profile error | failed | 任一 profile non-recoverable error |
| running | user abort | cancelled | AbortController triggered |
| failed | retry | submitted | 建立新 run，不覆寫舊 run |
| completed | new task | submitted | 建立新 run |

### 通知與背景執行

第一版不做 OS 通知、背景 queue 或重新喚醒。所有執行都是 foreground SSE。取消、重試、失敗告警都以 UI status strip 與 local artifacts 表示。

去重規則：

- 同一按鈕 submit 時若 `submittingProfilesRef` 或 run state 正在 running，忽略重複提交。
- 取消後若使用者重試，必須建立新 run，不覆蓋 cancelled run。

### UI 事件回報

| 事件名稱 | 觸發時機 | 欄位 | 用途 |
|---|---|---|---|
| surface_changed | TopBar surface 切換 | from, to, project_id | 追蹤模式使用 |
| agent_run_submitted | Agent task 送出 | project_id, run_id, profiles | 分析使用流程 |
| agent_run_cancelled | 使用者取消 | run_id, elapsed_ms | 追蹤取消率 |
| agent_trace_expanded | 展開 trace | run_id, profile_id, step_id | 確認 trace 可用性 |
| agent_tool_denied | tool policy denied | tool_name, profile_id | 安全觀測 |
| agent_analysis_ready | analysis 完成 | run_id, metrics | 完成率觀測 |

### UI ↔ API Mapping

| UI | API | 回應 |
|---|---|---|
| SurfaceSegmentedControl 切到 Agent 並新建任務 | `POST /api/projects` | `ProjectDocument.surface_type=agent` |
| AgentComposer 送出 | `POST /api/projects/{id}/runs` | `RunDocument` |
| AgentWorkspace 開始串流 | `GET /api/runs/{run_id}/stream` | SSE events |
| AgentPane 顯示 delta | SSE `delta` | append output text |
| TraceTimeline 顯示 step | SSE `agent_step_*` / `tool_call` / `subagent_call` | append trace item |
| StatusStrip 顯示 analysis | SSE `analysis_ready` | AgentAnalysisDocument |
| HistoryPanel 載入 Agent 專案 | `GET /api/projects/{id}/transcript` | agent transcript |

### UI 狀態保存與重新開始

- `surfaceType` 可記在 localStorage，但若 active project 存在，以 project `surface_type` 為準。
- Agent draft 可在切換 history panel 或 skill panel 時保留；切換 project 時清空。
- 附件 preview 在送出或移除時釋放 object URL。
- 「新任務」清空 composer、attachments、expanded trace 與 analysis，但不刪除歷史 run。
- 「新對話」建立新 project，surface 預設沿用目前 segmented control。

### 建議補充的功能

| 功能 | 優先度 | 原因 |
|---|---|---|
| Agent trace filter | P1 | 大量工具事件時可按 tool/subagent/error 篩選 |
| Artifact export bundle | P1 | 教學/demo 可分享完整 run |
| Durable resume | P2 | 長任務需要跨重啟續跑，第一版先不做 |
| Approval gate UI | P2 | 高風險 shell/container 操作可加入人工核准 |
| Agent eval dataset | P2 | 後續可做 regression gate |

### 驗收條件

- TopBar 有 Chat / Agent segmented control，Chat 既有功能不回歸。
- Agent project 建立後 `project.json.surface_type` 為 `agent`。
- Agent run 會建立 `NoHarnessAgent` 與 `HarnessAgent` artifacts。
- Harness Agent 可使用 shell/container/code/subagent/parallel tools；NoHarness Agent 不可使用 shell/container/code/subagent/parallel tools。
- Agent output 以 streaming 顯示，不等完整結果才出現。
- 取消 Agent run 後，UI 停止串流，run status 為 `cancelled`，partial events 保留。
- 任一 profile provider error 時 run status 為 `failed`，不產生完整 agent comparison analysis。
- 完成 run 會產生 deterministic agent analysis。
- 既有 Chat pytest、Vitest、Playwright 測試仍通過。

### 測試案例

| 類型 | 測試 |
|---|---|
| Backend unit | create agent project、create agent run、invalid surface payload、tool allowlist |
| Backend integration | stream agent run with fake provider events、cancel、provider failure |
| Storage | artifact layout、steps.jsonl append、subagent artifacts rollup |
| Frontend unit | surface switch、agent state reducer、SSE event handling |
| Frontend e2e | Chat to Agent switch、submit agent task、cancel running agent、history reload |
| Regression | Existing Chat independent mode、skill panel、attachments preview、analysis_ready |

### Gherkin / BDD

```gherkin
Feature: Agent mode comparison
  Scenario: User compares NoHarness Agent and Harness Agent
    Given the user is on the HarnessDiff workbench
    When the user switches the surface to Agent
    And submits an agent task
    Then the UI shows NoHarness Agent and Harness Agent panes
    And both panes stream output
    And tool and subagent events appear in the trace summary
    And completed runs produce agent analysis

  Scenario: User cancels an agent run
    Given an agent run is streaming
    When the user clicks cancel
    Then the stream stops
    And the run is marked cancelled
    And partial artifacts remain available
```

### Edge / Abuse cases

| 情境 | 行為 |
|---|---|
| 空 task | 禁用 submit，顯示 inline helper |
| 重複連點 submit | 忽略後續 click，不建立重複 run |
| 切換 surface 時正在 running | 禁用或提示先取消 |
| NoHarness 要求 shell | tool denied，寫入 trace |
| Container timeout | 記錄 tool error，agent 可繼續或失敗 |
| Subagent ID 不存在 | 回傳 subagent_not_allowed |
| 附件格式不支援 | UI preview 顯示 error，不送 provider |
| Provider 中斷 | run failed，保留 partial events |
| SSE JSON parse error | UI 顯示 stream error，後端 artifact 不覆寫 |

### 風險與未決事項

- 第一版不做 durable resume，因此長任務被關閉瀏覽器後只能追溯，不可續跑。這是刻意取捨。
- Agent step event 若完全仰賴 provider raw events，跨 provider 可能不一致；需在 provider-neutral layer 正規化。
- 允許 shell/container/code tools 會提高風險，必須嚴格保持 Harness-only 與 container sandbox。
- Agent analysis 初版 deterministic，可能無法評價語意品質，只能比較結構、成本、軌跡與明確錯誤。

## 非技術規格文件

### 這份規格是寫給誰看的

這份規格寫給要使用 HarnessDiff 做教學、示範或比較的人，也寫給後續要開發這個功能的人。它說明新增 Agent 模式後，使用者會看到什麼、能做什麼，以及哪些地方暫時不做。

### 這個工具能做什麼

新增 Agent 模式後，HarnessDiff 不只可以比較聊天回答，也可以比較兩個 Agent 做同一件事的差異。左邊是沒有 Harness 控制的 Agent，右邊是有 Harness 控制的 Agent。

使用者可以輸入一個任務，例如「幫我分析這個專案缺少哪些測試」，然後同時看到左右兩邊如何處理。畫面會顯示兩邊產出的內容，也會讓使用者查看它們用了哪些工具、是否叫了子任務、哪一邊花費比較多、哪一邊出錯。

### 你會怎麼使用它

你打開 HarnessDiff 後，可以在上方切換 `Chat` 或 `Agent`。選到 `Agent` 後，下方輸入框會變成任務輸入區。

你輸入任務後按下「執行 Agent 對照」，畫面會同時啟動左右兩邊。結果會一段一段出現在畫面上，不需要等整份結果完成才看到。任務執行中可以取消，取消後已經產生的內容和過程記錄仍會保留。

### 你會看到哪些主要畫面

你會看到上方的模式切換、左右兩個 Agent 區塊、下方任務輸入區，以及一條簡短狀態列。左邊標示 `NoHarness Agent`，右邊標示 `Harness Agent`。

每一邊會先顯示主要回答。如果你想看細節，可以展開過程記錄，看到它做了哪些步驟、用了哪些工具、是否有把小任務交給子任務處理。

### 畫面風格與色彩

畫面維持淺色、清楚、偏工具感。主要按鈕用藍色，完成狀態用綠色，等待或執行中用橘黃色，失敗或被阻擋用紅色。

左右兩邊不會用太強烈的顏色互相搶注意力。畫面重點會放在任務輸入、兩邊結果、目前狀態，其他細節會先收起來，需要時再展開。

### 畫面示意（SVG）

```svg
<svg viewBox="0 0 1440 960" xmlns="http://www.w3.org/2000/svg">
  <rect width="1440" height="960" fill="#f8fafc"/>
  <rect x="0" y="0" width="1440" height="72" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="36" y="44" font-size="22" font-family="Arial" fill="#0f172a">HarnessDiff</text>
  <rect x="210" y="18" width="170" height="36" rx="8" fill="#eff6ff" stroke="#93c5fd"/>
  <text x="230" y="42" font-size="14" font-family="Arial" fill="#475569">Chat</text>
  <rect x="292" y="22" width="78" height="28" rx="6" fill="#2563eb"/>
  <text x="314" y="42" font-size="14" font-family="Arial" fill="#ffffff">Agent</text>
  <rect x="40" y="96" width="660" height="610" rx="8" fill="#ffffff" stroke="#cbd5e1"/>
  <text x="64" y="132" font-size="18" font-family="Arial" fill="#0f172a">NoHarness Agent</text>
  <rect x="64" y="160" width="612" height="310" rx="6" fill="#f8fafc" stroke="#e2e8f0"/>
  <text x="88" y="198" font-size="14" font-family="Arial" fill="#334155">左邊產生的結果會在這裡逐段出現</text>
  <rect x="64" y="500" width="612" height="160" rx="6" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="88" y="538" font-size="14" font-family="Arial" fill="#334155">可展開查看處理過程</text>
  <rect x="740" y="96" width="660" height="610" rx="8" fill="#ffffff" stroke="#93c5fd"/>
  <text x="764" y="132" font-size="18" font-family="Arial" fill="#0f172a">Harness Agent</text>
  <rect x="764" y="160" width="612" height="310" rx="6" fill="#f8fafc" stroke="#e2e8f0"/>
  <text x="788" y="198" font-size="14" font-family="Arial" fill="#334155">右邊產生的結果會在這裡逐段出現</text>
  <rect x="764" y="500" width="612" height="160" rx="6" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="788" y="538" font-size="14" font-family="Arial" fill="#334155">可展開查看處理過程</text>
  <rect x="40" y="728" width="1360" height="64" rx="8" fill="#ffffff" stroke="#e2e8f0"/>
  <text x="64" y="766" font-size="14" font-family="Arial" fill="#334155">狀態：正在執行、已完成、已取消或失敗</text>
  <rect x="40" y="816" width="1360" height="104" rx="8" fill="#ffffff" stroke="#cbd5e1"/>
  <text x="64" y="856" font-size="15" font-family="Arial" fill="#334155">在這裡輸入你要兩邊 Agent 同時處理的任務</text>
  <rect x="1170" y="846" width="190" height="44" rx="8" fill="#2563eb"/>
  <text x="1218" y="874" font-size="15" font-family="Arial" fill="#ffffff">執行 Agent 對照</text>
</svg>
```

### 操作流程

1. 在上方選擇 `Agent`。
2. 在下方輸入你想讓 Agent 完成的任務。
3. 如果需要，可以加入圖片或其他檔案；畫面會先讓你確認預覽。
4. 按下「執行 Agent 對照」。
5. 左右兩邊開始產生內容，你可以一邊看結果一邊觀察狀態。
6. 如果不想等，可以按取消。
7. 完成後，你可以比較左右兩邊結果、處理步驟、工具使用與失敗情況。

### 你會看到的提示語

| 情境 | 提示語 |
|---|---|
| 等待開始 | 「正在啟動 Agent 對照...」 |
| 執行中 | 「Agent 正在處理任務，結果會逐段顯示。」 |
| 已完成 | 「Agent 對照完成，可以查看結果與過程摘要。」 |
| 已取消 | 「已取消執行，已保留目前產生的內容。」 |
| 一側失敗 | 「其中一側執行失敗，已保留目前過程記錄。」 |
| 工具不可用 | 「這個 Agent 沒有被允許使用該工具。」 |
| 檔案不支援 | 「這個檔案目前不能使用，請換成支援的格式。」 |

### 限制與注意事項

第一版不支援關掉畫面後繼續剛才的任務。你可以查看已經留下的內容與過程記錄，但不能從中斷處繼續跑。

不是所有工具都會給左右兩邊使用。右邊的 Harness Agent 可以使用更完整的工具，左邊的 NoHarness Agent 會被限制，這樣才能看出有沒有 Harness 控制時的差異。

### 成功完成後會得到什麼

你會得到左右兩邊的結果、簡短比較摘要、處理過程紀錄、工具使用紀錄，以及子任務使用紀錄。這些內容會保存在本機專案紀錄中，之後打開歷史紀錄時可以再看。

### 常見問題與錯誤提示

| 問題 | 說明 |
|---|---|
| 為什麼切換模式後開了新專案？ | 因為聊天比較和 Agent 比較的紀錄型態不同，分開保存比較不容易混亂。 |
| 為什麼左邊不能使用某些工具？ | 左邊是對照組，故意少了 Harness 的保護和工具能力。 |
| 取消後為什麼還看得到一部分內容？ | 系統會保留取消前已經產生的內容，方便你檢查發生了什麼。 |
| 為什麼失敗後沒有完整比較？ | 如果其中一側失敗，完整比較會失真，所以只保留錯誤與已產生內容。 |

## Codex / Claude Code 分階段開發計畫

### Stage 0：建立 Agent surface 骨架與相容規範

- 目標：新增 Agent surface 的資料型別、檔案邊界、測試骨架與文件占位，不改變 Chat 行為。
- 前置條件：既有 Chat 測試可執行；不要調整 provider adapter 實作細節。

Codex Instructions

```text
[建議貼用方式]
直接貼給 Codex。長期規則同步到 github_repo/AGENTS.md：Agent surface 不得破壞 Chat surface，LLM 輸出必須 Streaming。

[任務範圍]
做：新增 Agent surface 型別、模型占位、測試骨架、文件占位。
不做：不實作完整 Agent runtime，不改 Chat UI 行為。

[需修改/新增的檔案清單]
- github_repo/apps/api/app/models/agent.py
- github_repo/apps/api/app/models/run.py
- github_repo/apps/web/src/types.ts
- github_repo/docs/storage-format.md
- github_repo/docs/provider-adapter.md
- github_repo/tests/api/test_agent_runtime.py

[具體步驟]
1. 新增 agent models：AgentRunConfig、AgentStepEvent、AgentAnalysisDocument。
2. 在 RunCreate/RunDocument 加 optional surface_payload，保持舊 payload 相容。
3. 前端 types 加 SurfaceType 與 Agent 相關型別。
4. 文件補 Agent artifact layout 與 event names。
5. 新增空白但可執行的 pytest skeleton，先驗證 import 與 model validation。

[輸出格式要求]
列出修改檔案、相容性說明、測試結果。

[測試要求]
執行 python -m pytest tests/api/test_agent_runtime.py。

[驗收標準 DoD]
Chat API payload 不需新增欄位也能通過。
Agent model validation 有基本測試。
涉及 LLM 的後續輸出規則已明寫必須 Streaming。
```

Claude Code Instructions

```text
[建議貼用方式]
直接貼給 Claude Code。若作為長期專案規則，寫入 CLAUDE.md：不要破壞 Chat surface；Agent output 一律逐段顯示。

[任務範圍]
建立 Agent surface 基礎型別與文件，不做 runtime。

[需修改/新增的檔案清單]
- apps/api/app/models/agent.py
- apps/api/app/models/run.py
- apps/web/src/types.ts
- docs/storage-format.md
- docs/provider-adapter.md
- tests/api/test_agent_runtime.py

[具體步驟]
1. 檢查現有 SurfaceType 與 RunCreate。
2. 新增 optional agent payload，避免舊 Chat request 失效。
3. 建立 Agent event/type 文件。
4. 補最小模型測試。

[輸出格式要求]
回報差異、風險、測試指令與結果。

[測試要求]
python -m pytest tests/api/test_agent_runtime.py

[驗收標準 DoD]
舊 Chat request 相容。
Agent surface 型別可被後續 stage 使用。
若涉及智慧引擎輸出，必須逐段顯示。
```

- 風險與回滾方式：若 RunCreate 破壞舊 request，回滾 `run.py` 的 payload 變更，保留獨立 `agent.py`。

### Stage 1：加入 TopBar surface segmented control 與 project surface 行為

- 目標：UI 可切換 Chat / Agent；建立新 project 時保存 surface_type；Chat 專案載入仍走 Chat UI。
- 前置條件：Stage 0 完成。

Codex Instructions

```text
[建議貼用方式]
直接貼給 Codex。

[任務範圍]
做：TopBar surface segmented control、frontend createProject 支援 surface_type、project transcript normalize surface。
不做：不實作 Agent streaming runtime。

[需修改/新增的檔案清單]
- github_repo/apps/web/src/components/TopBar.tsx
- github_repo/apps/web/src/App.tsx
- github_repo/apps/web/src/api.ts
- github_repo/apps/web/src/types.ts
- github_repo/apps/web/src/components/SurfaceSegmentedControl.tsx
- github_repo/apps/web/src/api.test.ts

[具體步驟]
1. 新增 SurfaceSegmentedControl，選項 Chat / Agent。
2. App 管理 surfaceType；active project 存在時以 project.surface_type 為準。
3. createProject(name, surfaceType) 傳送 surface_type。
4. History project normalize 加 surface_type。
5. running 時禁止切換 surface 或提示先取消。

[輸出格式要求]
說明 UI 行為與 Chat 相容性。

[測試要求]
node apps/web/node_modules/vitest/vitest.mjs run src --root apps/web

[驗收標準 DoD]
Chat 預設仍可用。
Agent 切換不造成空白頁。
切換控制項在桌面與手機不溢出。
LLM 輸出相關 UI 不得改成非 Streaming。
```

Claude Code Instructions

```text
[建議貼用方式]
直接貼給 Claude Code。

[任務範圍]
新增上方模式切換與新專案模式保存。

[需修改/新增的檔案清單]
- apps/web/src/components/TopBar.tsx
- apps/web/src/components/SurfaceSegmentedControl.tsx
- apps/web/src/App.tsx
- apps/web/src/api.ts
- apps/web/src/types.ts

[具體步驟]
1. 建立 segmented control。
2. 將 Chat / Agent 狀態接到 App。
3. 建立新專案時帶入目前模式。
4. 歷史專案載入時恢復模式。
5. 加測試確認既有 Chat 未壞。

[輸出格式要求]
列出改動與測試結果。

[測試要求]
執行前端 Vitest，必要時補 component test。

[驗收標準 DoD]
使用者能清楚看到目前模式。
切換不會清掉正在執行的內容。
內容生成仍必須逐段顯示。
```

- 風險與回滾方式：若 TopBar 版面破壞 mobile，可先保留 surface control 但隱藏 disabled future options。

### Stage 2：實作 Agent runtime strategy 與 artifact 寫入

- 目標：後端可執行 Agent run，兩側 profile 串流、寫入 output/events/steps/usage。
- 前置條件：Stage 0-1 完成。

Codex Instructions

```text
[建議貼用方式]
直接貼給 Codex。

[任務範圍]
做：AgentRunOrchestrator、runtime strategy router、agent artifacts。
不做：不做 durable resume，不做 background queue。

[需修改/新增的檔案清單]
- github_repo/apps/api/app/services/agent_orchestrator.py
- github_repo/apps/api/app/services/run_orchestrator.py
- github_repo/apps/api/app/routes/runs.py
- github_repo/apps/api/app/storage/project_store.py
- github_repo/apps/api/app/models/agent.py
- github_repo/tests/api/test_agent_runtime.py
- github_repo/tests/api/test_agent_storage.py

[具體步驟]
1. routes/runs.py 依 project.surface_type 分派 Chat/Agent orchestrator。
2. AgentRunOrchestrator 以 profiles 建立兩個 async task。
3. 每個 profile prepare_agent_profile_run，寫 input/output/events/steps。
4. provider event delta 寫 output，tool/subagent/step event 寫 events/steps。
5. CancelledError 更新 run status=cancelled。
6. 任一 profile error 更新 run failed，不寫完整 analysis。

[輸出格式要求]
列出 event types、artifact layout、測試結果。

[測試要求]
python -m pytest tests/api/test_agent_runtime.py tests/api/test_agent_storage.py

[驗收標準 DoD]
Agent output 透過 SSE Streaming。
取消會保留 partial artifacts。
Chat stream_run 行為不變。
```

Claude Code Instructions

```text
[建議貼用方式]
直接貼給 Claude Code。

[任務範圍]
新增 Agent 執行流程與本機紀錄，不做背景續跑。

[需修改/新增的檔案清單]
- apps/api/app/services/agent_orchestrator.py
- apps/api/app/routes/runs.py
- apps/api/app/storage/project_store.py
- apps/api/app/models/agent.py
- tests/api/test_agent_runtime.py
- tests/api/test_agent_storage.py

[具體步驟]
1. 新增 AgentRunOrchestrator。
2. 依 project 模式選擇 Chat 或 Agent 流程。
3. 寫入 Agent 專屬紀錄。
4. 保留取消與失敗狀態。
5. 補測試。

[輸出格式要求]
回報修改點、測試、已知限制。

[測試要求]
pytest 指定 Agent runtime/storage 測試。

[驗收標準 DoD]
兩側 Agent 都逐段顯示。
取消後不產生完整比較。
舊聊天流程不受影響。
```

- 風險與回滾方式：若分派導致 Chat regression，保留 Agent route code 但先用 feature flag 關閉 Agent stream。

### Stage 3：套用 Agent tool policy、shell/container/code 與 subagent trace

- 目標：Harness Agent 可用高能力工具與 subagent，NoHarness Agent 保持受限；所有工具與 subagent 可追溯。
- 前置條件：Stage 2 完成。

Codex Instructions

```text
[建議貼用方式]
直接貼給 Codex。

[任務範圍]
做：Agent profile tool allowlist、Harness-only shell/container/code/subagent/parallel、trace normalization。
不做：不新增未 sandbox 的工具。

[需修改/新增的檔案清單]
- github_repo/apps/api/app/services/agent_orchestrator.py
- github_repo/apps/api/app/services/chat_tool_runtime.py
- github_repo/apps/api/app/services/subagent_runtime.py
- github_repo/docs/provider-adapter.md
- github_repo/tests/api/test_tool_runtime.py
- github_repo/tests/api/test_subagent_runtime.py
- github_repo/tests/api/test_agent_runtime.py

[具體步驟]
1. 定義 baseline_agent excluded tools：shell、container、subagent、parallel。
2. Harness Agent 啟用 tool_policy 時取得 full tool set。
3. Subagent artifacts 沿用現有 storage path，必要時支援 Agent profile ids。
4. 將 tool_call/subagent_call event 正規化到 Agent trace。
5. 測試 NoHarness denied 與 Harness allowed。

[輸出格式要求]
列出 allowlist/denylist 與安全邊界。

[測試要求]
python -m pytest tests/api/test_tool_runtime.py tests/api/test_subagent_runtime.py tests/api/test_agent_runtime.py

[驗收標準 DoD]
NoHarness Agent 無法用 shell/container/code/subagent/parallel。
Harness Agent 可用既有 sandboxed container code tool。
所有 LLM/tool/subagent 輸出維持 Streaming 或事件即時回報。
```

Claude Code Instructions

```text
[建議貼用方式]
直接貼給 Claude Code。

[任務範圍]
設定兩側 Agent 工具差異，並留下可查看紀錄。

[需修改/新增的檔案清單]
- apps/api/app/services/agent_orchestrator.py
- apps/api/app/services/chat_tool_runtime.py
- apps/api/app/services/subagent_runtime.py
- docs/provider-adapter.md
- tests/api/test_tool_runtime.py
- tests/api/test_subagent_runtime.py

[具體步驟]
1. 檢查現有工具清單。
2. 設定左側限制與右側完整工具。
3. 確認子任務紀錄可寫入。
4. 補測試確認限制生效。

[輸出格式要求]
回報工具權限表與測試結果。

[測試要求]
pytest 工具與子任務相關測試。

[驗收標準 DoD]
工具權限符合規格。
右側可使用受保護的程式執行能力。
生成內容仍逐段顯示。
```

- 風險與回滾方式：若 container runtime 測試環境不穩，保留 allowlist 邏輯，將 live container 測試標記為需要 Docker 的整合測試。

### Stage 4：建立 Agent UI workspace、composer 與 trace timeline

- 目標：Agent mode 有可用雙 pane UI、任務輸入、取消、trace summary 與延後揭露。
- 前置條件：Stage 1-3 完成。

Codex Instructions

```text
[建議貼用方式]
直接貼給 Codex。

[任務範圍]
做：AgentWorkspace、AgentPane、AgentComposer、AgentTraceTimeline、SSE event handling。
不做：不大改 ChatPane/Composer，必要時抽共用小元件。

[需修改/新增的檔案清單]
- github_repo/apps/web/src/App.tsx
- github_repo/apps/web/src/components/AgentWorkspace.tsx
- github_repo/apps/web/src/components/AgentPane.tsx
- github_repo/apps/web/src/components/AgentComposer.tsx
- github_repo/apps/web/src/components/AgentTraceTimeline.tsx
- github_repo/apps/web/src/api.ts
- github_repo/apps/web/src/types.ts
- github_repo/apps/web/src/styles.css
- github_repo/apps/web/e2e/harnessdiff.spec.ts

[具體步驟]
1. App 依 surfaceType render Chat workspace 或 Agent workspace。
2. AgentComposer 支援 objective、attachments preview、submit、cancel。
3. AgentPane 顯示 streaming output 與 compact trace。
4. Trace detail 用 accordion/drawer 延後揭露。
5. 將 agent SSE events 更新到 Agent state。
6. 確認 mobile 不溢出。

[輸出格式要求]
回報 UI 狀態模型、主要元件與測試結果。

[測試要求]
node apps/web/node_modules/vitest/vitest.mjs run src --root apps/web
corepack pnpm --dir apps/web run build
Playwright agent smoke test

[驗收標準 DoD]
Agent mode 首屏不超過 3 個主要視覺群組。
有且只有一個主 CTA。
回答逐段顯示。
取消可用。
Chat UI 不回歸。
```

Claude Code Instructions

```text
[建議貼用方式]
直接貼給 Claude Code。

[任務範圍]
新增 Agent 畫面與互動，保持聊天畫面原樣。

[需修改/新增的檔案清單]
- apps/web/src/App.tsx
- apps/web/src/components/AgentWorkspace.tsx
- apps/web/src/components/AgentPane.tsx
- apps/web/src/components/AgentComposer.tsx
- apps/web/src/components/AgentTraceTimeline.tsx
- apps/web/src/styles.css
- apps/web/e2e/harnessdiff.spec.ts

[具體步驟]
1. 建立 Agent 專用工作區。
2. 接上任務送出與取消。
3. 顯示左右結果與過程摘要。
4. 細節用展開方式顯示，不常駐。
5. 補桌面與手機測試。

[輸出格式要求]
回報畫面改動、測試結果與任何限制。

[測試要求]
Vitest、build、Playwright。

[驗收標準 DoD]
使用者可完成一次 Agent 對照。
畫面不擠、不溢出。
內容逐段顯示。
```

- 風險與回滾方式：若 App.tsx 過大，先抽 Agent hook；若 mobile 版面不穩，Agent panes 在 mobile 改上下堆疊但保留同一主任務。

### Stage 5：新增 deterministic Agent analysis 與 history reconstruction

- 目標：Agent run 完成後可看到比較摘要；歷史載入能重建 Agent runs。
- 前置條件：Stage 4 完成。

Codex Instructions

```text
[建議貼用方式]
直接貼給 Codex。

[任務範圍]
做：agent_analysis_builder、analysis API branching、Agent transcript reconstruction。
不做：不呼叫 LLM 評分語意品質。

[需修改/新增的檔案清單]
- github_repo/apps/api/app/services/agent_analysis_builder.py
- github_repo/apps/api/app/routes/runs.py
- github_repo/apps/api/app/routes/projects.py
- github_repo/apps/api/app/storage/project_store.py
- github_repo/apps/web/src/api.ts
- github_repo/apps/web/src/components/AgentWorkspace.tsx
- github_repo/tests/api/test_agent_runtime.py
- github_repo/tests/api/test_projects.py

[具體步驟]
1. 讀取 run/profile output/usage/events/steps/subagents。
2. 產生 AgentAnalysisDocument：usage delta、step count、tool count、subagent count、errors、Harness-only controls。
3. `/runs/{id}/analysis` 依 surface 回傳對應 analysis。
4. project transcript 對 Agent run 回傳 objective、outputs、step summary。
5. 前端 history load 可重建 Agent workspace。

[輸出格式要求]
列出 analysis 欄位與測試結果。

[測試要求]
python -m pytest tests/api/test_agent_runtime.py tests/api/test_projects.py

[驗收標準 DoD]
completed Agent run 有 agent-analysis.json。
failed/cancelled run 不產生完整比較。
歷史載入不誤用 Chat transcript。
```

Claude Code Instructions

```text
[建議貼用方式]
直接貼給 Claude Code。

[任務範圍]
新增 Agent 完成後的比較摘要與歷史載入。

[需修改/新增的檔案清單]
- apps/api/app/services/agent_analysis_builder.py
- apps/api/app/routes/runs.py
- apps/api/app/routes/projects.py
- apps/web/src/api.ts
- apps/web/src/components/AgentWorkspace.tsx
- tests/api/test_agent_runtime.py
- tests/api/test_projects.py

[具體步驟]
1. 從本機紀錄整理左右差異。
2. 完成時寫入比較摘要。
3. 歷史紀錄載入時恢復 Agent 畫面。
4. 失敗或取消時只顯示部分紀錄。

[輸出格式要求]
回報摘要欄位與測試結果。

[測試要求]
pytest 指定測試。

[驗收標準 DoD]
完成後可看比較摘要。
歷史紀錄可重新打開。
內容產生仍是逐段顯示。
```

- 風險與回滾方式：若 transcript response 變更影響 Chat，採 additive fields，前端 normalize 對未知欄位容錯。

### Stage 6：補齊整合測試 / 回歸測試 / 邊界測試

- 目標：確認 Chat 不回歸，Agent mode 主要路徑、取消、錯誤、工具限制、mobile layout 都受測。
- 前置條件：Stage 1-5 完成。

Codex Instructions

```text
[建議貼用方式]
直接貼給 Codex。

[任務範圍]
做：補完整測試與修正測試發現的缺口。
不做：不新增功能。

[需修改/新增的檔案清單]
- github_repo/tests/api/test_agent_runtime.py
- github_repo/tests/api/test_agent_storage.py
- github_repo/tests/api/test_tool_runtime.py
- github_repo/apps/web/src/*.test.ts
- github_repo/apps/web/e2e/harnessdiff.spec.ts
- github_repo/docs/troubleshooting.md

[具體步驟]
1. Backend 測試：success、provider failure、cancel、tool denied、subagent error。
2. Frontend 測試：surface switch、agent SSE handling、cancel UI。
3. Playwright：desktop/mobile Agent smoke 與 Chat regression。
4. 確認測試不以假成功掩蓋 backend/API/provider 契約。
5. 修正測試發現問題。

[輸出格式要求]
列出測試矩陣、執行指令、結果與修正摘要。

[測試要求]
python -m pytest
node apps/web/node_modules/vitest/vitest.mjs run src --root apps/web
corepack pnpm --dir apps/web run build
corepack pnpm --dir apps/web exec playwright test

[驗收標準 DoD]
所有既有 Chat 測試通過。
Agent success/cancel/failure/tool policy 有測試。
LLM/Agent 輸出仍以 Streaming 驗證。
```

Claude Code Instructions

```text
[建議貼用方式]
直接貼給 Claude Code。

[任務範圍]
補測試與修正測試發現問題，不加新功能。

[需修改/新增的檔案清單]
- tests/api/test_agent_runtime.py
- tests/api/test_agent_storage.py
- tests/api/test_tool_runtime.py
- apps/web/src/*.test.ts
- apps/web/e2e/harnessdiff.spec.ts
- docs/troubleshooting.md

[具體步驟]
1. 補後端成功、失敗、取消測試。
2. 補工具權限測試。
3. 補畫面切換與手機畫面測試。
4. 跑完整測試。
5. 修正回歸。

[輸出格式要求]
提供測試結果與修正清單。

[測試要求]
pytest、Vitest、build、Playwright。

[驗收標準 DoD]
測試能防止聊天功能被破壞。
Agent 主要流程可被自動驗證。
生成內容逐段顯示的行為被測到。
```

- 風險與回滾方式：若 Playwright 受環境影響，保留 backend/frontend unit 作為必跑，Playwright 標出環境需求但不得刪除。

### Stage 7：文件化與交付

- 目標：更新 README、架構、儲存格式、troubleshooting 與 release checklist，交付可維護說明。
- 前置條件：Stage 6 通過。

Codex Instructions

```text
[建議貼用方式]
直接貼給 Codex。

[任務範圍]
做：文件化 Agent mode 使用、架構、限制、測試與已知問題。
不做：不改功能邏輯。

[需修改/新增的檔案清單]
- github_repo/README.md
- github_repo/docs/architecture.md
- github_repo/docs/storage-format.md
- github_repo/docs/provider-adapter.md
- github_repo/docs/troubleshooting.md
- github_repo/docs/release-checklist.md
- github_repo/specs/product-spec.md
- github_repo/specs/requirements.md
- github_repo/specs/stage-plan.md

[具體步驟]
1. README 補 Chat / Agent surfaces 與 quickstart。
2. architecture 補 runtime strategy。
3. storage-format 補 Agent artifacts。
4. provider-adapter 補 Agent event boundary。
5. troubleshooting 補 Agent 失敗與取消。
6. release checklist 補 Agent 測試 gate。

[輸出格式要求]
列出文件變更與最終驗收結果。

[測試要求]
至少跑 markdown 相關檢查若存在；否則跑完整測試摘要引用 Stage 6 結果。

[驗收標準 DoD]
文件清楚說明 Agent mode 限制：第一版前景 streaming、可取消、可追溯，不支援背景續跑。
Codex/Claude 後續接手能找到規格、架構與測試指令。
所有 LLM/Agent 輸出規則仍要求 Streaming。
```

Claude Code Instructions

```text
[建議貼用方式]
直接貼給 Claude Code。長期文件規則可同步到 CLAUDE.md。

[任務範圍]
更新交付文件，不改功能。

[需修改/新增的檔案清單]
- README.md
- docs/architecture.md
- docs/storage-format.md
- docs/provider-adapter.md
- docs/troubleshooting.md
- docs/release-checklist.md
- specs/product-spec.md
- specs/requirements.md
- specs/stage-plan.md

[具體步驟]
1. 補使用說明。
2. 補架構與紀錄格式。
3. 補限制與常見錯誤。
4. 補測試與交付清單。

[輸出格式要求]
回報文件清單與交付狀態。

[測試要求]
確認文件連結與指令正確；引用 Stage 6 的完整測試結果。

[驗收標準 DoD]
新開發者能照文件理解 Agent mode。
已知限制清楚。
生成內容逐段顯示的規則沒有遺漏。
```

- 風險與回滾方式：文件變更若與實作不一致，以實作與測試為準修正文檔，不修改已通過功能。

## 來源與查證日期

- 查證日期：2026-05-31。
- OpenAI Agents SDK results/state: https://openai.github.io/openai-agents-python/results/
- OpenAI Agents SDK guide: https://platform.openai.com/docs/guides/agents-sdk
- LangGraph durable execution: https://docs.langchain.com/oss/python/langgraph/durable-execution
- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- OpenTelemetry GenAI metrics: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/
- LangGraph GitHub: https://github.com/langchain-ai/langgraph
- OpenTelemetry GenAI conventions repo: https://github.com/open-telemetry/semantic-conventions-genai
