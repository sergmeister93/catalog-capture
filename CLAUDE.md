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

**Phase M (Hosted Migration) — Railway live; Cloudflare Access pending (2026-05-03 evening)** — app is running on Railway (project `accurate-liberation`, service `catalog-capture`, region `us-west2`, 1 GB volume at `/data`, env vars `GEMINI_API_KEY` / `USE_MOCK_GEMINI=false` / `GEMINI_MODEL=gemini-2.5-flash` set). Auto-deploys from `main`. End-to-end smoke test passed against real Gemini: upload → extract → review → export → CSV downloads to browser. Three follow-up shipments during the deploy session: (a) gitignore anchor fix (`94198e9`, direct push) that recovered the `service_photo.exports` source package which had been silently excluded by an unanchored `exports/` pattern; (b) PR #1 merged — `GET /inbound/exports/{filename}` for browser CSV downloads via hidden `<a download>`; (c) PR #2 merged — `DELETE /inbound/data` + "Clear Data" button next to "Check for Images" for a full volume reset (server purge + localStorage wipe). Source of truth for status, what shipped, and next-session kickoff prompt: [`docs/handover/10_hosted_migration_status.md`](docs/handover/10_hosted_migration_status.md). **Remaining step:** Cloudflare Access in front of the public URL with email allowlist — blocked on a domain decision (CFA requires a hostname inside a Cloudflare-managed zone; `*.up.railway.app` direct is not supported).

**Phase 7H (Production Hardening) — branch `feat/production-hardening` (2026-06-12)** — Cloudflare Access is **live** (`https://app.catalog-capture.com`, Zero Trust team `sbf322`, One-time PIN + email allowlist; the "pending" note in Phase M above is stale). Hardening pass shipped on this branch: (a) CSV spreadsheet-formula-injection escaping in `_normalize_cell` (leading `=`/`+`/`-`/`@`/tab/CR on *text* cells gets a `'` prefix; numeric cells exempt); (b) single-active-extraction lock — a second `POST /inbound/extract` while one runs returns `409 extraction_already_running`; (c) Gemini client timeout (`GEMINI_TIMEOUT_SECONDS`, default 150s) + transient-error retry (`GEMINI_MAX_RETRIES`, default 2; backoff 3/8/15s) + per-call token-usage log lines (`gemini_call_ok …`); (d) **parallel extraction** — images run through a `ThreadPoolExecutor` bounded by `EXTRACTION_CONCURRENCY` (default 3; 1 = old sequential behavior; mind Gemini RPM limits before raising); (e) upload magic-byte sniffing (`_sniff_image_format` — extension alone no longer admits a file) + 50-files-per-request cap; (f) `GET /healthz` + Docker `HEALTHCHECK`; (g) 48 tests for the `/inbound` pipeline in `backend/tests/inbound/` (filesystem-only, no Postgres needed); (h) GitHub Actions CI (`.github/workflows/ci.yml`: ruff + full pytest with a Postgres service container, frontend build); (i) ruff config in `backend/pyproject.toml` (rules F/E9/B/PLE only — style rules deliberately off).

**Phase 7A (SQLite Durability) — branch `feat/sqlite-durability` (2026-06-12, PR #3 merged earlier same day)** — `services/inbound_store.py` (stdlib sqlite3, WAL mode, file at `<APP_DATA_PATH>/catalog.db`) replaces (a) the in-memory `_jobs` dict and (b) browser-localStorage review state. Five tables: `extraction_jobs`, `extraction_job_images`, `review_items` (JSON-blob edits — draft layer stays as `inbound/*.json` files), `review_events` (append-only audit trail), `exports`. New endpoints: `PUT /inbound/review/{id}`, `POST`/`DELETE /inbound/review/{id}/approve`; `GET /inbound` items now carry a `review` block. **Export contract changed:** client sends `{extraction_ids}` only; the server builds the CSV from stored *approved* snapshots and 400s on any unapproved id — the footer button no longer bulk-approves (gotcha #13 fixed; `approved_at`/`approved_by` CSV columns now carry real approval provenance). Audit actor comes from the `Cf-Access-Authenticated-User-Email` header Cloudflare Access injects (falls back to `local-dev`). Dockerfile runs `--workers ${WEB_CONCURRENCY:-2}` — the single-worker constraint is lifted. Frontend autosaves edits (800 ms debounce, flush on Done Editing / approve / export) and one-time-migrates the old localStorage key server-side, then deletes it.

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

### Active — per-image inbound pipeline (filesystem artifacts + SQLite review/job state)

```
GET    /api/v1/inbound                       list all extraction JSONs in inbound/ (each item carries its saved `review` block, or null)
GET    /api/v1/inbound/input-images          list files in input_images/ (Upload screen left rail)
POST   /api/v1/inbound/input-images          multipart upload — drag-and-drop into input_images/ (25 MB/file cap, safe-basename + extension whitelist, collision-safe rename)
GET    /api/v1/inbound/images/{filename}     serve image from input_images/ (path-traversal defended)
GET    /api/v1/inbound/batches               group artifacts by (batch_name, batch_started_at_utc) for Recent Batches screen
POST   /api/v1/inbound/extract               kick off Gemini over input_images/ — combined extraction+pricing in one call (purges inbound/ + review rows first, runs in daemon thread, accepts optional {batch_name})
GET    /api/v1/inbound/extract/{job_id}      poll extraction progress (SQLite-backed; works across workers and survives restarts)
PUT    /api/v1/inbound/review/{id}           save a card's edited content (audit event: 'edited')
POST   /api/v1/inbound/review/{id}/approve   approve a card, snapshotting the on-screen content (audit: 'approved')
DELETE /api/v1/inbound/review/{id}/approve   remove approval, content untouched (audit: 'unapproved')
POST   /api/v1/inbound/export                body {extraction_ids} — CSV built from server-stored APPROVED snapshots only; 400 on any unapproved id
GET    /api/v1/inbound/exports/{filename}    stream a written CSV as a browser download
DELETE /api/v1/inbound/data                  full reset: wipes the three dirs AND every SQLite table
```

**Extraction job tracking + review state live in SQLite** — `services/inbound_store.py`, file at `<APP_DATA_PATH>/catalog.db` (`/data/catalog.db` on Railway). Stdlib `sqlite3`, WAL mode, per-call connections. The single-active-extraction 409 lock is a `BEGIN IMMEDIATE` check-and-insert, safe across worker processes. Orphaned jobs (server died mid-run; heartbeat `updated_at_utc` older than 300s) flip to `failed` lazily on read — never swept unconditionally at startup, so a respawned worker can't kill a sibling's live run.

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

### Phase M (Hosted Migration) gotchas (do not reintroduce)

14. **`APP_DATA_DIR` controls where filesystem state lives.** In container mode it defaults to `/data` (mounted Railway volume); in local dev it defaults to the repo root so `dev.bat` keeps writing to `inbound/`, `input_images/`, `exports/` as before. `inbound_routes.py` reads paths from `APP_DATA_PATH` — do not hardcode `REPO_ROOT / "inbound"` etc. The export-response `csv_path` is reported relative to `APP_DATA_PATH`, not `REPO_ROOT`.

15. **~~Single uvicorn worker is mandatory in the container~~ — lifted in Phase 7A.** Job state now lives in SQLite (`services/inbound_store.py`), so polling works across worker processes. The Dockerfile runs `--workers ${WEB_CONCURRENCY:-2}`. (Historical: the in-memory `_jobs` dict forced `--workers 1` until 2026-06-12.)

16. **The `/jobs` pipeline (dormant) loads `contracts/gemini_response_schema.json` at import time.** `submit_service.py` walks parent dirs from its installed location looking for `contracts/`. The Dockerfile drops a copy at `/contracts` so the walk-up succeeds even though the active `/inbound` flow doesn't need it. If you delete `COPY contracts /contracts` from the Dockerfile, container startup will crash on import.

17. **`prompts/*.md` must ship inside the installed package.** `pyproject.toml` declares `[tool.setuptools.package-data] service_photo = ["prompts/*.md", "prompts/*.txt"]`. Without this, `pip install ./backend` strips the prompts dir and the container errors with "Prompt template not found" on the first extraction. `inbound_extraction.py` resolves `PROMPT_PATH` package-relative (parents[1] from the services dir), not repo-relative.

18. **Single-origin SPA serving in `main.py` skips CORS entirely.** When `FRONTEND_DIST_DIR` (or `/app/frontend_dist`, or `<repo>/frontend/dist`) exists, `main.py` mounts `/assets` and a SPA catch-all so one uvicorn process serves both the React bundle and `/api/*`. Do **not** add CORS middleware — that would mean the production deployment is misconfigured.

19. **Local Docker test data lives in `_local_data/` at the project root** (gitignored). It's the host folder bind-mounted to `/data` inside the container. Don't confuse it with the legacy `exports/` / `inbound/` folders at the repo root, which are written by `dev.bat` runs only.

20. **Anchor `.gitignore` runtime-storage patterns to repo root.** A pattern like `exports/` (no leading `/`) matches `exports/` *anywhere* in the tree — including `backend/src/service_photo/exports/`, which is a real Python package. This silently excluded the `service_photo.exports` source code from git, made local Docker builds work (they copy from disk) but crashed Railway's clean checkout with `ModuleNotFoundError`. Fix shipped in commit `94198e9`: all runtime-storage entries are now anchored (`/exports/`, `/inbound/`, `/input_images/`, `/storage/`, `/_local_data/`). Apply the same anchoring to any future runtime-storage folder that shares a name with anything inside `backend/src/service_photo/`.

21. **Browser CSV downloads use a streaming GET endpoint, not the export POST response.** `POST /inbound/export` writes the CSV to `/data/exports/` and returns JSON with `csv_filename`. `GET /inbound/exports/{filename}` streams that file with `media_type="text/csv", filename=...` — `FileResponse(filename=...)` adds `Content-Disposition: attachment` automatically. Frontend triggers the download via a hidden `<a download href={exportDownloadUrl(...)}>` click in `InboundScreen.tsx` so the SPA state isn't disturbed. Path-traversal defense: `_SAFE_CSV_FILENAME` regex (`^[A-Za-z0-9._-]+\.csv$`) plus a resolved-path containment check against `EXPORTS_DIR`. Reuse this pattern for any future filename-in-URL endpoint.

22. **`DELETE /api/v1/inbound/data` has no server-side auth.** The "Clear Data" button on the Upload screen calls this endpoint to wipe `input_images/`, `inbound/`, and `exports/` on the volume. The frontend gates the call behind `window.confirm`; the backend assumes the request is authorized. **This is correct only because Cloudflare Access goes in front of the deployment.** If the Access layer is delayed, treat this endpoint as the same risk surface as the rest of the app — anyone with the URL can wipe state. The frontend also clears the two localStorage keys (`service-photo:active-extraction-v1`, `service-photo:inbound-review-state-v2`) so the UI doesn't show review state for items that no longer exist on disk.

### Phase 7A gotchas (do not reintroduce)

23. **`services/inbound_store.py` is stdlib `sqlite3` on purpose.** Don't reach for SQLAlchemy here — the SQLAlchemy/Postgres stack belongs to the dormant `/jobs` pipeline and is slated for deletion. Tests redirect the store with `monkeypatch.setattr(inbound_store, "DB_PATH", tmp_path / "catalog.db")` (same pattern as the dir constants). Every store function opens its own short-lived connection; the schema is created lazily on first connect per path and eagerly at app startup via `init_db()` in `main.py`'s lifespan.

24. **Orphaned-job recovery is lazy, never a startup sweep.** A job row left `queued`/`running` by a dead server flips to `failed` only when read (or when a new job is created) AND its `updated_at_utc` heartbeat is >300s old (`STALE_ACTIVE_JOB_SECONDS`). An unconditional "mark all active as failed at startup" looks simpler but is wrong with multiple workers: a respawned worker would kill a job legitimately running in a sibling worker's thread.

25. **Approval lives only on the server now.** The frontend's `approved` flag is a mirror of the API response — `handleApproveToggle` updates local state only after the approve/unapprove call succeeds, so the UI can never claim an approval the audit trail doesn't have. Export sends ids only; content always comes from the server's `review_items` snapshots. Don't add a client-side path that bypasses this (that was gotcha #13, now fixed).

26. **`review_items` rows are purged when a new extraction starts; `review_events` never are** (except by Clear Data). If you add anything keyed by `extraction_id`, decide explicitly which side of that line it lives on.

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
