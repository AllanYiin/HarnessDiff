# Local JSON Storage Format

The local JSON store is the system of record for HarnessDiff MVP.

## Root Layout

```text
data/
  projects/
    {project_id}/
      project.json
      config/
        harness.default.json
      runs/
```

## Project Document

```json
{
  "schema_version": "2026-05-22.1",
  "id": "proj_...",
  "name": "Chat comparison",
  "surface_type": "chat",
  "config_profile": "harness.default",
  "created_at": "2026-05-22T00:00:00+00:00",
  "updated_at": "2026-05-22T00:00:00+00:00"
}
```

Allowed `surface_type` values are `chat`, `workflow`, `agent`, and `multi_agents`. Only `chat` is executable in the MVP.

Each chat run must keep `Harness` and `NoHarness` data physically separated:

```text
runs/
  {run_id}/
    run.json
    Harness/
    NoHarness/
    analysis/
      analysis.json
```

## Run Document

```json
{
  "schema_version": "2026-05-22.1",
  "id": "run_...",
  "project_id": "proj_...",
  "turn_index": 0,
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
  },
  "status": "submitted",
  "prompt": "User prompt",
  "created_at": "2026-05-22T00:00:00+00:00",
  "updated_at": "2026-05-22T00:00:00+00:00"
}
```

Run status values are `submitted`, `running`, `completed`, `failed`, and `cancelled`.

## Harness Config

Each project stores its default Harness module profile at `config/harness.default.json`:

```json
{
  "schema_version": "2026-05-22.1",
  "profile": "harness.default",
  "modules": {
    "context_manifest": { "enabled": true },
    "source_map": { "enabled": true },
    "guardrails": { "enabled": true },
    "output_contract": { "enabled": true },
    "planning_preamble": { "enabled": false },
    "tool_policy": { "enabled": true },
    "memory_selection": { "enabled": true },
    "post_answer_critique": { "enabled": true },
    "token_budgeter": { "enabled": true }
  }
}
```

Run-level `harness_modules` are the effective booleans after applying API/UI overrides to the project config. They are stored in `run.json` and repeated in `Harness/input.json` with the final instructions for traceability.

## Analysis Document

Completed runs write `analysis/analysis.json`:

```json
{
  "schema_version": "2026-05-22.1",
  "project_id": "proj_...",
  "run_id": "run_...",
  "turn_index": 1,
  "generated_at": "2026-05-22T00:00:00+00:00",
  "panes": {
    "NoHarness": {
      "pane": "NoHarness",
      "current_turn_usage": {
        "input_tokens": 30,
        "output_tokens": 12,
        "reasoning_tokens": 0,
        "total_tokens": 42,
        "source": "provider_reported"
      },
      "cumulative_usage": {
        "input_tokens": 70,
        "output_tokens": 30,
        "reasoning_tokens": 0,
        "total_tokens": 100,
        "source": "provider_reported"
      },
      "context_sections": [],
      "output_characters": 80,
      "enabled_harness_modules": [],
      "provider_context_keys": ["instructions", "prompt"]
    }
  },
  "comparison": {
    "total_token_delta": 8,
    "input_token_delta": 3,
    "output_token_delta": 5,
    "reasoning_token_delta": 0,
    "harness_extra_sections": ["behavior_preferences"]
  },
  "notes": [],
  "raw_sources": {}
}
```

Usage numbers come from provider `usage.json` when available. Context section `estimated_tokens` are deterministic estimates from saved character counts, not provider billing numbers.

## Versioning

Every stored JSON document must include `schema_version`. Stage 0 uses `2026-05-22.1`.

## Migration Strategy

For MVP, migrations are file-based transforms:

1. Read and validate `schema_version`.
2. Write a backup beside the original file before changing it.
3. Write upgraded JSON atomically.
4. Produce a repair report if manual edits or corrupt JSON prevent migration.

SQLite or another database can be added later, but local JSON remains the initial canonical format.

## Repair Reports

If a project document cannot be decoded or validated, the API writes `repair-report.json` next to the corrupt file and returns a conflict response. The original corrupt file is not overwritten.

## Seed Strategy

Development seed data should live under `tests/fixtures` first. Demo projects can later be generated into `data/projects` by a script, but generated demo data should not be committed unless it is a small deterministic fixture.
