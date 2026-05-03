# Service Photo POC — Project CLAUDE.md

## What This Project Is

AI-assisted used-camera listing workflow: photos → Gemini draft → human review → CSV export.
One job = one item. Human approval is required before export. This is a **proof of concept**, not a production system.

See [`docs/00_project_documentation.md`](docs/00_project_documentation.md) for full context.

---

## Current Phase

**Phase 1 — Contract & Schema Definition (complete)**
**Phase 2 — Backend Implementation (complete + verified: 47/47 pytest passing)**
**Phase 3 — Frontend Review Shell (paused after pivot to per-image inbound flow)**
**Phase 3.5 — Per-image Inbound Flow (complete)**
**Phase 4 — End-to-End Validation (complete as of 2026-04-19 — UI-triggered extraction + E2E smoke passed)**
**Phase 5 — Pricing / Web Enrichment (complete as of 2026-04-19 — single-pass: extraction + pricing in one grounded Gemini call; verified end-to-end 5/5 images against live API)**
**Phase 6 — UX Rebrand & Polish (complete as of 2026-04-19)** — app rebranded to "Catalog Capture"; nav renamed Upload / Review / Batch History (internal `#/inbound` route and `inbound/` folder on disk unchanged); Prep's button actually kicks off extraction and hands off to Review via localStorage; batch metadata persisted in artifact meta; new `/inbound/batches` endpoint; drag-and-drop upload via new `POST /inbound/input-images`; layout density, visual polish, StrictMode polling fix, **6G enterprise polish pass** (refreshed design tokens in `frontend/src/index.css` — type scale, spacing scale, radius scale `sm`/`md`/`lg`, shadow tokens, Manrope wordmark + Inter UI; upgraded buttons, cards, inputs, pills; Upload & Review screen copy cleanup — no more vendor/system strings in UI; all-caps labels switched to title case; `humanizeModelName`/`humanizePricingTag`/`humanizeWarning` helpers in `InboundScreen.tsx` scrub raw `snake_case` and `[BRACKETED_FLAGS]` before display) all shipped.

**Phase 7 — Open (2026-04-19)** — next-step candidates (promotion of in-memory `_jobs` to SQLite for durability, marketplace posting integrations, per-field confidence scoring, multi-reviewer queues, self-hosting Inter/Manrope) documented in [`docs/claude_code_phase7_handoff.md`](docs/claude_code_phase7_handoff.md). Confirm direction with Sergey before starting.

Full task checklist: [`docs/progress.md`](docs/progress.md)

### The pivot (read this before touching anything)

Mid-Phase-3, the workflow shifted from "one job = one item, multiple photos" to **"one image = one product listing"**. To avoid disturbing the verified DB-backed pipeline, the new flow runs **in parallel** to it:

- **Old `/jobs` pipeline (DB-backed, 8 endpoints, 47/47 tests passing):** untouched but currently dormant in the UI. Code is dead-but-not-deleted.
- **New `/inbound` pipeline (filesystem-backed, no DB):** powers the active UX. Drop photos → run Gemini per-image → review/edit/approve → bulk export to CSV.

Both pipelines share the same Gemini prompt and CSV column contract.

### Phase 2 verified stack (to reproduce the working state)

- **Python 3.12** (3.14 has no wheels for pinned deps). Install via `winget install Python.Python.3.12`.
- **PostgreSQL via Docker** — native winget install failed to set a superuser password. Use:
  ```
  docker run --name service-photo-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:15
  ```
- **Env vars** (cmd):
  ```
  set DATABASE_URL=postgresql://postgres:postgres@localhost:5432/service_photo_dev
  set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/service_photo_test
  ```
- **Bootstrap from `backend/`**:
  ```
  py -3.12 -m venv .venv
  .venv\Scripts\activate
  pip install -e ".[dev]"
  createdb -h localhost -U postgres service_photo_dev
  createdb -h localhost -U postgres service_photo_test
  alembic upgrade head
  pytest
  ```

### Bugs fixed during Phase 2 verification (do not reintroduce)

1. **Forward-ref timing** — `ReviewPayload` references `ListingJob` / `ListingJobImage` / `DraftContent` via `TYPE_CHECKING`. The runtime imports + `ReviewPayload.model_rebuild()` **must** live at the bottom of `schemas/review.py`, not in `main.py`. FastAPI's `@router.get(..., response_model=ReviewPayload)` decorator builds a `TypeAdapter` at import time, which requires forward refs already resolved.
2. **Error response shape** — `main.py` has a custom `HTTPException` handler that unwraps dict `detail` payloads. Routes raise `HTTPException(detail={"error": "...", "message": "..."})` and the handler returns that dict directly (not wrapped in `{"detail": ...}`). The OpenAPI contract + tests depend on this.
3. **Decimal → JSONB** — `export_service._orm_to_dict` converts `Decimal` to `str` before insertion into the `export_payload_snapshot` JSONB column. Python's stdlib `json.dumps` (which SQLAlchemy uses by default) can't serialize `Decimal`.
4. **Test fixture transaction** — `tests/conftest.py::override_get_db` must NOT call `db.rollback()` on exception. The outer `db` fixture owns the connection-level transaction; rolling back inside the override wipes state the test itself is reading after a 4xx response.

### Bug fixed during Phase 4 (do not reintroduce)

5. **`.env` path resolution in `core/config.py`** — pydantic-settings was configured with `env_file=".env"`, which is resolved relative to the current working directory. `dev.bat` launches uvicorn from `backend/`, so the backend couldn't find the repo-root `.env` and `GEMINI_API_KEY` came up empty, breaking UI-triggered extraction. Fixed by computing an absolute path: `Path(__file__).resolve().parents[4] / ".env"` (parents: core → service_photo → src → backend → repo root). Keep it absolute; any relative path will regress depending on how the server is launched.

### Bugs fixed during Phase 5 (do not reintroduce)

6. **SDK migration: `google-generativeai` → `google-genai`.** Phase 5 single-pass requires Google Search grounding on Gemini 2.x. The older `google-generativeai==0.5.4` SDK treats any dict in `tools=[{...}]` as a `FunctionDeclaration`, so both `{"google_search": {}}` and the legacy `{"google_search_retrieval": {}}` raise `ValueError: Unknown field for FunctionDeclaration`. The newer `google-genai` SDK has native grounding via `types.Tool(google_search=types.GoogleSearch())` passed through `types.GenerateContentConfig`. `backend/pyproject.toml` now pins `google-genai>=1.0` and `pydantic>=2.11` (google-genai needs newer pydantic than the old `2.7.1` pin). `real_gemini.py` was fully rewritten: uses `genai.Client(api_key=...).models.generate_content(model=..., contents=[...], config=...)` and `types.Part.from_bytes(data=..., mime_type=...)` for image parts. The old SDK should not be reinstalled.

7. **Stale-process trap on `dev.bat` relaunches.** `dev.bat` does NOT kill prior uvicorn / Vite processes before launching. Multiple relaunches stack duplicate listeners on ports 8000 and 5173 — Windows load-balances between them, so some requests hit the old code even after you edit a file and relaunch. Symptom: edits don't appear to take effect, or stale errors persist across relaunches. **Recovery**: `tasklist | grep python`, `tasklist | grep node`, kill the duplicates with `taskkill //F //PID <pid>`, then relaunch. Consider hardening `dev.bat` to `taskkill /F /FI "WINDOWTITLE eq Backend*"` before starting.

---

## Repository Layout (quick reference)

| Folder / file | Contents |
|---|---|
| `docs/` | Planning + reference docs (numbered `00_`–`03_`), decisions (ADRs), progress tracker, handoff docs |
| `contracts/` | OpenAPI spec, JSON Schemas, approval rules, workflow spec, Gemini response schema, CSV export spec |
| `backend/` | FastAPI + PostgreSQL service. Package root: `src/service_photo/`. Old DB pipeline lives in `api/routes.py`; new per-image inbound pipeline lives in `api/inbound_routes.py`. |
| `frontend/` | Vite + React + TS UI. Active screen is `src/screens/InboundScreen.tsx`. Old job/review screens still mounted but unused. |
| `scripts/run_gemini_extraction.py` | CLI: thin wrapper around `service_photo.services.inbound_extraction`. Self-contained `.env` loader. `--purge` flag wipes prior run JSONs. |
| `backend/src/service_photo/services/inbound_extraction.py` | Shared extraction service — both the CLI and `POST /inbound/extract` route delegate here. Scans a folder, calls Gemini per image, writes JSONs. Exposes `on_image_start` / `on_image_done` callbacks for progress reporting. |
| `input_images/` | Drop zone for raw photos (one image = one product listing). Read by extraction script and served by `GET /api/v1/inbound/images/{filename}`. |
| `inbound/` | Per-image extraction artifacts (`extraction_<UTC>__<image-stem>.json`). **Gitignored.** Source of truth for the Inbound screen. |
| `exports/` | Bulk-export CSVs (`listings_<UTC>.csv`). **Gitignored.** Written by `POST /api/v1/inbound/export`. |
| `dev.bat` | One-click launcher: starts backend + frontend in two cmd windows, opens browser to `#/inbound`. |
| `extract.bat` | One-click runner for the per-image Gemini extraction script. |
| `.env` | Repo-root env file (gitignored). Contains `GEMINI_API_KEY`, `GEMINI_MODEL`, `DATABASE_URL`, `USE_MOCK_GEMINI`. |
| `test_data/sample_images/` | Older sample camera photos (pre-pivot). |
| `storage/` | Runtime artifacts for the old DB pipeline (gitignored). |

Full tree: [`docs/00_project_documentation.md §12`](docs/00_project_documentation.md)

---

## Critical Contracts (read before touching backend or frontend)

| File | What it governs |
|---|---|
| [`contracts/openapi_service_photo_poc.yaml`](contracts/openapi_service_photo_poc.yaml) | All 8 REST endpoints + every request/response schema |
| [`contracts/backend_workflow_spec.md`](contracts/backend_workflow_spec.md) | Step-by-step backend logic for each endpoint, status transitions, DB write order |
| [`contracts/approval_validation_rules.md`](contracts/approval_validation_rules.md) | Exact approval gate: required fields, rule IDs, error codes |
| [`contracts/review_payload_schema.json`](contracts/review_payload_schema.json) | JSON Schema for `GET /jobs/{id}/review-payload` response |
| [`contracts/gemini_response_schema.json`](contracts/gemini_response_schema.json) | JSON Schema for Gemini draft response → populates `listing_draft_*` tables |
| [`contracts/csv_export_schema.md`](contracts/csv_export_schema.md) | CSV column order, field mapping, transform rules, export validation gate |
| [`docs/02_physical_schema_spec.md`](docs/02_physical_schema_spec.md) | PostgreSQL DDL spec (12 tables, types, constraints, indexes) |

---

## Architecture Decisions (do not re-debate without reading ADRs)

- **Two content layers, not one.** Draft tables (`listing_draft_*`) = AI output, read-only after creation. Review tables (`listing_review_*`) = human-edited, source of truth for approval and export. Never merge them.
  See [`docs/decisions/0001-draft-vs-review-layers.md`](docs/decisions/0001-draft-vs-review-layers.md)

- **Status history is append-only.** Every status transition writes a new row to `listing_job_status_history`. Never update old rows.

- **Export reads reviewed layer only.** Draft content must never appear in a CSV export.

- **Approval collects all failures, does not short-circuit.** Return every failing rule in one response.

---

## Database: 12 Core Tables (Phase 1 scope)

```
listing_jobs
listing_job_images
listing_job_status_history
listing_draft_overview
listing_draft_description
listing_draft_specifications
listing_draft_accessories
listing_review_overview          ← required for approval
listing_review_description       ← required for approval
listing_review_specifications    ← required for approval (≥1 spec field)
listing_review_accessories       ← required for approval
listing_exports
```

---

## API Endpoints

### Active — per-image inbound pipeline (filesystem-backed, no DB)

```
GET    /api/v1/inbound                       list all extraction JSONs in inbound/
GET    /api/v1/inbound/input-images          list files in input_images/ (Upload screen left rail)
POST   /api/v1/inbound/input-images          multipart upload — drag-and-drop into input_images/ (25 MB/file cap, safe-basename + extension whitelist, collision-safe rename)
GET    /api/v1/inbound/images/{filename}     serve image from input_images/ (path-traversal defended)
GET    /api/v1/inbound/batches               group artifacts by (batch_name, batch_started_at_utc) for Recent Batches screen
POST   /api/v1/inbound/extract               kick off Gemini over input_images/ — combined extraction+pricing in one call (purges inbound/ first, runs in daemon thread, accepts optional {batch_name})
GET    /api/v1/inbound/extract/{job_id}      poll extraction progress (status, completed, current_image, per-image results)
POST   /api/v1/inbound/export                bulk-write listings_<UTC>.csv to exports/
```

**Extraction job tracking is in-memory** — `_jobs` dict in `inbound_routes.py` keyed by job_id. Survives server uptime only; a restart drops any in-flight job state (but completed JSONs on disk remain authoritative). Good enough for a POC; promote to SQLite if durability is ever needed.

### Phase 5 pricing artifacts (single-pass, shape)

Phase 5 ships as a **single-pass** flow: the extraction prompt asks Gemini to return both the visual extraction and pricing in one call, with Google Search grounding (`tools=[{"google_search": {}}]`) attached to that same multimodal call. There is no separate `/inbound/price` endpoint — re-running `/inbound/extract` is the only way to refresh pricing.

Each `inbound/extraction_<UTC>__<stem>.json` therefore contains an optional top-level `pricing` block alongside `response`:

- `pricing` — Gemini-grounded result returned inline with the extraction. Fields: `product`, `pricing.{ebay_sold_avg, mpb_retail, keh_retail, bh_used}`, `market_valuation.{fair_price, deal_threshold}`, `market_summary`, `sources[]`, `uncertainty_tags[]`. All fields nullable — Gemini may return partial data. Block is absent entirely when Gemini chose not to return pricing for the item.

Meta sidecar fields (`meta.pricing_fetched_at_utc`, `pricing_web_search_enabled`) let the UI distinguish priced vs. never-priced without re-parsing the block. Schema validation covers the combined response via [`contracts/gemini_response_schema.json`](contracts/gemini_response_schema.json) — the optional `pricing` property is part of that schema rather than a separate file.

CSV now has 9 additional columns (between accessories and provenance): `fair_price`, `deal_threshold`, `ebay_sold_avg`, `mpb_retail`, `keh_retail`, `bh_used`, `market_summary`, `pricing_sources_json`, `pricing_fetched_at_utc`. Sources are flattened to a compact JSON string so downstream tools can parse back.

### Dormant — original DB-backed pipeline (still mounted, currently unused by the UI)

```
POST   /jobs                         create listing job
POST   /jobs/{id}/images             register job image
POST   /jobs/{id}/submit             submit to AI (triggers Gemini)
GET    /jobs/{id}                    get job + images + status history
GET    /jobs/{id}/review-payload     get draft + review content combined
PUT    /jobs/{id}/review             save reviewed content (upsert, per-section)
POST   /jobs/{id}/approve            run approval gate → approved
POST   /jobs/{id}/export             generate CSV → exported
```

---

## Status Lifecycle

```
initialized → submitted_to_ai → ai_response_received → ready_for_review
→ under_review → approved → exported

Exceptions: validation_failed | ai_error | needs_rework | rejected
```

---

## Daily Workflow (Inbound flow)

**UI-triggered path (default):**
1. Drop new photos into `input_images/` (one image = one product listing).
2. Double-click `dev.bat`. Backend + frontend launch in two cmd windows; browser opens to `http://localhost:5173/#/inbound`.
3. Click **Run Gemini Extraction** (top-right). Progress banner shows live status (`Extracting · 3 of 5 · current: foo.jpg`). `inbound/` is purged first so each run starts clean. Each Gemini call produces extraction **and** pricing in one shot via Google Search grounding.
4. When the banner flips to **Extraction complete**, cards auto-populate with both the product details and (when Gemini returned one) the pricing block.
5. Review each card. Edit content or pricing numbers if needed. Per-card **Approve** toggles the green state. Edits persist in `localStorage` (key: `service-photo:inbound-review-state-v2` — bumped from v1 when the pricing shape was added).
6. Click **Approve All & Export to CSV** at the bottom. CSV lands in `exports/listings_<UTC>.csv` (pricing cells blank for any card where Gemini returned no pricing block).

**CLI path (power-user fallback):**
Double-click `extract.bat` instead of using the UI button. Preserves prior runs by default; pass `--purge` to wipe first.

## Next Tasks

Phase 6 is closed. Phase 7 is open — see [`docs/claude_code_phase7_handoff.md`](docs/claude_code_phase7_handoff.md) for the queue of candidate directions and small open nits from the polish pass. Confirm with Sergey before starting any of them.

### Phase 6 gotchas (do not reintroduce)

8. **React StrictMode + single-shot handoff.** In dev, React StrictMode double-invokes mount effects. If a mount effect clears a resource on read *and* another mount effect has a cleanup that tears down a timer, the remount finds nothing to resume. Concretely: `InboundScreen` reads `ACTIVE_EXTRACTION_KEY` from localStorage and starts a poll timer; a separate `useEffect(() => () => stopPolling())` wipes the timer between the two StrictMode runs. The original code called `clearActiveExtraction()` on first read, so the re-mount found an empty handoff and the banner froze at "Queued…". Fix: only clear the handoff when the poll tick observes a terminal status (`completed` / `failed`). Pattern to remember — *don't consume a one-shot handoff on read if any sibling effect's cleanup can undo the work it triggered.*

9. **Display-name rename only.** The app is branded "Catalog Capture" and the nav uses Upload / Review / Batch History, but the `inbound/` filesystem directory, the `#/inbound` hash route, the `api/inbound.ts` frontend module, and the `/api/v1/inbound/*` backend routes are unchanged. Renaming those is a separate, larger change — if a future task asks to "rename inbound," clarify display vs. internal before touching anything.

### Phase 6G gotchas (do not reintroduce)

10. **`frontend/src/index.css` is the single source of truth for design tokens.** Phase 6G replaced the original brand-spec tokens (2px radius, Roboto stack, sparse tokens) with a full enterprise system: type scale (`--fs-xs`→`--fs-3xl`), spacing scale (`--space-1`→`--space-12`, 4/8px grid), radius scale (`sm` 6 / `md` 10 / `lg` 14 / `pill`), shadow tokens (`xs`/`sm`/`md`/`lg` + `--shadow-focus`), neutral palette refresh (`#f6f7f9` page, `#111827` primary text, `#6b7280` muted). **`docs/03_ui_design.md` is stale for token values** — read the CSS. The radius change is a deliberate override of the original "sharp 2px" brand spec; polish brief explicitly asked for 10–14px card radii.

11. **Don't show raw vendor/system strings in the UI.** Phase 6G added `humanizeModelName`, `humanizePlatform`, `titleCaseCondition`, `humanizePricingTag`, `humanizeWarning`, and `formatFetchedAt` helpers at the bottom of `frontend/src/screens/InboundScreen.tsx`. Any new surface that renders Gemini output (model names, `snake_case` field keys, `[BRACKETED_FLAGS]`, raw UTC timestamps, platform identifiers, condition strings) should route through the matching helper or add a new one. The rule: **no snake_case, no bracketed system flags, no file paths, no raw ISO timestamps reach the user.**

12. **Fonts load via Google Fonts CDN.** `index.css` `@import`s Inter + Manrope from `fonts.googleapis.com`. Works anywhere with internet; fails silently (system stack fallback) offline. If Sergey ever wants a self-contained / enterprise-air-gapped build, self-host the woff2 files and drop the `@import`. Don't add other font families without asking.

13. **The "Export Approved Items" button is the single export trigger.** The footer CTA performs **bulk approve + export** in one click — it bulk-approves any not-yet-approved cards, then writes the CSV. The per-card "Approve" / "Remove Approval" toggle only affects the visual state and the approved-count; the footer button does not respect an "only export approved" mode. If a reviewer wants to exclude items, they should remove them from the batch, not just leave them unapproved. Consider tightening the footer behavior in Phase 7 if this causes confusion.

---

## What Is Explicitly Out of Scope (Phase 1)

- Web enrichment (reviews, pricing, comparables, sources)
- User authentication
- Marketplace posting
- Pricing automation
- Pagination on any endpoint
- Soft deletes

---

## Code Style (from global CLAUDE.md, reiterated)

- Python unless project dictates otherwise
- Comment heavily (Sergey is learning — comments explain the why)
- Descriptive variable names, no single-letter vars except counters
- Simple over clever
- Docstring at top of every script: what it does, inputs, outputs
- No dependency if the task can be done without one
