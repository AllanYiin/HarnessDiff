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

The response includes a `tools` object so local runs can confirm whether HarnessDiff
started with the ToolAnything runtime loaded:

```json
{
  "status": "ok",
  "app": "HarnessDiff API",
  "schema_version": "2026-05-22.1",
  "data_dir": "D:\\PycharmProjects\\HarnessDiff\\github_repo\\data",
  "harnessdiff_home": "C:\\Users\\you\\.harnessdiff",
  "tools": {
    "enabled": true,
    "count": 16,
    "names": ["standard.web.search", "standard.shell.bash", "standard.code.container_exec", "harness.subagent.run", "multi_tool_use.parallel"],
    "container_runtime": {
      "available": false,
      "docker_found": true,
      "daemon_available": true,
      "image_present": false,
      "image": "harnessdiff-code-runtime:latest",
      "message": "Docker image is not built: harnessdiff-code-runtime:latest"
    }
  }
}
```

Expected response:

```json
{
  "status": "ok"
}
```

## Skills

### `GET /skills`

Ensures the HarnessDiff home exists, then returns installed skill summaries.

Response:

```json
{
  "home_dir": "C:\\Users\\you\\.harnessdiff",
  "skills_dir": "C:\\Users\\you\\.harnessdiff\\skills",
  "skills": [
    {
      "id": "demo-skill",
      "name": "demo-skill",
      "description": "Demo skill description",
      "version": "1.0",
      "path": "C:\\Users\\you\\.harnessdiff\\skills\\demo-skill"
    }
  ]
}
```

### `GET /skills/{skill_id}`

Returns the full `SKILL.md` content for one installed skill. The chat context uses only the first-layer summary unless the user explicitly drills into the skill.

### `POST /skills/import`

Imports a skill into `~/.harnessdiff/skills`.

Supported `mode` values:

- `zip`: `filename` plus `data_base64` for a zip archive containing `SKILL.md`
- `skill`: `filename` plus `data_base64` for a single `.skill` or Markdown skill file saved as `SKILL.md`
- `folder`: `filename` plus `files`, where each item has `relative_path` and `data_base64`

Zip and folder imports reject absolute paths, empty path parts, and `..` path traversal.

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

### `GET /projects/{project_id}/transcript`

Returns a project plus ordered run records and saved pane outputs so the frontend can rebuild a conversation history view.

Response shape:

```json
{
  "project": {
    "id": "proj_...",
    "name": "Conversation title"
  },
  "runs": [
    {
      "id": "run_...",
      "prompt": "User prompt",
      "target_panes": ["NoHarness", "Harness"],
      "status": "completed",
      "panes": {
        "NoHarness": { "output_text": "..." },
        "Harness": { "output_text": "..." }
      }
    }
  ]
}
```

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
  "attachments": [
    {
      "kind": "image",
      "name": "screen.png",
      "mime_type": "image/png",
      "size_bytes": 1843473,
      "image_url": "data:image/png;base64,...",
      "detail": "auto"
    }
  ],
  "target_panes": ["NoHarness", "Harness"],
  "harness_modules": {
    "context_summary": true,
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
- `attachments`: optional supported image inputs for OpenAI vision; `image_url` must be a data URL or fully qualified URL.
- `target_panes`: one or both of `NoHarness`, `Harness`
- `harness_modules`: optional per-run overrides; merged with `config/harness.default.json`
  - Legacy payloads using `context_manifest` are accepted and normalized to `context_summary`.

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
- per-subagent usage and caller-level subagent usage rollups when `harness.subagent.run` is called
- context section structure
- tool definition context for profiles where tools were sent
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

Profiles write `tool_names` to `input.json` when tools are available, and successful or failed tool calls are preserved as `tool_call` rows in `events.jsonl`. Harness chat profiles with `tool_policy` enabled include `standard.shell.bash`, `standard.code.container_exec`, `harness.subagent.run`, and `multi_tool_use.parallel`; NoHarness profiles omit those four while retaining standard web/fs/data tools. `standard.code.container_exec` accepts `command`, optional `workdir`, and optional `timeout_seconds`, then runs the command in an offline Docker container against a temporary repository copy. `harness.subagent.run` accepts `subagent_id`, `task`, and `context`, then returns the subagent result as a normal function tool output.

Subagent definitions are loaded from `~/.harnessdiff/agents/` when `harness.subagent.run` is invoked. Subagent instances are ephemeral and do not keep live state after the tool call, but their artifacts and token usage remain on disk. Definitions may include `tools: WebSearch, WebFetch` to let that subagent use only the mapped standard web search/fetch tools during its provider request; definitions without `tools:` still run with tools disabled. Subagent tool calls additionally write:

```text
runs/{run_id}/{profile_id}/subagents/{subagent_id}/input.json
runs/{run_id}/{profile_id}/subagents/{subagent_id}/events.jsonl
runs/{run_id}/{profile_id}/subagents/{subagent_id}/output.json
runs/{run_id}/{profile_id}/subagents/{subagent_id}/usage.json
```

Failed runs write run and pane error artifacts but skip `analysis/analysis.json`.
