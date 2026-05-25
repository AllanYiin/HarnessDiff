# Provider Adapter Boundary

HarnessDiff starts with OpenAI Responses API streaming, but the app must remain provider-extensible.

## Required Provider Shape

Future provider implementations should expose a common streaming interface:

```text
stream_text(request) -> async iterator[ProviderEvent]
```

The route layer should consume provider-neutral events:

- `created`
- `delta`
- `tool_call`
- `completed`
- `error`

Provider-specific raw events and raw usage should be preserved in local JSON for debugging and future migration.

## OpenAI Responses API Notes

The OpenAI provider stage must use Responses API streaming and handle semantic events such as `response.output_text.delta`. It must preserve usage fields including input, output, total, and reasoning tokens when present.

When `LLMRequest.tools_enabled` is true, the OpenAI provider also sends the HarnessDiff chat tool schema, handles `function_call` output items, executes the requested tool through the local tool runtime, appends `function_call_output`, and resumes the Responses request until the model returns a final non-tool response or the tool round limit is reached. The default tool round limit is 16 and can be overridden with `HARNESSDIFF_MAX_TOOL_ROUNDS`. Harness profiles with `tool_policy` receive the full tool set: standard web/fs/data tools, `standard.shell.bash`, `harness.subagent.run`, and `multi_tool_use.parallel`; the Harness tool schema places `standard.shell.bash` first. NoHarness profiles receive the standard web/fs/data tools but omit `standard.shell.bash`, `harness.subagent.run`, and `multi_tool_use.parallel`.

When a standard web tool returns URLs, the provider enriches the returned `function_call_output` with `citation_sources` and `citation_guidance`. This keeps source attribution in the final synthesis context without changing the public SSE or storage schema.

`harness.subagent.run` is a chat-local function tool. It runs one fixed backend subagent as an isolated provider request, disables nested tools for that subagent, writes subagent artifacts under the caller profile, and returns the subagent text as function output to the manager model. `multi_tool_use.parallel` is also chat-local and can concurrently invoke only tools that are already allowed for the current profile.

## Implemented Stage 3 Boundary

Stage 3 adds a provider-neutral streaming shape:

```text
LLMRequest -> async iterator[ProviderEvent]
```

Provider events are converted to app-level SSE payloads:

- `created`
- `delta`
- `tool_call`
- `completed`
- `error`
- `analysis_ready`
- `run_completed`
- `run_failed`

The backend route layer does not parse OpenAI events directly. It calls `RunOrchestrator`, which consumes an `LLMProvider` and writes per-pane JSON artifacts under the run folder.

## Harness Engine Boundary

Stage 4 adds a small Harness Engine slice before provider execution:

1. `ProjectStore` reads `config/harness.default.json`.
2. `RunCreate.harness_modules` overrides individual module booleans.
3. The effective module set is stored on `run.json`.
4. `context_builder.build_instructions()` converts enabled Harness modules into the Harness pane instructions.
5. `NoHarness` receives only the direct baseline instruction.

This keeps provider adapters unaware of Harness technique details. Providers receive only the final `LLMRequest`.

## Local JSON Outputs

For each run, `Harness` and `NoHarness` keep separate files:

```text
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
```

`events.jsonl` preserves provider events and tool-call events for debugging. `usage.json` keeps normalized usage and raw provider usage when available. Tool definitions are sent to both Harness and NoHarness profiles when the local tool runtime is loaded, with NoHarness using the restricted tool set described above. Subagent calls additionally write `{profile_id}/subagents/{subagent_id}/input.json`, `output.json`, `events.jsonl`, and `usage.json`.

## Stage 5 Analysis Boundary

Analysis is intentionally outside the provider adapter. After a run completes, `RunOrchestrator` calls the deterministic analysis builder, which reads:

- `run.json`
- `{pane}/input.json`
- `{pane}/output.json`
- `{pane}/usage.json`
- prior run artifacts in the same project

The analyzer writes `analysis/analysis.json` and emits an `analysis_ready` SSE payload before `run_completed`. It does not call an LLM. Provider-reported usage remains the source of truth for billed token numbers; context section token counts are only rough structural estimates.

Subagent token usage is tracked separately from the manager profile usage and is exposed as both per-subagent usage and caller-level rollup usage in analysis. This keeps the original Harness vs NoHarness comparison stable while still showing the full cost of delegated work.

If any pane raises a provider error, `RunOrchestrator` writes the pane error event, marks the run `failed`, emits `run_failed`, and does not write analysis for that run. This prevents failed partial output from being reported as a complete comparison.

## Stage 6 Regression Boundary

Stage 6 adds automated regression coverage for:

- provider failure in one pane while the other pane emits output;
- invalid and missing run ids;
- lazy analysis rebuild when `analysis.json` is absent;
- single-pane analysis without misleading cross-pane deltas;
- frontend Harness settings disclosure without horizontal overflow;
- frontend `analysis_ready` SSE rendering in desktop and mobile Playwright projects.

## Non-goals in Stage 0

Stage 0 does not call any LLM provider. It only defines the boundary and keeps the project layout ready for implementation.
