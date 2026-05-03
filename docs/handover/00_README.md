# Catalog Capture — Self-Host Migration Handover Bundle

_Snapshot taken: 2026-05-03._

This folder is a **point-in-time copy** of the files needed to plan Phase 2 of the self-host migration with a fresh model (GPT or otherwise). Files are numbered in the order you should share them.

> ⚠️ These are **copies**, not the source of truth. If you make edits during planning, edit the originals (paths listed below) and re-snapshot, or the live repo will drift from this bundle.

---

## What to paste into the new chat (in this order)

| # | File in this folder | Original location | Purpose |
|---|---|---|---|
| 1 | `01_self_host_migration_spec.md` | `docs/05_self_host_migration_spec.md` | **Start here.** The actual tech spec — architecture, decisions, 7-phase plan, risk register |
| 2 | `02_CLAUDE.md` | `CLAUDE.md` (repo root) | Project workflow, gotchas, contracts pointers |
| 3 | `03_phase7_handoff.md` | `docs/claude_code_phase7_handoff.md` | Broader Phase 7 menu so the new model doesn't double-scope |
| 4 | `04_project_documentation.md` | `docs/00_project_documentation.md` | Full project narrative — what the app does and why |
| 5 | `05_inbound_routes.py` | `backend/src/service_photo/api/inbound_routes.py` | Active route module — shows the in-memory `_jobs` pattern (relevant to Risk R3 in the spec) |
| 6 | `06_config.py` | `backend/src/service_photo/core/config.py` | The `parents[4]` env-file resolver (Risk R4 — likely needs refactor for containers) |
| 7 | `07_backend_pyproject.toml` | `backend/pyproject.toml` | Backend deps + Python version pin |
| 8 | `08_frontend_package.json` | `frontend/package.json` | Frontend deps + npm scripts |
| 9 | `09_dev.bat` | `dev.bat` (repo root) | Current Windows launcher — the Linux equivalent is what we're building |

## Suggested kickoff prompt for the new chat

> I'm planning Phase 2 of a self-host migration for a small POC web app called Catalog Capture. The tech spec is in the first file (`01_self_host_migration_spec.md`); read that first, then the supporting context. After you've read everything, I want you to (a) flag anything in the spec that's wrong, ambiguous, or under-scoped, (b) propose a concrete implementation order for Phase M2 (containerization), and (c) tell me what you'd want to know before writing the actual Dockerfiles and `docker-compose.yml`. Don't write any code yet.

## Files deliberately NOT in this bundle

- The dormant `/jobs` Postgres pipeline (`api/routes.py`, `services/export_service.py`, etc.) — out of scope, would distract.
- The contracts folder (`contracts/openapi_*.yaml`, JSON schemas) — only relevant if the migration touches the API surface, which it shouldn't.
- The full `frontend/src/` tree — the migration is a deployment change, not a UI change.
- Sample images, exports, prior extraction JSONs — not needed for planning.

If the new model asks for any of the above, you can pull them in on demand.
