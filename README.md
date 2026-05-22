# HarnessDiff

HarnessDiff is a localhost teaching workbench for comparing the same chat task with and without a Harness layer.

Stage 0 provides the project skeleton only:

- `apps/web`: React + Vite + TypeScript frontend scaffold.
- `apps/api`: FastAPI backend scaffold.
- `data/projects`: local JSON project storage root.
- `docs`: architecture, storage, and provider extension notes.
- `tests`: backend smoke tests.

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

The frontend is intentionally a placeholder in Stage 0. Real dual-pane chat behavior starts in later stages.

## Environment

Copy `.env.example` to `.env` and set `OPENAI_API_KEY` before the OpenAI streaming stage. Stage 0 does not call OpenAI.

## Stage Boundary

Stage 0 is complete when:

- backend health route works;
- pytest smoke tests pass;
- project folders and documentation exist;
- storage root can be initialized;
- frontend scaffold files exist for future implementation.

## Release Notes

This repository is prepared so GitHub release archives contain source, docs, tests, and lockfiles only. Generated folders such as `node_modules`, `dist`, caches, local `.env`, and local project data are ignored.

Before tagging a release, run:

```powershell
python -m pytest
cd apps/web
node node_modules\typescript\bin\tsc -b
node node_modules\vite\bin\vite.js build
node node_modules\vitest\vitest.mjs run
```

See `docs/release-checklist.md` for the release checklist.

