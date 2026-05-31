# HarnessDiff Architecture

HarnessDiff is a localhost web app for comparing chat and agent behavior with and without a Harness layer.

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
4. The route layer selects `RunOrchestrator` for Chat projects or `AgentRunOrchestrator` for Agent projects.
5. Chat starts one async provider task per target pane; Agent starts one foreground provider task per agent profile.
6. Each profile writes `input.json`, `events.jsonl`, `output.json`, and `usage.json`; Agent profiles also write `steps.jsonl`.
7. When all profiles complete successfully, the backend writes `analysis/analysis.json` for Chat or `analysis/agent-analysis.json` for Agent.
8. SSE sends `analysis_ready` and then `run_completed`.
9. If any profile fails, the run is marked `failed`, SSE sends `run_failed`, and complete comparison analysis is not written.

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

Agent runs use `baseline_agent/` and `harness_agent/` profile folders. The Harness Agent can use shell/container/code tools, `harness.subagent.run`, and `multi_tool_use.parallel` when tool policy is enabled; the NoHarness Agent intentionally omits those higher-risk tools. Agent mode is foreground-only in this release: streaming, cancel, and traceable artifacts are supported, but background resume/checkpointing is not.

## Future Stages

The Chat surface and first Agent surface are complete through the Agent mode delivery stages. Future work can add Workflow and MultiAgents surfaces or durable Agent resume without changing the provider boundary.
