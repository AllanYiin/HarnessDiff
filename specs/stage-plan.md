# HarnessDiff Stage Plan

This file tracks the original Chat MVP stages plus the delivered Agent surface expansion. Agent surface work is specified in [agent-surface-spec.md](agent-surface-spec.md).

## Stage 0: Project Skeleton

Status: complete

Acceptance:

- localhost web app repository layout exists
- FastAPI backend health route exists
- React/Vite frontend scaffold exists
- env sample and baseline docs exist
- storage/provider boundaries are documented

## Stage 1: Local JSON Project Storage

Status: complete

Acceptance:

- project CRUD uses local JSON
- schema version is stored
- writes are atomic
- corrupt project JSON creates a repair report

## Stage 2: Dual-pane Chat UI

Status: complete

Acceptance:

- NoHarness and Harness panes render side by side on desktop
- mobile layout has no horizontal overflow
- integrated input starts as the default
- independent input is available after a completed turn
- composer remains visible
- Playwright screenshots are written to `test-results/screenshots`

## Stage 3: Responses API Streaming

Status: complete

Acceptance:

- OpenAI provider is behind `LLMProvider`
- route layer does not parse OpenAI-specific events directly
- run streaming uses SSE
- Harness and NoHarness tasks run independently
- usage is saved per pane
- live OpenAI streaming has been smoke-tested with local `OPENAI_API_KEY`

## Stage 4: Harness Engine and Config

Status: complete

Acceptance:

- project default config writes `config/harness.default.json`
- per-run `harness_modules` overrides are accepted
- Harness modules affect only Harness instructions
- NoHarness keeps the baseline instruction
- final instructions and effective modules are saved in `input.json`
- UI exposes per-module toggles

## Stage 5: Turn and Cumulative Analysis

Status: complete

Acceptance:

- completed runs write `analysis/analysis.json`
- stream emits `analysis_ready`
- `GET /api/runs/{run_id}/analysis` returns or lazily rebuilds analysis
- current-turn usage and cumulative usage are reported
- context sections are represented for both panes
- provider usage and estimated section tokens are clearly separated

## Stage 6: Integration, Regression, and Boundary Tests

Status: complete

Acceptance:

- provider failure marks run `failed`
- partial failed runs do not write analysis
- invalid and missing run ids are covered
- single-pane analysis is covered
- Harness settings disclosure is covered in desktop/mobile Playwright
- `analysis_ready` frontend rendering is covered in desktop/mobile Playwright
- release verification commands pass

## Stage 7: Documentation and Handoff

Status: complete

Acceptance:

- README includes quick start, verification, environment, and docs map
- API reference exists
- troubleshooting guide exists
- product spec and stage plan exist under `specs/`
- architecture, storage, provider, release checklist, changelog, and DEVNOTE are current
- generated folders and local data are not required for release

## Agent Surface Stage 0: Contracts and Compatibility

Status: complete

Acceptance:

- Agent run config and step event models exist
- `RunCreate.surface_payload` is additive and does not break Chat requests
- frontend shared types include `SurfaceType` and Agent step traces

## Agent Surface Stage 1: Surface Switch

Status: complete

Acceptance:

- TopBar has a Chat / Agent segmented control
- project creation stores `surface_type`
- loading history restores the project surface
- running streams block surface switching

## Agent Surface Stage 2: Agent Runtime and Artifacts

Status: complete

Acceptance:

- Agent projects route to `AgentRunOrchestrator`
- `baseline_agent` and `harness_agent` stream foreground output
- profile folders write input, output, events, usage, and `steps.jsonl`
- Chat run streaming remains unchanged

## Agent Surface Stage 3: Tool Policy and Subagent Trace

Status: complete

Acceptance:

- `NoHarness Agent` omits shell/container/code/subagent/parallel tools
- `Harness Agent` can use those tools when tool policy is enabled
- tool calls are normalized into provider events and Agent step traces

## Agent Surface Stage 4: Agent UI

Status: complete

Acceptance:

- Agent mode renders dual agent panes and a task composer
- final output streams incrementally
- step/tool/subagent trace is visible with progressive disclosure
- cancel is available for foreground execution

## Agent Surface Stage 5: Agent Analysis and History

Status: complete

Acceptance:

- completed Agent runs write `analysis/agent-analysis.json`
- `/runs/{run_id}/analysis` branches by project surface
- project transcript returns Agent profile steps
- frontend history load reconstructs Agent output and trace

## Agent Surface Stage 6: Regression Verification

Status: complete

Acceptance:

- `python -m pytest`: 85 passed, 1 skipped
- `node apps\web\node_modules\vitest\vitest.mjs run src --root apps\web`: 18 passed
- `node node_modules\typescript\bin\tsc -b` from `apps/web`: passed
- `node node_modules\vite\bin\vite.js build` from `apps/web`: passed
- `node node_modules\@playwright\test\cli.js test` from `apps/web`: 26 passed

## Agent Surface Stage 7: Documentation and Handoff

Status: complete

Acceptance:

- README documents Chat / Agent surfaces and Agent first-version limits
- API, storage, provider, architecture, troubleshooting, release, product, and requirements docs describe Agent mode
- Agent limits are explicit: foreground streaming, cancel, traceable artifacts; no background resume/checkpointing

## Future Work

- send uploaded non-image files to provider
- replay selected stored history into provider context
- add Workflow / MultiAgents surfaces
- add durable background Agent resume/checkpointing
- add optional semantic analyzer provider
- add persistent server-side config editing UI
