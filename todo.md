# TODO

## One-click Launcher

- [x] Add `project.config.json` with usage scene and APSM selection.
- [x] Add `specs/requirements.md` as executable requirements source.
- [x] Add root `AGENTS.md` with vibe-coding and workbench rules.
- [x] Copy `scripts/project_launcher.py` from the vibe-coding skill.
- [x] Copy `scripts/apsm_validate.py` from the vibe-coding skill.
- [x] Add backend start bridge for `apps/api`.
- [x] Run `scripts/project_launcher.py` to generate launchers and runtime metadata.
- [x] Run APSM validation.
- [x] Run backend/frontend regression checks.

## Future

- [x] Allow independent panes to submit concurrently without a global composer lock.
- [x] Package release ZIP with `python scripts/project_launcher.py --package`.
- [x] Add PDF attachment extraction with NoHarness grep reading and Harness progressive block reading.
- [ ] Replace Playwright `/api` route fixtures with real-backend e2e coverage; keep any remaining fixture tests clearly labeled as UI-only.
- [ ] Add UI-based API key setup flow if the app is handed to users who cannot set environment variables.
