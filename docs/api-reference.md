# API Reference

## Overview

This reference covers the local FastAPI surface implemented in the Chat MVP.

Base URL during local development:

```text
http://127.0.0.1:8000/api
```

## Version

The app version is currently `0.0.0-stage0` in FastAPI metadata, while the implemented feature scope is complete through Stage 7 for the Chat MVP. Stored JSON documents use `schema_version` from backend settings.

## Parameters

Common path parameters:

- `project_id`: local id matching `proj_...`
- `run_id`: local id matching `run_...`

Common body parameters:

- `model`: OpenAI model id used by the provider adapter
- `reasoning_effort`: reasoning effort passed to the OpenAI Responses API when set
- `target_panes`: one or both of `NoHarness`, `Harness`

## Health

### `GET /health`

Returns backend health.

Expected response:

```json
{
  "status": "ok"
}
```

## Projects

### `GET /projects`

Lists projects.

### `POST /projects`

Creates a project and its default Harness config.

Request:

```json
{
  "name": "HarnessDiff local session",
  "surface_type": "chat",
  "config_profile": "harness.default"
}
```

Important fields:

- `name`: required, 1-120 characters
- `surface_type`: `chat`, `workflow`, `agent`, or `multi_agents`; only `chat` is executable now
- `config_profile`: defaults to `harness.default`

Success: `201 Created`

### `GET /projects/{project_id}`

Returns a project.

Errors:

- `400`: invalid project id
- `404`: project not found
- `409`: project storage is corrupt; response includes `repair_report`

### `PATCH /projects/{project_id}`

Updates project metadata.

### `DELETE /projects/{project_id}`

Deletes a project directory.

Success: `204 No Content`

## Runs

### `POST /projects/{project_id}/runs`

Creates a run. Streaming does not start until `GET /runs/{run_id}/stream`.

Request:

```json
{
  "prompt": "Compare the task with and without Harness.",
  "input_mode": "integrated",
  "model": "gpt-5.4-mini",
  "reasoning_effort": "medium",
  "target_panes": ["NoHarness", "Harness"],
  "harness_modules": {
    "context_manifest": true,
    "source_map": true,
    "guardrails": true,
    "output_contract": true,
    "planning_preamble": false,
    "tool_policy": true,
    "memory_selection": true,
    "post_answer_critique": true,
    "token_budgeter": true
  }
}
```

Important fields:

- `prompt`: required
- `input_mode`: `integrated` or `independent`
- `target_panes`: one or both of `NoHarness`, `Harness`
- `harness_modules`: optional per-run overrides; merged with `config/harness.default.json`

Success: `201 Created`

### `GET /runs/{run_id}/stream`

Streams Server-Sent Events (`text/event-stream`) for a run.

SSE event payloads are emitted as JSON in `data:` lines.

Common event types:

- `created`
- `delta`
- `completed`
- `error`
- `analysis_ready`
- `run_completed`
- `run_failed`

Example delta:

```text
data: {"run_id":"run_...","pane":"Harness","type":"delta","text":"partial text","sequence":1}
```

Success path:

1. pane events stream independently
2. `analysis_ready` includes the generated analysis document
3. `run_completed` ends the completed run

Failure path:

1. the failing pane emits `error`
2. the run status becomes `failed`
3. `run_failed` ends the run
4. no analysis artifact is written

### `GET /runs/{run_id}/analysis`

Returns `analysis/analysis.json`.

If the artifact is missing and the run data exists, the API builds analysis lazily from local JSON artifacts.

Analysis includes:

- current-turn usage
- cumulative usage
- context section structure
- Harness vs NoHarness token deltas
- notes about estimated section tokens

## Token Usage Notes

Provider-reported `usage.json` is the source of truth for input, output, reasoning, and total tokens.

Context section `estimated_tokens` are deterministic estimates derived from saved text length. They are useful for structure comparison but are not billing numbers.

## Local Artifact Side Effects

Successful streamed runs write:

```text
runs/{run_id}/run.json
runs/{run_id}/{pane}/input.json
runs/{run_id}/{pane}/events.jsonl
runs/{run_id}/{pane}/output.json
runs/{run_id}/{pane}/usage.json
runs/{run_id}/analysis/analysis.json
```

Failed runs write run and pane error artifacts but skip `analysis/analysis.json`.
