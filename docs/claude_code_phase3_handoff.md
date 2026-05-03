# Phase 3 Handoff — Next Chat Starter

Paste the content below as the opening message in a new Claude Code chat.

---

## Starter Prompt

Read these files to ground yourself:

- `CLAUDE.md` (project root) — current phase state and verified-stack notes
- `docs/progress.md` — task tracker; find the "Phase 3" section for exact status
- `docs/03_ui_design.md` — design tokens / brand spec
- `contracts/openapi_service_photo_poc.yaml` — backend API contract
- `contracts/backend_workflow_spec.md` — backend behavior for existing endpoints
- `frontend/src/screens/PrepScreen.tsx` — current first screen
- `frontend/src/stubs/inputImages.ts` — the stub to replace
- `backend/src/service_photo/api/routes.py` — existing routes to extend

## Where We Left Off

**Stack is working end-to-end against mocks.** The frontend (Vite + React + TS in `frontend/`) boots on `http://localhost:5173` and proxies `/api/*` to the FastAPI backend on `http://localhost:8000` (routes mount under `/api/v1`). 47/47 backend tests still passing.

**What the user sees today:**
1. **Prep screen at `#/`** — left rail shows images from a stub (5 hardcoded files mirrored from repo-root `input_images/` into `frontend/public/input_images/`), right panel has "Batch Name" input + big red "Approve → Send to Gemini" button. Button is UI-only: clicking it shows a success banner without any backend call.
2. **Recent Jobs at `#/jobs`** — list of jobs the user created earlier (localStorage-backed since there's no `GET /jobs` list endpoint).
3. **Job Detail + Review screen** — side-by-side draft-vs-review editor with per-section save. Works end-to-end. **Note: Sergey said this review editor is "not what I have in mind"** — the screen works and is not broken, but its UX direction is not confirmed. **Do not build more on the review screen without checking with him first.**

## The Single Next Task

Wire the prep screen's "Approve" button to a real backend. Requires building two new endpoints:

### Backend work

1. **`GET /api/v1/input-images`** — list files currently in `STORAGE_BASE_PATH/input_images/` (or a similar configured folder). Return shape should match the stub in `frontend/src/stubs/inputImages.ts` (array of `{file_name, file_size_bytes, file_type, file_path}`). Only include image MIME types.

2. **`POST /api/v1/batches`** — body: `{batch_name: string, file_names: string[]}`. Behavior:
   - Create a listing job (set `notes = batch_name` for now, or add a `batch_name` column if you prefer — discuss with Sergey first)
   - For each `file_name`, verify it exists under `input_images/`, then register it via the same logic as `register_image` (copy/move to per-job storage if appropriate — check `STORAGE_BASE_PATH` conventions in `core/config.py`)
   - Call `submit_service.submit_job` to trigger Gemini (mock for now)
   - Return the `ListingJob` (HTTP 201)
   - Rollback the whole thing if any image registration fails

Add tests: unit for the folder scanner, integration for `POST /batches` happy path + missing-file failure.

### Frontend work

1. Replace the call in `frontend/src/stubs/inputImages.ts` with a real `fetch("/api/v1/input-images")`. Keep the file as the one swap-point.
2. In `PrepScreen.tsx`, replace the `TODO(backend)` at `handleApprove` with a real `POST /api/v1/batches` call. On success, navigate to the new job's detail screen (`#/jobs/:id`).

## Important Behaviors (Do Not Break)

- **Terminology:** Sergey uses "Approve" both for "send this batch to Gemini" (prep screen) AND for the formal export gate (downstream). Don't rename either. The UI disambiguates by position — prep says "Approve → Send to Gemini"; the final gate should say "Approve for Export" or similar when built.
- **One batch = one listing = one item.** All photos in a batch depict the same item and its accessories. The backend's existing "one job = one item" model matches — don't introduce a new multi-item batch concept.
- **UI-first workflow.** Sergey prefers shaping the UX before building backend to match. Show mockups / describe layouts before writing endpoints.
- **Don't ask more than one clarifying question at a time** unless necessary (per global CLAUDE.md).
- **Logo lives at `frontend/public/logo.png`** and is wired into the navbar already.

## Verified-Stack Reproducer

From `backend/` (Python 3.12 + Postgres 15 via Docker):
```
docker start service-photo-pg  # or run once: see CLAUDE.md Phase 2 section
set DATABASE_URL=postgresql://postgres:postgres@localhost:5432/service_photo_dev
set TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/service_photo_test
.venv\Scripts\activate
uvicorn service_photo.main:app --reload
```

From `frontend/`:
```
npm run dev       # http://localhost:5173
npm run typecheck
```

## Known Open Questions (surface these with Sergey before building)

1. Review editor UX — he flagged the current implementation as off-direction. Ask what he wants to see before building M5.
2. Whether `batch_name` should be a proper column on `listing_jobs` or overloaded into `notes`.
3. Post-Approve navigation — after a batch is sent, does the user land on the job detail screen, the review screen, or back on the prep screen with a success toast?

## Code-Style Reminders

- Python, comment heavily, simple over clever, no unnecessary deps (per global CLAUDE.md).
- Frontend is TS with JSDoc-style comments — match that style.
- No backwards-compat shims or removed-code comments.
