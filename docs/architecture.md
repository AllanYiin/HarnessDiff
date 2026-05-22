# HarnessDiff Architecture

HarnessDiff is a localhost web app for comparing chat behavior with and without a Harness layer.

## Stage 0 Architecture

- `apps/web` owns the browser UI.
- `apps/api` owns orchestration, provider adapters, storage, and analysis.
- `data/projects` is the local JSON source of truth.
- `docs` records design decisions and future extension points.

## Module Boundaries

The frontend must not call OpenAI directly. It talks to the local FastAPI server only.

The backend must not hard-code OpenAI behavior inside route handlers. Provider-specific code belongs behind a provider adapter. Stage 0 does not implement the adapter yet, but the folder layout and documentation assume that boundary.

## Future Stages

Stage 1 adds project CRUD and JSON schemas.
Stage 2 adds the dual-pane chat UI.
Stage 3 adds OpenAI Responses API streaming.
Stage 4 adds the Harness module engine.
Stage 5 adds turn and cumulative analysis.

