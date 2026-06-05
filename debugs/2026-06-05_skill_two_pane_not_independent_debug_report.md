# Debug Report — skill_two_pane_not_independent

- **日期**：2026-06-05
- **影響範圍**：HarnessDiff skill routing、NoHarness/Harness pane independence、Agent surface skill invocation
- **嚴重度**：降級

## 本次 debug 規模（代理指標）

| 指標 | 數值 |
|---|---:|
| 工具呼叫（Read/Grep/Glob） | 約 18 |
| 工具呼叫（Edit/Write） | 6 |
| 工具呼叫（Bash/PowerShell） | 約 10 |
| 涉及檔案數（讀 + 寫） | 約 16 |
| 實際修改檔案數（git diff） | 8 |
| 本次 skill-pane 修正檔案數 | 5 |
| 嘗試但否決的方案數 | 3 |

> 註：`git diff --name-only` 目前列出 8 個修改檔，其中 `pdf_attachments.py`、`styles.css`、`tests/api/test_tool_runtime.py` 與 `tests/api/test_runs.py` 內的 PDF surrogate 測試片段並非本次 skill pane 修正的核心範圍，未在本報告中歸入已確認清理項目。

---

## 症狀

使用者觀察到：NoHarness pane 與 Harness pane 觸發的 skill 總是完全相同。

### 最小重現

1. 在 integrated mode 送出同一個 prompt，讓 NoHarness 與 Harness 兩個 profile 同時執行。
2. prompt 觸發 skill selection。
3. 觀察兩邊 assistant message 或 profile events 中的 `skill_invocation`。

### 預期

- NoHarness 與 Harness 是兩個獨立 pane。
- NoHarness：只做 LLM-only skill selection，不套 deterministic fallback。
- Harness：做 LLM selection，並保留 deterministic guard/fallback。
- 兩邊可以依 profile capability 選到不同 skill。

### 實際

- 舊實作在整個 run 開始時只呼叫一次 `_select_skills_for_run(run)`。
- 同一份 `selected_skill_ids` 被套入每一個 profile。
- 因此 NoHarness 與 Harness 的 skill context、`skill_invocation` 事件完全相同。

## 試過什麼、為何無效

1. **假設**：這可能只是前端把同一份 skill invocation 顯示到兩個 pane。
   - **動作**：檢查 `App.tsx` streaming event handling 與 profile message update。
   - **結果**：前端是依 `event.profile_id` 更新對應 assistant message。
   - **為何無效**：UI 沒有把同一 event 誤掛兩邊；後端是真的對每個 profile 寫入同一組 skill events。

2. **假設**：只要 integrated submit 改成兩個獨立 run 就能解。
   - **動作**：檢查 `App.tsx` submit flow。
   - **結果**：integrated mode 確實把所有 active profiles 放入同一個 run，但這是產品上用來比較 pane 的正常行為。
   - **為何無效**：問題不是 integrated run 本身，而是 run 裡的 skill selection state 被放在 profile 外層。把 integrated mode 拆成兩個 run 會破壞原本同題比較的資料結構。

3. **假設**：只改一般 chat orchestrator 就足夠。
   - **動作**：檢查 `AgentRunOrchestrator`。
   - **結果**：Agent surface 也沿用 run-level selection pattern。
   - **為何無效**：若只改 `RunOrchestrator`，Agent mode 仍會復發同一問題。

## 最終解法與原因

### 根因（Root Cause）

skill selection 的狀態邊界放錯層級。

NoHarness 與 Harness 的差異來自 profile：`harness_modules`、tool policy、PDF mode、AGENTS context、guardrails 都是在 `run_profile(profile)` 內決定。但舊版 skill selection 在 profile 之前先做一次，等於把 profile-specific policy 退化成 run-global state。只要 selector 不知道 profile，就不可能實作「NoHarness LLM-only、Harness LLM + fallback」這種不同 policy。

Google SRE 對 postmortem 的核心要求是紀錄 incident impact、actions、root cause 與 prevention，並保持 blameless；本報告也採用這個方向，把問題定位在 state boundary 設計，而不是歸咎到個人操作。

### 解法

- **變動**：[apps/api/app/services/run_orchestrator.py](../apps/api/app/services/run_orchestrator.py)
  - 將 `selected_skills = await self._select_skills_for_run(run)` 從 run 外層移入 `run_profile(profile)`。
  - 新增 `_select_skills_for_profile(run, profile)`。
  - 新增 `_skill_selection_policy_for_profile(profile)`。
  - NoHarness/baseline 回傳 `llm_only`；Harness 回傳 `llm_with_deterministic_fallback`。

- **變動**：[apps/api/app/services/agent_orchestrator.py](../apps/api/app/services/agent_orchestrator.py)
  - 同步把 Agent mode 的 skill selection 移入 profile 執行路徑。
  - 重用 `_profile_has_harness_context(profile)`，避免一般 chat 與 Agent surface policy 分裂。

- **變動**：[apps/api/app/providers/base.py](../apps/api/app/providers/base.py)
  - 擴充 `SkillSelectionRequest`，加入 `profile_id`、`profile_label`、`harness_modules`、`selection_policy`。
  - 這些欄位都有預設值，保留舊呼叫相容性。

- **變動**：[apps/api/app/providers/openai_responses.py](../apps/api/app/providers/openai_responses.py)
  - selector prompt 加入 profile context。
  - selector input JSON 帶入 profile id、label、harness modules 與 selection policy。

- **變動**：[tests/api/test_runs.py](../tests/api/test_runs.py)
  - `SkillSelectingProvider` 支援依 `profile_id` 回傳不同 selected skills。
  - 新增 `test_integrated_run_selects_skills_independently_per_profile`。
  - 更新 deterministic fallback 測試：baseline 不應收到 fallback skill；harness 應收到 fallback skill。

### 為何這個解法正確

skill 是否應該被啟用取決於兩層因素：

1. 使用者 prompt 是否符合 skill metadata。
2. 目前 pane/profile 的 policy 與 capability。

舊實作只看第 1 點，所以兩個 pane 永遠共享結果。新實作把第 2 點納入 `SkillSelectionRequest` 與 fallback policy，使 selector 與 deterministic guard 都在 profile 邊界內運作。

### 驗證

已執行：

```text
python -m pytest tests\api\test_runs.py tests\api\test_openai_provider.py
```

結果：

```text
45 passed
```

已執行：

```text
python -m pytest tests\api\test_agent_runtime.py
```

結果：

```text
10 passed
```

第一次測試在 sandbox 內 collection 失敗，原因是 `toolanything` 初始化要寫入 `logs/toolanything.log`；依 sandbox policy 升權重跑後通過。

## 預防建議

- **偵測**：保留 `test_integrated_run_selects_skills_independently_per_profile`，防止未來又把 profile-level state 移回 run-level。
- **護欄**：凡是依 `harness_modules`、tool availability、AGENTS context、PDF mode、guardrails 判斷的資料，都應優先放在 profile 層，不應預設為 run-level。
- **流程**：新增任何 routing/selection 功能時，同時檢查一般 chat 與 Agent surface，避免只修其中一條 orchestrator。
- **文件**：在 routing 架構文件補上原則：integrated run 可以共享 prompt 與 attachments，但 selection/result/context 應以 profile 為界。

## 相關檔案

- [apps/api/app/services/run_orchestrator.py](../apps/api/app/services/run_orchestrator.py) — 一般 chat profile-level skill selection。
- [apps/api/app/services/agent_orchestrator.py](../apps/api/app/services/agent_orchestrator.py) — Agent mode profile-level skill selection。
- [apps/api/app/providers/base.py](../apps/api/app/providers/base.py) — `SkillSelectionRequest` schema。
- [apps/api/app/providers/openai_responses.py](../apps/api/app/providers/openai_responses.py) — selector prompt/input profile context。
- [tests/api/test_runs.py](../tests/api/test_runs.py) — regression coverage。
- `debugs/archive/2026-06-05_skill_two_pane_not_independent/` — 無封存檔案；本次沒有採用後又丟棄的替代實作。

## 清理與待確認

### 已清理

- 無。未發現可 100% 確認是本次 skill pane debug 加入且應刪除的 `console.log`、臨時 early return、註解舊碼或 hard-coded fixture。

### 不清理，待使用者確認

以下項目存在於工作樹，但無法確認全都屬於本次 skill pane debug，依 prompt 契約不擅自刪除：

1. `apps/api/app/services/pdf_attachments.py`
2. `apps/web/src/styles.css`
3. `tests/api/test_tool_runtime.py`
4. `tests/api/test_runs.py` 內 PDF surrogate 相關新增測試片段
5. `skill-panel-live-fixed.png`
6. `skill-panel-runtime.png`
7. `skill-panel-tools-runtime.png`

## Diff 檢視

目前 `git diff --stat`：

```text
 apps/api/app/providers/base.py              |   4 +
 apps/api/app/providers/openai_responses.py  |   7 ++
 apps/api/app/services/agent_orchestrator.py |  15 +--
 apps/api/app/services/pdf_attachments.py    |  15 ++-
 apps/api/app/services/run_orchestrator.py   |  48 ++++++--
 apps/web/src/styles.css                     |   9 +-
 tests/api/test_runs.py                      | 174 ++++++++++++++++++++++++++--
 tests/api/test_tool_runtime.py              |  49 ++++++++
 8 files changed, 293 insertions(+), 28 deletions(-)
```

請在進入 `/clear` 前檢視目前 diff。若要我繼續清理上述待確認項目，請指明項目編號；若 diff 正確，回覆 `confirmed` 或 `go`。
