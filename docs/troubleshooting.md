# Troubleshooting

Use this guide when local development or verification fails.

## Runbook Format

Each item is organized around symptoms, diagnosis, remediation, and verification. Escalation is usually local: inspect artifacts, rerun tests, or stop before release. Rollback means reverting the local change that introduced the failure; do not delete local data unless the task explicitly calls for it.

Alert condition: if a release verification command fails, do not tag or publish a release until the failure is diagnosed and fixed.

## Backend Does Not Start

Symptoms:

```text
ModuleNotFoundError: No module named 'app'
```

Diagnosis: the backend was started without `--app-dir apps/api` or without the API package on `PYTHONPATH`.

Remediation:

```powershell
python -m uvicorn app.main:app --app-dir apps/api --reload
```

Verify:

```powershell
python -m pytest tests\api\test_health.py
```

## OpenAI Streaming Fails

Symptoms:

```text
OPENAI_API_KEY is required for OpenAI streaming.
```

Diagnosis: `OPENAI_API_KEY` is not visible to the backend process.

Remediation:

```powershell
$env:OPENAI_API_KEY="sk-..."
python -m uvicorn app.main:app --app-dir apps/api --reload
```

Do not print or commit the key.

Escalation: if the key is present but the API still fails, inspect the provider error in `{pane}/events.jsonl` and retry a minimal live smoke before changing application code.

## Frontend Cannot Reach Backend

Symptoms: Playwright or Vite logs:

```text
http proxy error: /api/projects
Error: connect ECONNREFUSED 127.0.0.1:8000
```

Diagnosis: the frontend is running without the FastAPI backend.

Expected behavior: the UI surfaces the backend failure. Product code and e2e tests must not replace the response with mock streaming, because that hides missing backend/API contracts.

Remediation: start the backend on port 8000.

Verify: submit a prompt and confirm the run creates local JSON artifacts under `data/projects`.

## Playwright Chromium Cannot Start

Symptoms:

```text
spawn EPERM
```

Diagnosis: local sandbox restrictions can block launching Chromium.

Remediation: run the Playwright command with the local environment permission required by the shell/session.

Verify:

```powershell
node apps\web\node_modules\@playwright\test\cli.js test --config apps\web\playwright.config.ts
```

## Vitest Picks Up Playwright Tests

Symptoms: Vitest tries to execute files under `apps/web/e2e`.

Diagnosis: test discovery is too broad.

Remediation: run Vitest only against `src`:

```powershell
node apps\web\node_modules\vitest\vitest.mjs run src --root apps\web
```

## Corrupt Local Project JSON

Symptoms: project read returns `409` with a `repair_report` path.

Diagnosis: `project.json` is not valid JSON or no longer matches the schema.

Remediation:

1. Open the generated `repair-report.json`.
2. Inspect the referenced corrupt file.
3. Restore from backup or manually repair the JSON.
4. Retry `GET /api/projects/{project_id}`.

The API does not overwrite corrupt project data automatically.

Rollback: restore the corrupt JSON from a known-good backup or discard the affected local project only when the user explicitly approves data deletion.

## Run Fails After One Pane Errors

Symptoms: SSE ends with `run_failed`.

Diagnosis: at least one pane provider task raised an error. A run is considered incomplete if either side fails.

Expected behavior:

- failing pane writes `events.jsonl`
- `run.json` status becomes `failed`
- `analysis/analysis.json` is not written

Remediation: inspect the pane `events.jsonl` and provider error, then rerun.

Verify: the next successful run should end with `analysis_ready` and `run_completed`.

## Horizontal Overflow In UI Tests

Symptoms: Playwright fails the overflow assertion.

Diagnosis: a new control or label exceeded the viewport width.

Remediation:

1. Check `apps/web/src/styles.css` for fixed widths.
2. Prefer `minmax(0, 1fr)`, wrapping controls, or responsive disclosure.
3. Rerun Playwright desktop and mobile projects.

Escalation: if overflow remains after local CSS fixes, inspect the Playwright screenshots before changing layout structure.
