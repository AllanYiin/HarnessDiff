# HarnessDiff

## Overview

HarnessDiff is a localhost teaching workbench for comparing the same chat task with and without a Harness layer.

It currently implements the Chat surface only. Workflow, Agent, and MultiAgents are reserved surface types for future stages.

## What Works Now

- Dual-pane chat comparison: `NoHarness` on the left, `Harness` on the right.
- First turn can use integrated input; later turns can use independent pane input.
- OpenAI Responses API streaming through a local FastAPI backend.
- Project, run, input, output, event, usage, and analysis artifacts stored as local JSON.
- Per-run Harness module toggles for the Harness pane only.
- Deterministic current-turn and cumulative token/context analysis.
- Desktop and mobile Playwright smoke/regression coverage.

## Prerequisites

- Python 3.10+
- Node.js 22+
- Corepack / pnpm for frontend dependencies
- `OPENAI_API_KEY` for live OpenAI streaming

## Quick Start

### One-click start

For normal local use, start from the generated launcher for your platform:

- Windows: double-click `run_app.bat`
- macOS: run `chmod +x run_app.command` once if needed, then double-click `run_app.command`
- Linux: run `chmod +x run_app.sh` once if needed, then run `./run_app.sh`

The launcher creates `.venv`, installs Python dependencies from `requirements.txt`, installs frontend dependencies with Corepack/pnpm, starts the FastAPI backend and Vite frontend, then writes runtime metadata to `.runtime/` and logs to `logs/`.

Live OpenAI streaming requires `OPENAI_API_KEY` from your shell environment or `.env`.

### Manual start

From the repository root:

```powershell
python -m pip install -r requirements.txt
cd apps/web
corepack pnpm install
```

Set the API key in your shell:

```powershell
$env:OPENAI_API_KEY="sk-..."
```

Start the backend from the repository root:

```powershell
python -m uvicorn app.main:app --app-dir apps/api --reload
```

Start the frontend in another shell:

```powershell
cd apps/web
corepack pnpm run dev
```

Open the Vite URL shown in the terminal, normally `http://localhost:5173`.

## Verify

```powershell
python scripts\apsm_validate.py --project . --strict
python scripts\project_launcher.py --ensure-only
python -m pytest
python -m compileall apps\api
node apps\web\node_modules\typescript\bin\tsc -b apps\web
node apps\web\node_modules\vitest\vitest.mjs run src --root apps\web
node apps\web\node_modules\vite\bin\vite.js build apps\web
node apps\web\node_modules\@playwright\test\cli.js test --config apps\web\playwright.config.ts
```

The Playwright command writes screenshots to `test-results/screenshots`.

## Environment

Copy `.env.example` to `.env` or set environment variables in the shell.

Important variables:

- `HARNESSDIFF_DATA_DIR`: local JSON storage root, default `./data`
- `HARNESSDIFF_HOME`: user-level HarnessDiff home, default `~/.harnessdiff`
- `OPENAI_API_KEY`: required for live OpenAI streaming
- `OPENAI_DEFAULT_MODEL`: documented default model
- `OPENAI_DEFAULT_REASONING_EFFORT`: documented default reasoning effort

The current frontend default is `gpt-5.4-mini` with `medium` reasoning effort.

## OpenAI Streaming

The backend exposes run streaming through:

- `POST /api/projects/{project_id}/runs`
- `GET /api/runs/{run_id}/stream`

The first provider is OpenAI Responses API streaming. The frontend calls the local API and surfaces backend/provider failures instead of substituting mock streaming. UI-only fixture tests must not be treated as live backend verification.

See [docs/api-reference.md](docs/api-reference.md) for endpoint details.

## Analysis

The backend produces analysis after each streamed run:

- `GET /api/runs/{run_id}/analysis`
- local artifact: `data/projects/{project_id}/runs/{run_id}/analysis/analysis.json`

The analysis is deterministic and reads saved JSON artifacts. Provider-reported usage is used for input, output, reasoning, and total tokens when `usage.json` exists. Context section token counts are marked as estimates derived from saved text length.

Analysis is not an LLM call. It does not add token cost.

## Harness Modules

Each project gets `config/harness.default.json`. A run can override individual Harness modules through the UI or API with `harness_modules`.

The current module switches are:

- `context_summary`
- `source_map`
- `guardrails`
- `output_contract`
- `planning_preamble`
- `tool_policy`
- `memory_selection`
- `post_answer_critique`
- `token_budgeter`

These switches affect only the `Harness` pane. `NoHarness` keeps the direct baseline instruction.

When `source_map` and `tool_policy` are enabled together, Harness web tool results are carried into final answer synthesis with citation guidance so web-supported claims can include inline Markdown links and a short `Sources` section.

## Skills

HarnessDiff creates `~/.harnessdiff` at startup with `CLAUDE.md`, `AGENTS.md`, `agents.md`, `agents/`, and `skills/`. `AGENTS.md` is appended to provider instructions for every chat turn. The `agents/` folder stores editable subagent definition files; `harness.subagent.run` loads those definitions when invoked, runs the selected subagent as an ephemeral isolated provider request, and persists its token usage under the caller profile for analysis rollup. The UI skill panel lists installed skills from `~/.harnessdiff/skills`, imports `.zip`, `.skill`/`.md`, or folder uploads, and reveals full `SKILL.md` content only after a skill is selected.

On the first run in a new conversation, HarnessDiff adds only the first layer of installed skills to provider context: `name` and `description`.

In the composer, typing `/` opens installed skill suggestions. Selecting or typing `/skill-id` in a prompt loads that skill's full `SKILL.md` into the current run context.

## Repository Map

- `apps/api`: FastAPI backend, storage, run orchestration, provider adapter, analysis builder
- `apps/web`: React workbench, composer, pane UI, Playwright tests
- `data`: ignored local JSON runtime data
- `docs`: architecture, API, storage, provider, release, troubleshooting docs
- `specs`: product spec and stage acceptance notes
- `scripts`: APSM validator, one-click launcher generator, backend launch bridge
- `tests`: backend pytest coverage
- `DEVNOTE.md`: cumulative development handoff notes

## Documentation

- [Architecture](docs/architecture.md)
- [API Reference](docs/api-reference.md)
- [Storage Format](docs/storage-format.md)
- [Provider Adapter](docs/provider-adapter.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Release Checklist](docs/release-checklist.md)
- [Product Spec](specs/product-spec.md)
- [Stage Plan](specs/stage-plan.md)
- [Executable Requirements](specs/requirements.md)

## Release Notes

This repository is prepared so GitHub release archives contain source, docs, tests, and lockfiles only. Generated folders such as `node_modules`, `dist`, caches, local `.env`, and local project data are ignored.

Before tagging a release, run:

```powershell
python -m pytest
cd apps/web
node node_modules\typescript\bin\tsc -b
node node_modules\vite\bin\vite.js build
node node_modules\vitest\vitest.mjs run src
node node_modules\@playwright\test\cli.js install chromium
node node_modules\@playwright\test\cli.js test
```

See `docs/release-checklist.md` for the release checklist.

Backend dependencies are listed in `requirements.txt`. ToolAnything is installed from the local wheel under `vendor/wheels` via the `--find-links` entry in `requirements.txt`.
