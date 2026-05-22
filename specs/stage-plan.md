# HarnessDiff Stage Plan

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

## Future Work

- send uploaded files/images to provider
- implement voice input
- replay selected stored history into provider context
- add Workflow / Agent / MultiAgents surfaces
- add optional semantic analyzer provider
- add persistent server-side config editing UI
