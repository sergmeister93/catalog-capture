# Open Issues, Risks, and Unknowns

Separated into three tiers: **Confirmed** (directly evidenced), **Probable** (reasoned inference), and **Unknowns** (questions that must be answered before productionization).

---

## Confirmed issues

### C1 · In-memory job tracker is volatile
The `_jobs` dict in `api/inbound_routes.py` is module-level state. Any backend restart drops in-flight extraction state. Completed JSON artifacts on disk survive, but a reviewer polling during a restart sees an orphaned "Queued…" banner.
- **Impact:** Medium. Reviewer must manually refresh and re-check `inbound/` contents.
- **Source:** `CLAUDE.md` Phase 7 candidates; `inbound_routes.py` code.
- **Fix path:** Promote `_jobs` to SQLite. Identified as top Phase 7 candidate.

### C2 · No test coverage for the active `/inbound` pipeline
The 47/47 passing test suite targets the **dormant** `/jobs` pipeline. The live user-facing workflow has zero automated coverage.
- **Impact:** High. Any change to `inbound_routes.py`, `inbound_extraction.py`, or `export_service.py` ships without regression safety.
- **Source:** Direct inspection of `backend/tests/integration/` — all files mirror `/jobs/*` routes.
- **Fix path:** Mirror the existing test patterns onto `/inbound`.

### C3 · README is stuck at Phase 1
`README.md` declares "Phase 1" and "Backend and frontend scaffolding are in place but not yet implemented." The project has completed Phases 2–6.
- **Impact:** Medium. Actively misleads inheriting engineers on first read.
- **Source:** `README.md` lines 1–20.
- **Fix path:** Rewrite README to point at `CLAUDE.md` as the current orientation doc.

### C4 · `dev.bat` stacks duplicate processes
The launcher does not kill prior uvicorn or Vite processes before starting new ones. Repeat launches load-balance between stale and fresh listeners on ports 8000 and 5173.
- **Impact:** Medium. Symptom: "my edit didn't take effect" — a debugging trap.
- **Source:** `CLAUDE.md` gotcha #7.
- **Fix path:** `taskkill /F /FI "WINDOWTITLE eq Backend*"` before launch.

### C5 · `docs/03_ui_design.md` is stale
Phase 6G replaced the original design tokens wholesale. The doc still reflects pre-6G values.
- **Impact:** Low. Misleads UI contributors.
- **Source:** `CLAUDE.md` gotcha #10.
- **Fix path:** Rewrite to cite `frontend/src/index.css` as source of truth.

### C6 · Single-user assumption in the active pipeline
`input_images/`, `inbound/`, and `exports/` are shared folders. Concurrent reviewers will race on writes. The extraction route purges `inbound/` before each run, which would silently destroy a colleague's in-flight work.
- **Impact:** High if multi-user is ever a requirement.
- **Source:** `api/inbound_routes.py::POST /inbound/extract` purge logic.
- **Fix path:** Per-user workspaces or database-backed state.

### C7 · No authentication on any endpoint
No auth layer, no session, no tokens. Any reachable client can trigger extraction or export.
- **Impact:** High outside of localhost-only deployments.
- **Source:** `main.py`, `api/*.py` — no auth dependencies.
- **Fix path:** Even a single shared credential + HTTP basic auth closes the biggest gap.

### C8 · Bulk-export also bulk-approves
The "Export Approved Items" button approves any not-yet-approved cards before exporting — it does not filter to approved-only. A reviewer who leaves cards un-approved expecting them to be excluded will be surprised.
- **Impact:** Medium. Can contaminate the CSV with unreviewed items.
- **Source:** `CLAUDE.md` gotcha #13.
- **Fix path:** Add an "export approved only" toggle or change the default.

### C9 · Fonts loaded from Google Fonts CDN
`index.css` `@import`s Inter and Manrope from `fonts.googleapis.com`. Fails silently offline / in air-gapped environments.
- **Impact:** Low unless deploying air-gapped.
- **Source:** `CLAUDE.md` gotcha #12.
- **Fix path:** Self-host the woff2 files.

### C10 · Two large files concentrate risk
- `frontend/src/screens/InboundScreen.tsx` — 1,301 LOC, three screens in one file.
- `backend/src/service_photo/api/inbound_routes.py` — 943 LOC, routing + orchestration + job tracking.
- **Impact:** Medium. Slows feature work and complicates testing.
- **Fix path:** Decompose before the next major feature.

---

## Probable issues

### P1 · Pricing accuracy is unaudited
The entire pricing block comes from Gemini's grounded Google Search. There is no independent verification, no confidence score persisted alongside each price, and no sanity check against a historical distribution.
- **Source:** `integrations/real_gemini.py`, `contracts/gemini_response_schema.json`.
- **Mitigation:** Surface `uncertainty_tags[]` and `sources[]` in the UI (partially done). Add a reviewer warning when the spread between comps is large.

### P2 · No retry / backoff for Gemini failures
If a single image's Gemini call fails, the extraction continues but that image is lost from the batch. No retry, no exponential backoff, no explicit dead-letter.
- **Source:** `services/inbound_extraction.py`.
- **Mitigation:** Wrap the call in a retry with jitter for 429/5xx.

### P3 · No rate limiting on `/inbound/extract`
A reviewer or misbehaving client can trigger unlimited extractions, each of which spends Gemini quota.
- **Source:** `api/inbound_routes.py`.
- **Mitigation:** Per-IP or global token bucket on the route.

### P4 · Logging is `print`-based
No structured logger, no log level discipline, no correlation IDs. Debugging a live incident would be painful.
- **Source:** Inspection of `inbound_extraction.py` and `real_gemini.py`.
- **Mitigation:** Standard `logging` with JSON formatter; emit one event per image start/complete/error with `job_id` + `image`.

### P5 · Dormant pipeline may have regressed after Phase 5 dependency bumps
The 47/47 passing baseline predates the pydantic 2.7.1 → ≥2.11 upgrade and the `google-generativeai` → `google-genai` SDK migration. The dormant `submit_service.py` still references the AI integration abstraction; the test run was not re-verified after the upgrade.
- **Source:** `backend/pyproject.toml` history (documented in `CLAUDE.md`), no re-run evidence in `progress.md`.
- **Mitigation:** Re-run `pytest` and re-confirm 47/47 before attempting Phase 7 work that touches the DB pipeline.

### P6 · CSV schema may not match a real marketplace
The CSV is engineered against the in-repo spec, not against a verified target marketplace's import format. If a target system exists, it is not referenced in the code.
- **Source:** `contracts/csv_export_schema.md` — self-referential.
- **Mitigation:** Confirm the target and adjust columns before the first real import.

### P7 · Content Security Policy, CORS, and API origin assumptions unstated
`main.py` likely has a permissive CORS config for local dev. For any non-local deployment this would need to be tightened.
- **Source:** Inferred from typical FastAPI POC setup; `main.py` was not deeply inspected in this audit.
- **Mitigation:** Audit CORS config before any hosted deployment.

---

## Unknowns requiring validation

### U1 · Is multi-reviewer access a near-term requirement?
Answer determines whether Phase 7's "promote `_jobs` to SQLite" is enough, or whether a full Postgres-backed queue is required.

### U2 · What is the target marketplace, and does the CSV actually match its import spec?
If unknown, the export format is a theoretical artifact until confirmed.

### U3 · What is the expected extraction volume and Gemini cost envelope?
Unknown volume → unknown whether rate limiting, caching, or batching is urgent.

### U4 · What is the retention policy for `input_images/`, `inbound/`, and `exports/`?
Currently unbounded local folders. At some volume this becomes a housekeeping problem.

### U5 · Who operates this? Where does it run in production?
Currently Windows-first with `dev.bat`. A cloud or Linux target would require a different deployment model (Dockerfile, process supervision, TLS, reverse proxy).

### U6 · Is there a formal SLA for Gemini availability or response time?
Affects whether asynchronous queue-and-retry semantics become mandatory.

### U7 · Are reviewer edits ever audited, or is the CSV the only record?
No audit table in the active pipeline. If edits must be traceable, this is a gap.

### U8 · Will the dormant `/jobs/*` pipeline ever be revived, or should it be deleted?
Keeping dead-but-not-deleted code adds maintenance drag. A decision is owed here before Phase 7 ships.

---

## Risk summary matrix

| Risk | Likelihood | Impact | Priority |
|---|---|---|---|
| C1 · Volatile job tracker | Certain on restart | Medium | **High** |
| C2 · No `/inbound` test coverage | Certain | High | **High** |
| C6 · Single-user assumption | Certain if multi-user | High | **High** |
| C7 · No auth | Certain off-localhost | High | **High** |
| P3 · No rate limiting | Medium | High ($) | **High** |
| C8 · Export bulk-approves | Certain on misunderstanding | Medium | Medium |
| C10 · God components | Certain over time | Medium | Medium |
| P1 · Pricing unaudited | Medium | Medium | Medium |
| P2 · No Gemini retry | Occasional | Medium | Medium |
| P4 · `print`-based logging | Certain on incident | Medium | Medium |
| C4 · dev.bat stale processes | Frequent in dev | Low | Low |
| C3 · README stale | Certain | Low | Low |
| C5 · 03_ui_design stale | Certain | Low | Low |
| C9 · CDN fonts | Only air-gapped | Low | Low |
