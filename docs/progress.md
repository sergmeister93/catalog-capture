# Progress Tracker

Running checklist across sessions. Update at the end of each working session.

---

## Current Phase

**Phase 6 — UX Rebrand & Polish (complete — 2026-04-19)**
Phases 1–5 complete. Phase 6 ran in sub-phases (6A flow+persistence, 6B density, 6C visual polish, 6D strict-mode polling fix, 6E drag-and-drop upload, 6F terminology rename, **6G enterprise polish + copy cleanup**). Phase 7 is now open — see [`claude_code_phase7_handoff.md`](claude_code_phase7_handoff.md).

---

## Completed

### Docs
- [x] Project overview and scope — `docs/00_project_documentation.md`
- [x] Logical database schema architecture — `docs/01_database_schema_architecture.md`
- [x] Physical schema spec for PostgreSQL — `docs/02_physical_schema_spec.md`
- [x] UI design notes — `docs/03_ui_design.md`
- [x] System architecture diagram source — `docs/diagrams/system_architecture.jsx`

### Contracts
- [x] OpenAPI spec — `contracts/openapi_service_photo_poc.yaml`
- [x] Review payload JSON Schema — `contracts/review_payload_schema.json`
- [x] Approval validation rules — `contracts/approval_validation_rules.md`
- [x] Backend workflow spec — `contracts/backend_workflow_spec.md`

### Repository
- [x] Folder structure reorganization (UI→frontend, images_archive→test_data, numbered docs)
- [x] Backend/frontend/storage/scripts scaffolding
- [x] Root `README.md`, `.gitignore`, `.env.example`
- [x] ADR: draft-vs-review layer separation

---

## In Progress — Remaining Phase 1

- [x] Gemini response JSON Schema — `contracts/gemini_response_schema.json`
- [x] CSV export field mapping spec — `contracts/csv_export_schema.md`
- [x] First-pass Gemini prompt — `backend/src/service_photo/prompts/listing_extraction_v1.md`

---

## Phase 2 — Backend Implementation ✓ COMPLETE + VERIFIED (47/47 tests passing)

- [x] Initial PostgreSQL migration SQL — `docs/04_initial_migration.md` + `backend/src/service_photo/db/migrations/initial_schema.sql`
- [x] Backend scaffold extended — all module directories + `__init__.py` files in place
- [x] Handoff docs complete — `docs/claude_code_starter_prompt.md`, `docs/claude_code_backend_implementation_guide.md`, `docs/claude_code_seed_data_spec.md`
- [x] `backend/pyproject.toml` — all runtime + dev dependencies pinned
- [x] `core/config.py` — pydantic-settings with DATABASE_URL, GEMINI_API_KEY, STORAGE_BASE_PATH, LOG_LEVEL, USE_MOCK_GEMINI
- [x] `db/base.py` + `db/session.py` — declarative base + get_db() FastAPI dependency
- [x] Alembic wired: `alembic.ini` + `migrations/env.py` + `script.py.mako` + `versions/001_initial_schema.py`
- [x] 12 SQLAlchemy ORM models in `models/` (one file per table, mirroring physical schema exactly)
- [x] Pydantic schemas in `schemas/` — jobs, draft, review, export, errors
- [x] Repository helpers in `repositories/` — jobs, images, draft, review, exports
- [x] Job number generator — `utils/job_number.py` (JOB-YYYYMMDD-NNN format)
- [x] Gemini integration: `GeminiClientInterface` + `MockGeminiClient` (Canon EOS R6) + `RealGeminiClient` stub
- [x] Service layer: job_service, image_service, submit_service, review_payload_service, review_service, approval_service, export_service
- [x] CSV export generator — `exports/csv_generator.py` (exact column order per spec, all transform rules applied)
- [x] All 8 FastAPI route handlers — `api/routes.py`
- [x] FastAPI app entry point — `main.py`
- [x] Test fixtures: `tests/fixtures/factories.py` — all 7 seed scenarios (A–G)
- [x] Unit tests: job number, approval validator, CSV transforms
- [x] Integration tests: jobs, images, submit, review, approval, export
- [x] E2E test: `tests/test_workflow_e2e.py` — full happy path create→export
- [x] `backend/README.md` — local run instructions

---

## Phase 3 — Frontend Review Shell (PAUSED — superseded by Phase 3.5 pivot)

- [x] Framework chosen: Vite + React + TypeScript
- [x] M1 — Scaffold, design tokens, app shell, typed API client, backend ping
- [x] M2 — Job creation + image upload (metadata-only) + submit-to-AI flow
- [x] M3 — Review screen (draft vs. review side-by-side, per-section save) — built but mental model abandoned
- [x] Prep screen (Option A) — left image rail + batch name + Approve button (stubbed)
- [~] M4–M5 — **dropped**, replaced by Phase 3.5 inbound flow

Old screens (PrepScreen, NewJobScreen, JobDetailScreen, ReviewScreen, HomeScreen) are still mounted in the router but unused. Dead-but-not-deleted pending Phase 4 outcome.

---

## Phase 3.5 — Per-Image Inbound Flow (built 2026-04-19; awaiting Sergey's E2E)

- [x] Real Gemini client — `backend/src/service_photo/integrations/real_gemini.py` (multimodal, lazy SDK import, JSON code-fence stripping, model overridable via `GEMINI_MODEL` env)
- [x] Per-image extraction CLI — `scripts/run_gemini_extraction.py` (self-contained `.env` loader, one Gemini call per image, one JSON per image, schema validation non-fatal)
- [x] Backend inbound router — `backend/src/service_photo/api/inbound_routes.py` mounted at `/api/v1/inbound`
  - [x] `GET /api/v1/inbound` — list + reshape extraction JSONs
  - [x] `GET /api/v1/inbound/images/{filename}` — serve from `input_images/` with path-traversal defense
  - [x] `POST /api/v1/inbound/export` — write `exports/listings_<UTC>.csv` per CSV contract
- [x] Frontend Inbound screen — `frontend/src/screens/InboundScreen.tsx` (per-card edit/approve, localStorage persistence, sticky bottom bulk-export bar, schema-mismatch + API-error badges)
- [x] Hash route `#/inbound` + nav link
- [x] `dev.bat` and `extract.bat` launchers at repo root
- [x] `inbound/` and `exports/` added to `.gitignore`
- [x] Frontend typecheck clean; backend endpoints verified via TestClient
- [ ] Sergey-driven end-to-end walkthrough → Phase 4

---

## Phase 4 — End-to-End Validation ✓ COMPLETE (smoke test passed 2026-04-19)

Scope expanded mid-session: instead of running the CLI separately and refreshing the UI, Sergey asked for seamless E2E — kick off extraction from the UI, track progress live, get notified on completion. That became the actual deliverable for Phase 4.

- [x] Shared extraction service — `backend/src/service_photo/services/inbound_extraction.py`. Both the CLI (`scripts/run_gemini_extraction.py`) and the new HTTP endpoint delegate here, so the two pipelines can't drift.
- [x] `POST /api/v1/inbound/extract` — synchronously discovers images, registers an in-memory job, spawns a daemon thread, returns `202 {job_id, status, total}`. Purges `inbound/*.json` first so the UI reflects only the latest run.
- [x] `GET /api/v1/inbound/extract/{job_id}` — returns the full job state (status, completed/total, current_image, per-image results).
- [x] In-memory job registry with thread lock — `_jobs` dict in `inbound_routes.py`. POC-grade, not durable across restarts.
- [x] Frontend: `startExtraction()` + `getExtractionStatus()` in `frontend/src/api/inbound.ts`; `ExtractionBanner` component + 1.5s polling loop in `InboundScreen.tsx`. Banner shows progress bar, current image name, model, per-image counts; auto-refreshes the card list on completion.
- [x] CLI refactored to use the shared service; added `--purge` flag (opt-in, CLI preserves history by default).
- [x] `core/config.py` fixed to load `.env` from an absolute repo-root path (pydantic-settings was resolving `.env` relative to cwd, which broke when uvicorn launched from `backend/`).
- [x] 47/47 backend tests still passing.
- [x] Sergey smoke test passed: drop photos → click button → progress bar → cards populate → export CSV.

Walkthrough test plan still available for future regression-style runs: [`docs/claude_code_phase4_e2e_handoff.md`](claude_code_phase4_e2e_handoff.md).

---

## Phase 5 — Pricing / Web Enrichment ✓ COMPLETE (2026-04-19)

**Single-pass** Gemini-grounded pricing: the extraction prompt produces both the visual extraction and pricing in one multimodal + web-grounded call. Pricing is editable on review and exported to CSV. When Gemini returns no pricing block, the CSV cells are blank and export is not blocked.

- [x] Enrichment approach decided: **Gemini with `google_search` grounding tool attached to the extraction call itself**. Initially built as a second-pass flow; Sergey redirected mid-build to a single-pass design — rationale: "Gemini should consume the images, understand the products, then go out with those products to get pricing" in one motion rather than requiring a second prompt.
- [x] Prompt — [`backend/src/service_photo/prompts/listing_extraction_v1.md`](../backend/src/service_photo/prompts/listing_extraction_v1.md) now asks for both the extraction (Part A — visual) and pricing (Part B — web search) in one response.
- [x] Response schema — [`contracts/gemini_response_schema.json`](../contracts/gemini_response_schema.json) extended with an optional top-level `pricing` property (inlined rather than `$ref`'d because the jsonschema loader doesn't resolve external file refs). All pricing fields nullable so partial Gemini returns still validate.
- [x] Gemini interface: `analyse_images(image_paths, prompt, enable_web_search=False)`. Real client wires `tools=[{"google_search": {}}]` when `enable_web_search=True`. Mock client returns a deterministic Canon R6 payload with pricing inline.
- [x] Extraction service — [`backend/src/service_photo/services/inbound_extraction.py`](../backend/src/service_photo/services/inbound_extraction.py) calls `analyse_images(..., enable_web_search=True)`, hoists the `response["pricing"]` block up to the artifact root (`artifact["pricing"]`), and stamps `meta.pricing_fetched_at_utc` / `meta.pricing_web_search_enabled` when a block is present.
- [x] Removed the separate `/inbound/price` flow entirely: deleted `services/inbound_pricing.py`, `prompts/pricing_v1.md`, `contracts/pricing_response_schema.json`, `tests/unit/test_inbound_pricing.py`, `_pricing_jobs` registry, `POST /inbound/price`, `GET /inbound/price/{job_id}`.
- [x] CSV extended with 9 pricing columns between accessories and provenance: `fair_price`, `deal_threshold`, `ebay_sold_avg`, `mpb_retail`, `keh_retail`, `bh_used`, `market_summary`, `pricing_sources_json`, `pricing_fetched_at_utc`.
- [x] [`contracts/csv_export_schema.md`](../contracts/csv_export_schema.md) updated with the new columns + Phase 5 note.
- [x] Frontend: typed `PricingBlock` / `PricingPlatforms` / `PricingValuation` / `PricingSource`; `PricingSection` shows editable currency fields, editable market summary, read-only sources table with clickable URLs, uncertainty-tag badges. When pricing is absent, shows a muted "Gemini did not return pricing" note.
- [x] Frontend: removed separate pricing-job UI (banner, bulk button, per-card retry). Re-running extraction is the only way to refresh pricing.
- [x] Frontend: `localStorage` key bumped `v1` → `v2` (added `editedPricing`); fresh backend pricing adopts into local state when local is null.
- [x] Docs refreshed — this file + [`CLAUDE.md`](../CLAUDE.md).

---

## Phase 6 — UX Rebrand & Polish (in progress — 2026-04-19)

App branded as **Catalog Capture**. Top-level nav renamed **Upload / Review / Recent Batches** (internal routes `#/`, `#/inbound`, `#/batches` unchanged; `inbound/` folder on disk untouched).

**6A — Flow + batch persistence**
- [x] Prep's "Approve → Send to Gemini" actually kicks off extraction (was a stub) and auto-navigates to Review via a localStorage handoff (`state/extractionHandoff.ts`).
- [x] Backend threads `batch_name` + `batch_started_at_utc` through `services/inbound_extraction.py` → stamped into every artifact's `meta`.
- [x] New `GET /api/v1/inbound/batches` groups artifacts by `(batch_name, batch_started_at_utc)`; legacy artifacts roll up under a synthetic `__legacy__` id.
- [x] New `BatchesScreen` (`#/batches`) lists one row per upload with image/ok/failed counters.
- [x] Removed the "Run Gemini Extraction" button from Review — extraction is always started from Upload.
- [x] Router simplified to 3 routes (`prep`, `inbound` with optional `batchId`, `batches`). Old DB-pipeline screens deleted (`HomeScreen`, `NewJobScreen`, `JobDetailScreen`, `ReviewScreen`, `stubs/inputImages.ts`, `api/client.ts`, `api/types.ts`, `state/recentJobs.ts`). Backend DB routes still mounted.

**6B — Layout density**
- [x] Root cause of huge vertical gaps in Review cards: `Section` used `display: flex; flex-direction: column`, and `Field` had `flex: 1 1 200px` — in column-flex the basis is interpreted as **height**, so every Field got ~200px of vertical space. Fixed by switching the Section inner to `display: grid; rowGap: 6px` (grid children get natural `min-content` height).
- [x] Pricing section moved to sit between Description and Specifications.
- [x] Image column sticky (`position: sticky; top: 12px`), 220px wide; card marginBottom 14px; body padding `14px 16px`.

**6C — Visual polish**
- [x] Navbar now white (matches black-on-white logo canvas); logo bumped to 48px; wordmark "Catalog Capture".
- [x] `--ui-border-strong` token; cards + secondary buttons use it.
- [x] `.btn-primary` gets a red-tinted box-shadow + hover `translateY(-1px)` for lift.
- [x] Section headers: 2px `--brand-primary` bottom border + dark bold label (was 1px muted).

**6D — StrictMode polling fix**
- [x] Review banner was freezing at "Queued…" because `clearActiveExtraction()` ran on first read. React StrictMode in dev double-invokes the mount effect, and the companion unmount effect wiped the poll timer between runs — the re-mount then found the handoff already cleared and never resumed. Fixed by clearing the handoff only when the job hits a terminal state (`completed` / `failed`).

**6E — Drag-and-drop upload**
- [x] New `POST /api/v1/inbound/input-images` accepts multipart `files[]`. Enforces: safe-basename filename regex, extension in `IMAGE_SUFFIXES`, 25 MB cap per file, collision-safe destination (`foo.jpg` → `foo-1.jpg`). Per-file success/failure in response so one bad file doesn't kill the batch.
- [x] `uploadInputImages()` API client.
- [x] Upload (formerly Prep) page: left-rail drop zone (dashed border, click-to-browse fallback via hidden `<input type="file">`), plus a window-level drag overlay so drops anywhere on the page work. Per-file success/error summary under the zone; thumbnail list auto-refreshes.

**6G — Enterprise polish + copy cleanup**
- [x] Rewrote `frontend/src/index.css` as a full design-token system: type scale (`--fs-xs`→`--fs-3xl`), spacing scale (`--space-1`→`--space-12`, 4/8px grid), radius scale (`sm` 6 / `md` 10 / `lg` 14 / `pill`), shadow tokens (`xs`/`sm`/`md`/`lg`), `--shadow-focus` ring, refreshed neutral palette (`#f6f7f9` page, `#111827` primary text, `#6b7280` muted, `#e4e7eb` borders), semantic color families for success/error/warning/info. Added Google Fonts `@import` for Inter (body) + Manrope (wordmark); introduced `--font-display` token.
- [x] Upgraded `.btn` variants (new `.btn-danger`, `.btn-ghost`, `.btn-sm`, `.btn-lg`; real `:focus-visible` rings; 40px default height), `.card` (14px radius, soft shadow, generous padding, `.card__section` divider helper), global form control styles (`input`, `textarea`, `select` with consistent 40px height, inset shadow, focus ring, `aria-invalid` state, styled select caret, `accent-color`'d checkboxes), `.status-pill` variants (`--success`/`--error`/`--warning`/`--info`), `.action-bar` utility (blurred translucent sticky footer).
- [x] Upload screen copy cleanup (`frontend/src/screens/PrepScreen.tsx`): `INPUT IMAGES` → `Upload Images`, dynamic `No images added yet` / `N image(s) added`, `Refresh` → `Check for Images`, drop zone split to `Drag images here` + `or click to browse` + separate `Supported formats: …` line, heading `New Upload` → `Create New Batch`, intro rewritten to remove `input_images/` path reference, label `UPLOAD NAME` → `Batch Name`, placeholder → `batchname_uploadername`, helper → `This name will appear in Batch History.`, summary secondary line switches between `Add images to continue` / `Ready for analysis`, CTA `Approve → Send to Gemini` → `Start Analysis` (with context-aware disabled helper), footer link `View recent batches →` → `View Batch History →`. Dropped uppercase transform from field labels.
- [x] Review screen copy cleanup (`frontend/src/screens/InboundScreen.tsx`): intro rewritten, `Refresh` → `Refresh Results`, progress banner language (`Extracting` → `Analyzing`, `Extraction complete` → `Analysis complete`, `N of M images · gemini-2.5-flash` → `N of M images processed · Model: Gemini 2.5 Flash`, `current:` → `Currently processing:`), card chip `✓ APPROVED` → `✓ Approved` (pill radius, no uppercase), `Unapprove` → `Remove Approval`, `Done editing` → `Done Editing`, schema/api error chips renamed (`Schema mismatch` → `Needs Review`, `API error` → `Analysis Error`), `Gemini call failed.` → `AI analysis failed for this item.`
- [x] Field-label title-case sweep on Review cards: Overview (`Family` → `Product Family`, `Serial visible` → `Visible Serial Number`, all others title-case), Description (`Short title` → `Listing Title`, `Visible wear notes` → `Visible Wear`), Pricing (`Fair price (USD)` → `Estimated Fair Price (USD)`, `Deal threshold (USD)` → `Target Buy Price (USD)`, `eBay sold (avg)` → `eBay Sold Average`, `MPB retail` → `MPB Retail`, etc.), Specifications (all title-case), Accessories (`Missing typical` → `Commonly Missing`). `Gemini warnings` section → `AI Warnings`.
- [x] Sticky footer: `N of M approved` → `N of M item(s) approved`, `✓ ready` → `✓ Ready to export`, `Exported N rows to exports/listings_…csv` → `Exported N item(s) to CSV` (raw path dropped), primary CTA `Approve All & Export to CSV` → `Export Approved Items`.
- [x] Added display humanizers in `InboundScreen.tsx`: `humanizeModelName` (e.g. `gemini-2.5-flash` → `Gemini 2.5 Flash`), `humanizePlatform` (e.g. `ebay` → `eBay`, `b_and_h` → `B&H`), `titleCaseCondition`, `humanizePricingTag` (turns raw `keh_retail [ESTIMATED_LENS_PRICE]` into `KEH price is estimated from comparable listings.` etc.), `humanizeWarning` (strips snake_case keys and bracketed flags), `formatFetchedAt` (UTC ISO → localized short datetime). Uncertainty tag badge row replaced with a **Pricing Notes** list styled as a soft warning callout.
- [x] Nav: `RECENT BATCHES` → `Batch History`; NavLink styling lost the uppercase transform, gained semibold on active.
- [x] Wordmark: `.navbar__brand` now uses Manrope 700, 19px, `letter-spacing: -0.01em`, title case, color `#0f172a` (dark navy) — reads as a deliberate wordmark while the rest of the UI stays in Inter. No data-shape or interaction changes; purely cosmetic.

**6F — Terminology rename**
- [x] Navbar wordmark: Review → **Catalog Capture**; nav links: Prep → **Upload**, Inbound → **Review**.
- [x] Page copy: "New Batch" → "New Upload"; "Batch Name" → "Upload Name"; stray "from Prep" links → "from Upload".
- [x] Only display strings changed. The `inbound/` directory, `#/inbound` route, and `api/inbound.ts` module are untouched (internal references).

---

## Deferred (Future Phases)

- Web enrichment (reviews, pricing, sources, comparables)
- User authentication and role-based access
- Marketplace posting integrations (eBay, Shopify)
- Inventory system integration
- Confidence scoring by field
- Approval queues and multi-reviewer workflows

---

## Session Log

| Date | Session Focus | Outcome |
|---|---|---|
| 2026-04-19 | Contract package generation + repo restructure + handoff | OpenAPI spec, JSON Schema, approval rules, workflow spec, folder restructure, README/.gitignore/.env.example, ADR 0001, progress tracker, project CLAUDE.md |
| 2026-04-19 | Gemini schema + prompt intake | Placed `contracts/gemini_response_schema.json` and `backend/src/service_photo/prompts/listing_extraction_v1.md`; removed misplaced docs/ originals |
| 2026-04-19 | Initial migration review + placement | Added `extraction_warnings JSONB` to `listing_draft_overview`; placed `docs/04_initial_migration.md` + `backend/src/service_photo/db/migrations/initial_schema.sql`; updated physical schema spec |
| 2026-04-19 | Scaffold extension + handoff docs | Extended backend scaffold with `core/`, `models/`, `repositories/`, `integrations/`, `exports/` modules + all `__init__.py` files; fixed all stale file paths in starter prompt and implementation guide; documented structure decision and extraction_warnings gap in guide §15–16; updated CLAUDE.md for next chat handoff |
| 2026-04-19 | Phase 2 backend implementation | Built complete FastAPI + SQLAlchemy backend: pyproject.toml, Alembic migration, 12 ORM models, Pydantic schemas, 5 repository modules, 7 service modules, MockGeminiClient, CSV generator, 8 API routes, 7-scenario factory, unit + integration + e2e tests, README |
| 2026-04-19 | Phase 3 Prep screen (Option A) | Sergey redirected: the first screen should show images currently in the repo-root `input_images/` folder on the left, with a batch-name input and a big "Approve → Send to Gemini" button on the right. One batch = one listing = one item (all photos depict the same item + its accessories). Built PrepScreen with left rail (thumbnails + filename + size + Refresh button) and right panel (Batch Name + count summary + Approve button). Stubbed image list (`src/stubs/inputImages.ts` returns 5 hardcoded filenames); actual thumbnails resolve by mirroring `input_images/*.jpg` into `frontend/public/input_images/` (gitignored). Wired `logo.png` into navbar alongside wordmark; added top-right "Prep" / "Recent Jobs" nav links. Routing rework: `#/` → PrepScreen (new home), `#/jobs` → previous home (job list). Approve button is UI-only stub — shows a success banner but no backend call. Two backend endpoints marked TODO(backend) for next session: `GET /input-images` and `POST /batches`. Naming note: Sergey uses "Approve" both for sending-to-Gemini and for the formal export gate; UI distinguishes by position and labels ("Approve → Send to Gemini" vs the downstream "Approve for Export"). Review editor from earlier in the session was flagged as "not what I had in mind"; it still exists and works but UX direction is open. |
| 2026-04-19 | Phase 3 M3 — review editor | Before build, spotted 3 contract mismatches in M1 types: approval failure is HTTP 400 (not 422), envelope field is `validation_failures` with `{rule, detail}` items (not `failures` with `{rule_id, ...}`), and approval success returns `ListingJob` directly (not wrapped); fixed all three in types.ts + client.ts. Added `SaveReviewInput` Pydantic-mirror types. Extended hash router with `/jobs/:id/review`. Built ReviewScreen with 4 side-by-side panels (overview, description, specifications, accessories): each shows draft readout on left and editable form on right, "Copy from draft" button to prefill, per-section "Save" button hitting PUT /jobs/{id}/review with just that section, inline save-state badge (saving / ✓ saved / ✗ error). Client-side validation of required fields + numeric parsing for megapixels/weight_grams. Linked from JobDetail when status is review-eligible. Typecheck clean; e2e smoke (create→submit→save overview) passed through proxy. |
| 2026-04-19 | Phase 3 M2 — job create + image register + submit | Hash-based router (no react-router dep), localStorage-backed recent-jobs list (compensates for missing GET /jobs backend route), Home + NewJob + JobDetail screens, image picker registers metadata with synthetic file_paths (FIXME(upload) marked for Phase 4 real-upload work), Submit-to-AI button gated by status + image count, status history panel, fixed Vite proxy to target `/api/v1` prefix. Typecheck clean; POST /jobs through proxy verified end-to-end (created JOB-20260419-001). |
| 2026-04-19 | Phase 3 M1 — frontend scaffold | Vite + React + TS set up in `frontend/`; design tokens CSS from `03_ui_design.md`; navbar + page shell; typed API client (`src/api/client.ts` + `types.ts`) covering all 8 endpoints; Vite dev-server proxy `/api` → `localhost:8000` (no backend CORS changes needed); `HealthCheck` component pings `/openapi.json`; `npm run typecheck` clean; dev server boots and serves HTTP 200 on :5173 |
| 2026-04-19 | Phase 3.5 — per-image inbound flow (pivot) | **Mid-Phase-3 pivot:** workflow shifted from "one job = one item with multiple photos" to "one image = one product listing." Built parallel filesystem-backed pipeline alongside the dormant DB pipeline. New deliverables: (1) `RealGeminiClient` with multimodal `generate_content`, lazy SDK import, JSON code-fence stripping, `gemini-2.5-flash` default; (2) `scripts/run_gemini_extraction.py` — self-contained `.env` loader, makes N Gemini calls (one per image in `input_images/`), drops one timestamped JSON per image into `inbound/`, includes started/finished/duration/model/prompt-path/schema-valid meta; (3) `api/inbound_routes.py` mounted at `/api/v1/inbound` with three endpoints (list, image-server with path-traversal defense, bulk export); (4) `InboundScreen.tsx` — one card per JSON, image left + 4 sections right (overview/description/specs/accessories), per-card edit/approve toggles, localStorage state (`service-photo:inbound-review-state-v1`), green tint when approved, amber badge on schema mismatch, red badge on API error, sticky bottom "Approve All & Export to CSV" bar; (5) hash route `#/inbound` + navbar link; (6) `dev.bat` (two-window launcher) and `extract.bat` at repo root; (7) `inbound/` + `exports/` gitignored; (8) `.env` at repo root with `GEMINI_API_KEY` (rotated mid-session after Sergey pasted it in chat) + `GEMINI_MODEL=gemini-2.5-flash`. Backend verified via TestClient (5 inbound items list/parse, image serve, CSV write with proper column order + blank handling + line-flatten). Frontend typecheck clean. **Path bug fixed:** `parents[5]` resolved one level too high (to `ServicePhoto/`); corrected to `parents[4]` (`UsedItemsListing_App/`). **Architectural decision:** old DB pipeline left intact (dead-but-not-deleted, 47/47 tests still pass) so Phase 4 outcome can decide which pipeline survives. Spec field types loosened to `unknown` in TS client because Gemini occasionally returns `"33MP"` strings instead of numbers. Pricing search asked about and correctly deferred per scope. Sergey called wrap on UI work; next session is end-to-end validation. |
| 2026-04-19 | Phase 2 verification + bugfixes | Installed Python 3.12 + deps, brought up Postgres via Docker (winget install left no usable password — pivoted), ran Alembic migration, fixed 4 bugs uncovered by pytest: (1) `ReviewPayload.model_rebuild()` timing — moved forward-ref resolution to bottom of `schemas/review.py` so it runs before FastAPI decorator builds its TypeAdapter; (2) error response shape — added `HTTPException` handler in `main.py` to unwrap dict details so responses are `{"error",...}` at top level per OpenAPI contract; (3) Decimal JSONB serialization — `export_service._orm_to_dict` now converts Decimal→str for `export_payload_snapshot`; (4) test fixture — removed `db.rollback()` from `override_get_db` which was nuking the shared outer transaction on 4xx paths. **Final result: 47/47 tests passing.** |
| 2026-04-19 | Phase 5 — pricing / web enrichment | Second-pass Gemini-grounded pricing. New contract: `contracts/pricing_response_schema.json` (all nullable — Gemini returns partials). New prompt: `backend/src/service_photo/prompts/pricing_v1.md` (derived from Sergey's proven manual prompt; `{{PRODUCT_IDENTITY}}` placeholder; searches eBay sold, MPB/KEH retail, B&H used; USD only; `uncertainty_tags[]` for estimates; sources[] with clickable URLs). `GeminiClientInterface.analyse_text(prompt, enable_web_search=False)` added; real client wires `tools=[{"google_search": {}}]` when enabled; mock returns deterministic Canon R6 pricing for tests. Service: `services/inbound_pricing.py` — `run_pricing_for_artifact` resolves identity (brand+model+variant+mount → short_title → product_name), calls Gemini, validates against schema (non-fatal), atomic file write, merges `pricing` block on success or writes `pricing_error` on failure, clears stale errors on retry. Routes: `POST /inbound/price` (body `extraction_ids: null` = all unpriced, or explicit list) + `GET /inbound/price/{job_id}`. **Serial** worker — web-grounded Gemini throttles under parallel load. New `_pricing_jobs` dict + lock mirrors extraction pattern. CSV extended with 9 columns between accessories and provenance: `fair_price`, `deal_threshold`, `ebay_sold_avg`, `mpb_retail`, `keh_retail`, `bh_used`, `market_summary`, `pricing_sources_json`, `pricing_fetched_at_utc`. Sources flattened to compact JSON string so downstream parses back. `market_summary` added to `_FLATTEN_NEWLINE_FIELDS`. Frontend: `PricingBlock`/`PricingError` + pricing-job types; `startPricing`/`getPricingStatus`. `InboundScreen`: `PricingSection` component (empty/error/data modes, editable currency fields + market summary, read-only sources table with clickable URLs, uncertainty-tag badges), `PricingBanner` polling loop, bulk "Price N unpriced" header button (disabled when `unpricedCount===0`), per-card "Get pricing"/"Retry", pricing included in export payload. `localStorage` key bumped v1→v2 (added `editedPricing`); fresh backend pricing adopts into local when local is null. Pytest: `backend/tests/unit/test_inbound_pricing.py` — 5 classes covering identity resolution, run success (+ stale-error clear), run failures (missing artifact, missing identity), CSV column contract, CSV row cells populated/blank. Decisions pushed back on: doc recommended "inline pricing on extraction" — Sergey confirmed second-pass instead (cheaper failure mode, supports retry-without-re-extraction). Failure handling: pricing errors surface on the card but **do not block export** per Sergey. Dropped shutter-count field per Sergey. Market summary lives in all three places (artifact + card + CSV) per Sergey. Old DB pipeline untouched — 47/47 tests still pass. |
| 2026-04-19 | Phase 5 SDK migration + live verification | After the two-pass → single-pass pivot, first live run failed with `ValueError('Unknown field for FunctionDeclaration: google_search')`. Root cause: `google-generativeai==0.5.4` (the SDK we had) treats any dict in `tools=[{...}]` as a function-calling `FunctionDeclaration` and doesn't support native Google Search grounding at all. Tried `google_search_retrieval` as a fallback — same error. Migrated to the newer `google-genai` SDK, which exposes native grounding via `types.Tool(google_search=types.GoogleSearch())` threaded through `types.GenerateContentConfig`. Rewrote `real_gemini.py` end-to-end: `genai.Client(api_key=...).models.generate_content(model=..., contents=[...], config=...)` + `types.Part.from_bytes(...)` for image parts. Uninstalled `google-generativeai`. Updated `pyproject.toml`: `google-genai>=1.0` replaces `google-generativeai==0.5.4`; bumped `pydantic>=2.11` (and `pydantic-settings>=2.2.1`) because google-genai needs newer pydantic than the old `2.7.1` pin. **Debug detour worth remembering**: three uvicorn and two Vite processes had stacked up on ports 8000/5173 from multiple `dev.bat` relaunches, so requests were hitting whichever stale listener Windows load-balanced to — that's why SDK edits appeared to have no effect. `tasklist | grep python` + `taskkill //F //PID ...` cleared it. **Live verification**: kicked off extraction via `POST /api/v1/inbound/extract`, polled to terminal state — 5/5 images succeeded on `gemini-2.5-flash`, 21–43s per image, 1 non-fatal schema warning (`megapixels: "14.2 MP"` string where schema expects number or null — UI tolerates it). Pricing blocks returned inline as designed. Handed off for fresh `dev.bat` launch. |
| 2026-04-19 | Phase 5 pivot — two-pass → single-pass pricing | Sergey rejected the second-pass pricing UX and redirected to inline pricing: Gemini should return the `pricing` block in the same call that produces the extraction, with `google_search` grounding attached. Merged the old `pricing_v1.md` prompt into `listing_extraction_v1.md` as Part A (visual) + Part B (web search). Extended `contracts/gemini_response_schema.json` with an optional top-level `pricing` property (inlined — jsonschema loader can't resolve external `$ref`s without custom setup). Simplified `GeminiClientInterface` to a single method `analyse_images(image_paths, prompt, enable_web_search=False)`; real client attaches `tools=[{"google_search": {}}]` when enabled; mock returns a combined payload. Extraction service now calls `analyse_images(..., enable_web_search=True)` and hoists `response["pricing"]` up to `artifact["pricing"]`. Deleted `services/inbound_pricing.py`, `prompts/pricing_v1.md`, `contracts/pricing_response_schema.json`, `tests/unit/test_inbound_pricing.py`, the `_pricing_jobs` registry, `POST /inbound/price`, `GET /inbound/price/{job_id}`. Frontend: removed `startPricing` / `getPricingStatus` / `PricingJob` / `PricingError` / `PricingBanner` / bulk "Price N unpriced" / per-card "Get pricing" / "Retry" / `pricing_error` references / `unpricedCount`; simplified `PricingSection` to display-and-edit only (no retry affordance — re-running extraction is the way to refresh). CSV output unchanged (9 columns stay). `localStorage` v2 stays. Typecheck clean. |
| 2026-04-19 | Phase 6 — UX rebrand & polish | **6A flow + persistence:** Prep's "Approve → Send to Gemini" now actually kicks off `POST /inbound/extract` and hands off via `localStorage` (`service-photo:active-extraction-v1`) to Review, which resumes polling. Removed the separate "Run Gemini Extraction" button from Review. Backend now threads `batch_name` + `batch_started_at_utc` through `services/inbound_extraction.py` into every artifact's `meta`. New `GET /inbound/batches` groups artifacts into upload-runs; new `BatchesScreen` at `#/batches` lists them. Router collapsed to 3 routes (`prep`, `inbound`, `batches`); old DB-pipeline screens and their helpers deleted (backend DB routes still mounted but dormant). **6B density fix:** root cause of ~200px of vertical dead space per Field in Review cards was `Section` using `display: flex; flex-direction: column` paired with `Field { flex: 1 1 200px }` — in column-flex the basis is **height**. Switched Section inner to `display: grid; rowGap: 6px` (grid children get natural `min-content` height). Moved PricingSection between Description and Specifications. Image column sticky at 220px. **6C visual polish:** navbar white to match the logo's white canvas (was onyx-black — logo looked boxed); logo 48px; wordmark set to "Catalog Capture". New `--ui-border-strong` token; cards + secondary buttons adopt it. `.btn-primary` gets red-tinted box-shadow + hover `translateY(-1px)`. Section headers: 2px `--brand-primary` bottom border + dark bold label. **6D StrictMode polling fix:** Review banner was freezing at "Queued…". Root cause: `clearActiveExtraction()` ran on first effect read; in dev, React StrictMode double-invokes the mount effect, and a sibling unmount effect's cleanup wipes the poll timer between the two runs. Re-mount then found the handoff already cleared and never resumed polling. Fix: only clear the handoff when the poll tick observes a terminal status. **6E drag-and-drop upload:** new `POST /api/v1/inbound/input-images` accepts multipart `files[]`, enforces safe-basename regex + extension whitelist + 25 MB cap, auto-renames on collision (`foo.jpg` → `foo-1.jpg`), returns per-file success/failure so one bad file doesn't abort the batch. Upload page drops a dashed drop zone into the left rail (click-to-browse fallback via hidden `<input type="file">`) plus a window-level drag overlay so drops anywhere on the page work. `python-multipart` 0.0.26 already installed; no backend dep changes. **6F terminology rename:** display strings only — wordmark "Review" → "Catalog Capture"; nav Prep → Upload, Inbound → Review; "New Batch" → "New Upload"; "Batch Name" → "Upload Name". Landing page is Upload (`#/` → prep route). Internal names untouched: `inbound/` dir, `#/inbound` route, `api/inbound.ts`, `/api/v1/inbound/*`. 47/47 backend tests still pass. Frontend typecheck clean throughout. |
| 2026-04-19 | Phase 6G — enterprise polish + copy cleanup | Rewrote `frontend/src/index.css` as a full token system (type/space/radius/shadow scales, refreshed neutrals, Inter + Manrope via Google Fonts, `--font-display` for the wordmark). Upgraded `.btn` (primary/secondary/danger/ghost + sm/lg variants with real `:focus-visible` rings), `.card` (14px radius, soft shadow, `.card__section` divider helper), global form controls (40px inputs, focus rings, `aria-invalid`, styled `select` caret, `accent-color` checkboxes), `.status-pill` semantic variants, `.action-bar` utility. Upload screen copy cleanup: `INPUT IMAGES` → `Upload Images`, dynamic empty/count states, `Refresh` → `Check for Images`, heading `New Upload` → `Create New Batch`, intro no longer mentions `input_images/`, label `UPLOAD NAME` → `Batch Name`, placeholder `batchname_uploadername`, helper `This name will appear in Batch History.`, CTA `Approve → Send to Gemini` → `Start Analysis` with context-aware disabled helper text, footer link → `View Batch History →`. Review screen copy cleanup: intro rewritten, `Refresh` → `Refresh Results`, progress banner language humanized (`Extracting` → `Analyzing`, `Extraction complete` → `Analysis complete`, `current:` → `Currently processing:`, model string run through `humanizeModelName`), card chip `✓ APPROVED` → `✓ Approved` (pill, title case), schema/API badges renamed, `Unapprove` → `Remove Approval`, `Gemini call failed.` → `AI analysis failed for this item.`, `Gemini warnings` section → `AI Warnings`. Full title-case sweep on all field labels (Overview/Description/Pricing/Specifications/Accessories): highlights `Family` → `Product Family`, `Serial visible` → `Visible Serial Number`, `Short title` → `Listing Title`, `Visible wear notes` → `Visible Wear`, `Fair price (USD)` → `Estimated Fair Price (USD)`, `Deal threshold (USD)` → `Target Buy Price (USD)`, `eBay sold (avg)` → `eBay Sold Average`, `Missing typical` → `Commonly Missing`. Sticky footer: `N of M approved` → `N of M items approved`, `✓ ready` → `✓ Ready to export`, raw `.csv` path replaced with `Exported N items to CSV`, CTA → `Export Approved Items`. Top nav: `RECENT BATCHES` → `Batch History`; all-caps transform dropped from NavLink. Wordmark moved to Manrope 700 / dark navy via new `--font-display` token. Added helpers at the bottom of `InboundScreen.tsx` that scrub every remaining piece of vendor/system language: `humanizeModelName`, `humanizePlatform`, `titleCaseCondition`, `humanizePricingTag` (rewrites `keh_retail [ESTIMATED_LENS_PRICE]` etc. into plain English), `humanizeWarning`, `formatFetchedAt`. Uncertainty badge row replaced with a "Pricing Notes" callout. No workflow, data shape, or API changes — cosmetic + copy only. Typecheck clean; 47/47 backend tests still pass. Phase 6 closed. |
| 2026-04-21 | Architecture diagram + full project audit & handoff pack | Produced presentation-ready system architecture (`docs/system-architecture-diagram.svg` + executive & technical `.mmd` sources + `system-architecture-summary.md` + `system-architecture-components.md`). Then reverse-engineered the build process into a seven-document audit: `project-audit-and-development-spec.md` (full 13-section audit with Evidenced/Inferred/Uncertain labels), `component-build-inventory.md` (structured table of every component), `implementation-sequence.md` (phase-by-phase chronology), `open-issues-and-risks.md` (Confirmed/Probable/Unknowns + risk matrix), `production-readiness-assessment.md` (10-category scorecard: 1 Ready / 5 Partial / 4 Not Ready), `system-overview.md` (one-page orientation), `developer-handoff.md` (day-one / day-two / first-week brief). Rewrote `README.md` (previously stuck at "Phase 1 — scaffolded but not implemented") to reflect current Phase 6-complete state with links into the new audit pack + known-constraints callout. Left `CLAUDE.md` untouched as the curated live orientation doc. Did not rewrite `docs/03_ui_design.md` (flagged stale; real rewrite, not a touch-up — deferred). Top audit findings worth action: (1) zero automated test coverage on the active `/inbound` pipeline — 47/47 covers only dormant DB; (2) dormant DB pipeline not re-verified after pydantic ≥2.11 + google-genai upgrades; (3) `InboundScreen.tsx` (1301 LOC) and `inbound_routes.py` (943 LOC) are refactor targets; (4) `_jobs` in-memory tracker volatility confirmed as top Phase 7 promotion candidate. |
| 2026-04-19 | Phase 4 — UI-triggered extraction + E2E smoke | Sergey asked for seamless E2E rather than CLI-plus-refresh: kick off extraction from the UI, track progress live, get notified on completion. Built it. (1) Extracted `backend/src/service_photo/services/inbound_extraction.py` as a shared service — both the CLI and the new endpoint delegate here, with optional `on_image_start`/`on_image_done` progress callbacks so CLI can print and HTTP can update job state. (2) Added `POST /api/v1/inbound/extract` (returns 202 with `job_id`, spawns daemon thread, purges prior JSONs so re-runs are clean) and `GET /api/v1/inbound/extract/{job_id}` (returns full job state). State is an in-memory `_jobs` dict guarded by a `threading.Lock`; POC-grade, not durable. (3) Frontend: added `startExtraction()` + `getExtractionStatus()` typed clients; built `ExtractionBanner` with progress bar, current-image label, and per-image counts; polling at 1.5s intervals with auto-refresh of card list on completion. (4) CLI refactored to use the shared service; added `--purge` flag (opt-in — CLI preserves history by default, UI always purges). (5) **Bug fix**: `core/config.py` was using `env_file=".env"` relative to cwd. `dev.bat` launches uvicorn from `backend/` so the backend never found the repo-root `.env` → `GEMINI_API_KEY` empty → extraction failed. Fixed by computing an absolute path `Path(__file__).resolve().parents[4] / ".env"`. First real backend consumer of the key so the bug had been latent. 47/47 backend tests still passing. Sergey ran the smoke test and confirmed the full E2E flow works: drop photos → click button → progress bar → cards populate → approve → CSV. Also reviewed a third-party frontend-design skill (`.claude/SKILL.md`) and declined to apply it to the Inbound review UI — skill is aimed at marketing surfaces (maximalist, distinctive) and would hurt the review-tool UX (density, legibility, fatigue resistance). Noted as potential fit for future marketing surfaces or export-celebration states. |
