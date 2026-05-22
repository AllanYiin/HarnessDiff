# Release Checklist

Use this checklist before creating a GitHub tag or release.

## Preflight

- Confirm no generated folders are staged: `node_modules`, `dist`, `.pytest_cache`, `.pnpm-store`, `__pycache__`, local `.env`, and local `data/projects/*`.
- Confirm `.env.example` contains all required environment variables without secrets.
- Confirm `CHANGELOG.md` has a release entry.
- Confirm README startup instructions are current.

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
node node_modules\vitest\vitest.mjs run
```

## Tagging

- Use semantic version tags once the project reaches public release readiness, for example `v0.1.0`.
- Attach release notes that include user-visible changes, known limitations, and upgrade notes.
- Do not attach local data or dependency folders to GitHub Releases.

