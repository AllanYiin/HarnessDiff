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
- `completed`
- `error`

Provider-specific raw events and raw usage should be preserved in local JSON for debugging and future migration.

## OpenAI Responses API Notes

The OpenAI provider stage must use Responses API streaming and handle semantic events such as `response.output_text.delta`. It must preserve usage fields including input, output, total, and reasoning tokens when present.

## Implemented Stage 3 Boundary

Stage 3 adds a provider-neutral streaming shape:

```text
LLMRequest -> async iterator[ProviderEvent]
```

Provider events are converted to app-level SSE payloads:

- `created`
- `delta`
- `completed`
- `error`
- `run_completed`

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

`events.jsonl` preserves provider events for debugging. `usage.json` keeps normalized usage and raw provider usage when available.

## Non-goals in Stage 0

Stage 0 does not call any LLM provider. It only defines the boundary and keeps the project layout ready for implementation.
