# Local JSON Storage Format

The local JSON store is the system of record for HarnessDiff Chat and Agent modes.

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

HarnessDiff also maintains a user-level home outside project JSON storage:

```text
~/.harnessdiff/
  CLAUDE.md
  AGENTS.md
  agents.md
  agents/
    researcher.md
    critic.md
    summarizer.md
  skills/
    {skill_id}/
      SKILL.md
      ...
```

`HARNESSDIFF_HOME` can override this location. `AGENTS.md` is read into provider instructions for every chat turn. `agents/` contains editable subagent definition files; Markdown files use frontmatter for `id`, `label`, `description`, `model`, `reasoning_effort`, `max_output_chars`, and `enabled`, with the Markdown body as instructions. `skills/{skill_id}/SKILL.md` is parsed for the first-layer skill `name`, `description`, and optional `version`. New conversation context receives only that first layer; full skill content is read on demand through the skill API/UI.

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

Allowed `surface_type` values are `chat`, `workflow`, `agent`, and `multi_agents`. `chat` and `agent` are executable; `workflow` and `multi_agents` remain reserved.

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

Each Agent run uses the same profile-per-folder pattern with `baseline_agent` and `harness_agent`, plus a foreground step trace per profile:

```text
runs/
  {run_id}/
    run.json
    baseline_agent/
      input.json
      events.jsonl
      steps.jsonl
      output.json
      usage.json
    harness_agent/
      input.json
      events.jsonl
      steps.jsonl
      output.json
      usage.json
      subagents/
        {subagent_id}/
          input.json
          events.jsonl
          output.json
          usage.json
    analysis/
      agent-analysis.json
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
    "context_summary": true,
    "source_map": true,
    "guardrails": true,
    "output_contract": true,
    "planning_preamble": false,
    "tool_policy": true,
    "memory_selection": true,
    "post_answer_critique": true,
    "token_budgeter": true,
    "consequence_gate": true
  },
  "status": "submitted",
  "prompt": "User prompt",
  "surface_payload": {
    "type": "agent",
    "objective": "Inspect the repository",
    "context": "",
    "max_steps": 16,
    "allow_subagents": true,
    "allow_container_tools": true
  },
  "created_at": "2026-05-22T00:00:00+00:00",
  "updated_at": "2026-05-22T00:00:00+00:00"
}
```

Run status values are `submitted`, `running`, `completed`, `failed`, and `cancelled`.

`surface_payload` is optional and remains `null` for Chat runs. Agent runs store an `agent` payload; if the client omits it, the backend derives `objective` from `prompt`.

## Harness Config

Each project stores its default Harness module profile at `config/harness.default.json`:

```json
{
  "schema_version": "2026-05-22.1",
  "profile": "harness.default",
  "modules": {
    "context_summary": { "enabled": true },
    "source_map": { "enabled": true },
    "guardrails": { "enabled": true },
    "output_contract": { "enabled": true },
    "planning_preamble": { "enabled": false },
    "tool_policy": { "enabled": true },
    "memory_selection": { "enabled": true },
    "post_answer_critique": { "enabled": true },
    "token_budgeter": { "enabled": true },
    "consequence_gate": { "enabled": true }
  }
}
```

Run-level `harness_modules` are the effective booleans after applying API/UI overrides to the project config. They are stored in `run.json` and repeated in profile `input.json` files with the final instructions for traceability. Supported image attachments are stored on `run.json` as provider-ready image URLs; profile `input.json` repeats only attachment metadata. Profiles also store `tool_names` for the tools sent to the provider. Harness profiles and `Harness Agent` with `tool_policy` enabled receive the full set, including `standard.shell.bash`, `standard.code.container_exec`, `harness.subagent.run`, and `multi_tool_use.parallel`; `NoHarness` and `NoHarness Agent` receive standard web/fs/data tools but omit those four. Harness profiles with `consequence_gate` enabled can also write `harness_decision` events before provider execution when the prompt appears to produce externally visible content. Those events may contain preview audit fields such as `missing_context`, `scanner_coverage_gaps`, `scanner_findings`, `similarity_matches`, `provenance_findings`, `claim_gaps`, `offer_disclosure_gaps`, `provenance_gaps`, and `rollback_constraints`; these are local trace data, not a production blacklist.
Older artifacts that use `context_manifest` are read as `context_summary` for backward compatibility.

Profile `input.json`:

```json
{
  "schema_version": "2026-05-22.1",
  "profile_id": "harness",
  "profile_label": "Harness",
  "prompt": "User prompt",
  "instructions": "Final provider instructions",
  "harness_modules": { "tool_policy": true },
  "conversation_messages": [],
  "attachments": [
    {
      "kind": "image",
      "name": "screen.png",
      "mime_type": "image/png",
      "size_bytes": 1843473,
      "detail": "auto"
    }
  ],
  "tool_names": ["standard.shell.bash", "standard.code.container_exec", "standard.web.fetch", "standard.fs.read", "harness.subagent.run", "multi_tool_use.parallel"],
  "created_at": "2026-05-22T00:00:00+00:00"
}
```

Tool call events are stored in `{profile_id}/events.jsonl` as provider events with `type: "tool_call"` and a raw payload containing the tool name, masked/truncated arguments, elapsed milliseconds, and either a result summary or structured error. Container code tool calls return stdout, stderr, exit code, elapsed milliseconds, Docker image name, network mode, and truncation status from an offline temporary workspace copy; they do not directly modify the original repository.

Agent step events are stored in `{profile_id}/steps.jsonl`. Each row is an `AgentStepEvent` with `profile_id`, `step_id`, `sequence`, `type`, `label`, `status`, optional `tool_name`, optional subagent ids, elapsed milliseconds, and optional token usage. The UI uses this file to reconstruct Agent trace timelines from history.

Subagent calls are created from the current `~/.harnessdiff/agents/` definitions when `harness.subagent.run` is invoked. They are ephemeral provider requests, and their artifacts are stored under the caller profile without replacing the caller profile output. Subagents run with tools disabled unless their definition declares an allowed `tools:` frontmatter value; currently web aliases such as `WebSearch` and `WebFetch` map to the standard web search/fetch tools only.

```text
runs/{run_id}/{profile_id}/subagents/{subagent_id}/
  input.json
  output.json
  events.jsonl
  usage.json
```

Each subagent `usage.json` records the subagent provider token usage. Analysis rolls these values up into the caller profile without overwriting the caller profile's own `usage.json`.

## Analysis Document

Completed Chat runs write `analysis/analysis.json`. Completed Agent runs write `analysis/agent-analysis.json` with the same top-level `AnalysisDocument` shape plus Agent structural metrics in `raw_sources.agent_metrics`.

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
      "context_sections": [
        {
          "key": "tool_definitions",
          "label": "Tool definitions",
          "status": "sent",
          "characters": 120,
          "estimated_tokens": 30,
          "notes": "Tool definitions were sent to the provider for this profile."
        }
      ],
      "output_characters": 80,
      "enabled_harness_modules": [],
      "provider_context_keys": ["instructions", "prompt", "tools"]
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

