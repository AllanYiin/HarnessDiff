# HarnessDiff

HarnessDiff is a localhost teaching workbench for comparing the same chat task with and without a Harness layer.

Current local milestone:

- `apps/web`: React + Vite + TypeScript frontend scaffold.
- `apps/api`: FastAPI backend scaffold.
- `data/projects`: local JSON project storage root.
- `docs`: architecture, storage, and provider extension notes.
- `tests`: backend smoke tests.
- Stage 4 has a first Harness Engine slice: project JSON config, per-run Harness module overrides, Harness-only instruction assembly, and UI toggles.

## Prerequisites

- Python 3.10+
- Node.js 22+ for the frontend
- A working package manager for frontend dependencies. This environment currently has Node available, but `npm` may need repair before frontend scripts can run.

## Backend

```powershell
python -m uvicorn app.main:app --app-dir apps/api --reload
```

Health check:

```powershell
python -m pytest
```

## Frontend

After installing dependencies:

```powershell
cd apps/web
corepack pnpm install
corepack pnpm run dev
```

The frontend starts as a dual-pane Chat workbench. It sends to the API first and falls back to mock streaming when the backend is unavailable.

## Environment

Copy `.env.example` to `.env` or set `OPENAI_API_KEY` in the local environment before live OpenAI streaming.

## OpenAI Streaming

The backend exposes run streaming through:

- `POST /api/projects/{project_id}/runs`
- `GET /api/runs/{run_id}/stream`

The first provider is OpenAI Responses API streaming. The frontend attempts the local API first and falls back to mock streaming when the backend is not running, so UI smoke tests can run without an API key.

## Harness Modules

Each project gets `config/harness.default.json`. A run can override individual Harness modules through the UI or API with `harness_modules`.

The current module switches are:

- `context_manifest`
- `source_map`
- `guardrails`
- `output_contract`
- `planning_preamble`
- `tool_policy`
- `memory_selection`
- `post_answer_critique`
- `token_budgeter`

These switches affect only the `Harness` pane. `NoHarness` keeps the direct baseline instruction.

## Stage Boundary

The initial local milestones are complete through Stage 4 when:

- backend health route works;
- pytest smoke tests pass;
- project folders and documentation exist;
- storage root can be initialized;
- dual-pane UI passes desktop/mobile Playwright smoke;
- OpenAI Responses API streaming works through the provider adapter and run SSE route;
- Harness module config can be toggled per run and stored in local JSON.

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

Backend dependencies are listed in `requirements.txt`.
