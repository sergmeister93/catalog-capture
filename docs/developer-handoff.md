# Developer Handoff

Written for the engineer inheriting Catalog Capture. Skip the marketing; this is the shortest path to being productive.

---

## Day one: orient yourself

1. **Read `CLAUDE.md` first, not `README.md`.** The README is frozen at Phase 1. `CLAUDE.md` is the living orientation doc and lists 13 gotchas that will save you hours.
2. **Skim `docs/system-overview.md`** — one-page summary.
3. **Boot the app**: run `dev.bat`. It opens two `cmd` windows (backend, frontend) and points the browser at `http://localhost:5173/#/inbound`.
4. **Run the happy path end to end**:
   - Drop a couple of camera photos into `input_images/`.
   - Click **Run Gemini Extraction** on the Upload screen.
   - Watch the progress banner, then switch to Review.
   - Edit something, approve a card, click **Export Approved Items**.
   - Confirm a CSV appears in `exports/`.

If all six steps work, your environment is sound and you understand what the app does before touching any code.

---

## Day two: read the code in this order

1. `backend/src/service_photo/api/inbound_routes.py` — every endpoint the UI calls.
2. `backend/src/service_photo/services/inbound_extraction.py` — the orchestration core.
3. `backend/src/service_photo/integrations/real_gemini.py` — the single AI call that defines the product.
4. `contracts/gemini_response_schema.json` — the response shape you cannot break.
5. `contracts/csv_export_schema.md` — the export contract you cannot break.
6. `frontend/src/screens/InboundScreen.tsx` — all three screens live here.

Deliberately skip on day two:
- The `/jobs/*` pipeline (`api/routes.py`, all DB services, 12 ORM models). It is dormant and will not execute in the active flow.
- `docs/00_–03_*`. Read these when you actually need the DB pipeline's specs.

---

## What matters most

- **The Gemini prompt** (`backend/src/service_photo/prompts/listing_extraction_v1.md`). This single file defines the product's output quality.
- **The response schema** (`contracts/gemini_response_schema.json`). Any prompt change must preserve this shape, because both the UI and the CSV depend on it.
- **The CSV contract** (`contracts/csv_export_schema.md`). The deliverable.
- **The `inbound/` directory**. Source of truth for the Review screen. Every artifact here is the output of one Gemini call.

---

## What's risky

Read these before editing the named files.

- **`_jobs` in-memory dict** (`api/inbound_routes.py`). Module-level state. Don't assume it survives a restart. Don't reach into it from outside the routes file.
- **StrictMode + localStorage handoff** (gotcha #8 in `CLAUDE.md`). Don't consume a one-shot localStorage handoff on read; clear it only when the work hits a terminal state.
- **`.env` absolute-path resolver** (gotcha #5, `core/config.py`). Do not switch it back to a relative path — it breaks under `dev.bat`.
- **SDK choice** (gotcha #6). Do not reinstall `google-generativeai`. Use `google-genai` for native `google_search` grounding.
- **`dev.bat` doesn't kill stale processes** (gotcha #7). If your edits don't appear, `tasklist | grep python` and kill duplicates before assuming the code is wrong.
- **`docs/03_ui_design.md` is stale** (gotcha #10). Source of truth for UI tokens is `frontend/src/index.css`.

---

## Validate these assumptions first

Before writing any new feature code, get answers:

1. **Is multi-reviewer access a near-term requirement?** Determines whether you can stay on filesystem + in-memory or must promote to a database.
2. **Is the CSV format right?** The column contract is self-referential. If a real target marketplace exists, align first.
3. **What's the Gemini spend envelope?** Determines whether rate limiting is urgent.
4. **Does the dormant DB pipeline have a future?** Either plan to revive it or plan to delete it — carrying it indefinitely is drag.

---

## Quick reference

### Run it
```
dev.bat                 # launches backend + frontend + browser
extract.bat             # CLI-only Gemini extraction (no UI)
extract.bat --purge     # wipe inbound/ first
```

### Environment
```
# .env at repo root
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash        # or current model
USE_MOCK_GEMINI=false
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/service_photo_dev
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/service_photo_test
```

### Postgres (only needed for the dormant DB pipeline)
```
docker run --name service-photo-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:15
createdb -h localhost -U postgres service_photo_dev
createdb -h localhost -U postgres service_photo_test
cd backend && alembic upgrade head
pytest
```

### Key paths
| Path | Purpose |
|---|---|
| `input_images/` | Raw photos — upload here |
| `inbound/` | Per-image extraction JSON artifacts (gitignored) |
| `exports/` | CSV output (gitignored) |
| `backend/src/service_photo/api/inbound_routes.py` | Active backend routes |
| `backend/src/service_photo/services/inbound_extraction.py` | Extraction orchestration |
| `backend/src/service_photo/integrations/real_gemini.py` | Gemini client |
| `backend/src/service_photo/prompts/listing_extraction_v1.md` | The prompt |
| `frontend/src/screens/InboundScreen.tsx` | All three UI screens |
| `contracts/gemini_response_schema.json` | Response contract |
| `contracts/csv_export_schema.md` | Export contract |

### Common operations

**Change the prompt.**
Edit `prompts/listing_extraction_v1.md`. Confirm the response still matches `contracts/gemini_response_schema.json`. If not, update the schema, the CSV transform in `services/export_service.py`, and any UI rendering in `InboundScreen.tsx`.

**Add a CSV column.**
1. Update `contracts/csv_export_schema.md`.
2. Update `services/export_service.py`.
3. Update the prompt and `contracts/gemini_response_schema.json` if the data is new.

**Debug a Gemini call.**
Set `USE_MOCK_GEMINI=true` to bypass Gemini for iteration; otherwise check the latest JSON in `inbound/` for the raw response.

**Add a new endpoint.**
Add to `api/inbound_routes.py`. The file is large — follow existing patterns (response model, error shape unwrapped to `{error, message}`, never return raw `HTTPException`).

---

## The dormant pipeline, if you need it

The `/jobs/*` pipeline is fully implemented with 47/47 passing tests. If you revive it:

1. Re-run `pytest` first — dependency upgrades since Phase 2 (pydantic, `google-genai`) may have regressed it.
2. Read `contracts/backend_workflow_spec.md` and `docs/decisions/0001-draft-vs-review-layers.md`.
3. Remember: draft tables are read-only; review tables are source of truth for approval and export; status history is append-only.
4. The forward-ref fix in `schemas/review.py` (gotcha #1) and the error-shape convention (gotcha #2) are load-bearing.

---

## First-week backlog suggestion

If you want to make the project measurably better in five days without starting a big feature:

- Day 1: update `README.md` and `docs/03_ui_design.md` to current state.
- Day 2: add integration tests for the three most-used `/inbound` routes (`extract`, `export`, `input-images`).
- Day 3: replace `print` with structured logging; add `/health`.
- Day 4: promote `_jobs` to SQLite (Phase 7 candidate #1).
- Day 5: add basic shared-credential auth and rate-limit `/inbound/extract`.

At the end of that week, the scorecard in `production-readiness-assessment.md` moves from four **Not Ready** to one or zero, and the project is a credible internal tool.
