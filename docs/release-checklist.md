# Release Checklist

Use this checklist before creating a GitHub tag or release.

## Preflight

- Confirm no generated folders are staged: `node_modules`, `dist`, `.pytest_cache`, `.pnpm-store`, `__pycache__`, local `.env`, and local `data/projects/*`.
- Confirm `.env.example` contains all required environment variables without secrets.
- Confirm `CHANGELOG.md` has a release entry.
- Confirm README startup instructions are current.
- Confirm `DEVNOTE.md` snapshot matches the implemented stage.
- Confirm local `data/projects/*` artifacts are not staged.
- Confirm `specs/product-spec.md` and `specs/stage-plan.md` match the release scope.
- Confirm Playwright screenshots are generated but not required as release assets.

## Verification

From the repository root:

```powershell
python -m pytest
```

From `apps/web`:

```powershell
corepack pnpm install
node node_modules\typescript\bin\tsc -b
node node_modules\vite\bin\vite.js build
node node_modules\vitest\vitest.mjs run src
node node_modules\@playwright\test\cli.js install chromium
node node_modules\@playwright\test\cli.js test
```

Expected regression coverage includes provider failures, invalid run ids, lazy analysis rebuilds, Harness settings disclosure, no horizontal overflow, composer visibility, pane visibility, and streamed `analysis_ready` rendering.

## Release Notes Draft

For the first Chat MVP release, include:

- dual-pane Harness vs NoHarness Chat workbench
- OpenAI Responses API streaming
- per-run Harness module toggles
- local JSON artifacts for project/run/input/output/events/usage/analysis
- deterministic current and cumulative token/context analysis
- known limitations: Chat surface only, no real provider file/image upload, no voice input, stored history not yet replayed into provider context

## Tagging

- Use semantic version tags once the project reaches public release readiness, for example `v0.1.0`.
- Attach release notes that include user-visible changes, known limitations, and upgrade notes.
- Do not attach local data or dependency folders to GitHub Releases.
