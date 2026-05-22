# HarnessDiff Architecture

HarnessDiff is a localhost web app for comparing chat behavior with and without a Harness layer.

## Current Architecture

- `apps/web` owns the browser UI and calls only the local API.
- `apps/api` owns orchestration, provider adapters, storage, Harness instruction assembly, and analysis.
- `data/projects` is the local JSON source of truth.
- `docs` records design decisions and operational guidance.
- `specs` records product scope and stage acceptance.

## Module Boundaries

The frontend must not call OpenAI directly. It talks to the local FastAPI server only.

The backend must not hard-code OpenAI behavior inside route handlers. Provider-specific code belongs behind an `LLMProvider` adapter.

Harness technique details must not leak into provider adapters. The Harness Engine converts enabled modules into final pane instructions before the provider receives `LLMRequest`.

Analysis must be deterministic by default. Stage 5 analysis reads local JSON artifacts and does not call an LLM.

## Runtime Flow

1. The frontend creates a project if needed.
2. The frontend creates a run with prompt, target panes, model, reasoning effort, and Harness module overrides.
3. The backend writes `run.json`.
4. `RunOrchestrator` starts one async provider task per target pane.
5. Each pane writes `input.json`, `events.jsonl`, `output.json`, and `usage.json`.
6. When all panes complete successfully, the backend writes `analysis/analysis.json`.
7. SSE sends `analysis_ready` and then `run_completed`.
8. If any pane fails, the run is marked `failed`, SSE sends `run_failed`, and analysis is not written.

## Local Data Layout

```text
data/projects/{project_id}/
  project.json
  config/harness.default.json
  runs/{run_id}/
    run.json
    Harness/
      input.json
      output.json
      usage.json
      events.jsonl
    NoHarness/
      input.json
      output.json
      usage.json
      events.jsonl
    analysis/analysis.json
```

## Future Stages

The current Chat MVP is complete through Stage 7. Future work can add Workflow, Agent, and MultiAgents surfaces without changing the provider boundary.
