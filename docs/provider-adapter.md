# Provider Adapter Boundary

HarnessDiff starts with OpenAI Responses API streaming, but the app must remain provider-extensible.

## Required Provider Shape

Future provider implementations should expose a common streaming interface:

```text
stream_chat(request) -> async iterator[ProviderEvent]
```

The route layer should consume provider-neutral events:

- `created`
- `delta`
- `completed`
- `error`

Provider-specific raw events and raw usage should be preserved in local JSON for debugging and future migration.

## OpenAI Responses API Notes

The OpenAI provider stage must use Responses API streaming and handle semantic events such as `response.output_text.delta`. It must preserve usage fields including input, output, total, and reasoning tokens when present.

## Non-goals in Stage 0

Stage 0 does not call any LLM provider. It only defines the boundary and keeps the project layout ready for implementation.

