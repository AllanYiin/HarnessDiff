# Local JSON Storage Format

The local JSON store is the system of record for HarnessDiff MVP.

## Root Layout

```text
data/
  projects/
    {project_id}/
      project.json
      config/
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
```

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
