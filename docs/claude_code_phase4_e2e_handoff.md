# Phase 4 — End-to-End Validation Handoff

**Status as of 2026-04-19:** all code for the per-image inbound flow is built, type-checks, and is verified at the unit level. This document is the test plan for Sergey to drive the workflow himself with real photos.

> Paste this whole file into the next chat as the opening message.

---

## What was built (the pivot, in one paragraph)

Mid-Phase-3 we pivoted from "one job = one item, multiple photos" to **"one image = one product listing."** The original DB-backed `/jobs` pipeline (47/47 tests passing) is **left untouched but dormant** in the UI. A parallel filesystem-backed pipeline now powers the active UX:

```
input_images/  →  extract.bat  →  inbound/*.json  →  dev.bat  →  #/inbound  →  exports/*.csv
   (drop)        (Gemini × N)      (one per image)    (review)    (per-card)    (bulk)
```

Both pipelines share the same Gemini prompt (`backend/src/service_photo/prompts/listing_extraction_v1.md`) and the same CSV column contract (`contracts/csv_export_schema.md`).

---

## Files to know

| File | Why it matters |
|---|---|
| `scripts/run_gemini_extraction.py` | The CLI. Reads `.env` from repo root, walks `input_images/`, makes one Gemini call per image, writes `inbound/extraction_<UTC>__<image-stem>.json`. Self-contained (no python-dotenv dep). |
| `backend/src/service_photo/integrations/real_gemini.py` | Multimodal client. Lazy SDK import, JSON code-fence stripping, default model `gemini-2.5-flash`, overridable via `GEMINI_MODEL`. |
| `backend/src/service_photo/api/inbound_routes.py` | Mounts at `/api/v1/inbound`. Three endpoints: list, serve image, bulk export to CSV. |
| `backend/src/service_photo/main.py` | Includes `inbound_router` alongside the dormant `router`. |
| `frontend/src/screens/InboundScreen.tsx` | The active UI. ~430 lines. Per-card edit/approve, localStorage persistence (key `service-photo:inbound-review-state-v1`), bulk-export bar at the bottom. |
| `frontend/src/api/inbound.ts` | Typed client. Spec fields are `unknown` because Gemini occasionally returns `"33MP"` instead of `33`. |
| `dev.bat`, `extract.bat` | One-click launchers at repo root. |
| `.env` | Repo-root, gitignored. Must contain `GEMINI_API_KEY` and (optionally) `GEMINI_MODEL`. |

---

## The Phase 4 test plan

### 1. Smoke test with the existing photos

Goal: confirm what's already in `inbound/` renders and exports correctly, no new Gemini calls needed.

- [ ] Double-click `dev.bat`. Two cmd windows open (backend on :8000, frontend on :5173). Browser opens to `http://localhost:5173/#/inbound`.
- [ ] Confirm the screen shows one card per JSON in `inbound/` (currently 5).
- [ ] For each card, verify: image renders on the left, all four sections (Overview / Description / Specifications / Accessories) populate on the right, no red API-error badges. Amber schema-mismatch badges are OK to note but not blockers.
- [ ] Click "Edit" on one card. Change a field. Click "Save". Reload the page. Confirm the edit survived (it lives in localStorage, not on disk).
- [ ] Click "Approve" on 2 cards. Confirm green border + tint.
- [ ] Click "Approve All & Export to CSV" at the bottom. Confirm: remaining cards flip to approved, success banner shows, file appears at `exports/listings_<UTC>.csv`.
- [ ] Open the CSV in a text editor (not Excel — Excel can mangle line-flattened cells). Verify: 32 columns starting with `job_number`, ending with `exported_at`. Long-form fields (description, condition_notes, etc.) should have no embedded newlines. Empty fields are blank, not `null`.

### 2. Real-world test

- [ ] Clear `inbound/` and `exports/`.
- [ ] Drop 3–10 fresh photos into `input_images/` (mix of single-camera shots and bundles with accessories).
- [ ] Double-click `extract.bat`. Watch the console. ~13s per image is normal. If any image errors, the error lands in the JSON's `meta.api_error` field — UI shows a red badge but still renders the empty card.
- [ ] Run `dev.bat` (or refresh if already running) and walk through every card.
- [ ] Track these as you go (open a notepad):
  - Per card: how many fields needed editing? Which ones?
  - Were any fields wrong but believable (would have shipped if you weren't paying attention)?
  - Any totally missed fields (Gemini returned null but the answer is visible in the photo)?
  - Was anything hallucinated (Gemini invented detail not in the image)?
- [ ] Bulk approve & export. Verify the CSV.

### 3. Decision points after the walkthrough

After Phase 4, choose between:

- **Productize the inbound flow** → delete the dormant `/jobs` pipeline, formalize the localStorage state into a real backend, add upload-via-UI instead of folder-drop, etc.
- **Iterate the prompt** → if correction patterns are concentrated in 2–3 fields, edit `backend/src/service_photo/prompts/listing_extraction_v1.md` and re-run.
- **Revisit the architecture** → if the per-image model is too lossy (e.g. accessories in a separate photo from the camera get split into different listings), reconsider batching.

---

## Things that might trip you up

- **The `.env` file lives at repo root**, not inside `backend/`. The CLI script and the backend both look there.
- **Gemini API key was rotated mid-session.** The current key in `.env` is the rotated one. If you re-rotate, both `extract.bat` and `dev.bat` (backend) read fresh on each launch.
- **`google-generativeai==0.5.4`** is the pinned SDK. It still works for `gemini-2.5-flash` despite Google's newer SDK existing.
- **localStorage state is per-browser, per-origin.** Clearing site data in DevTools wipes all approvals and edits. There's no cross-device sync.
- **The export endpoint reads what the UI sends, not what's on disk.** So edits made in the UI flow into the CSV via the `POST /api/v1/inbound/export` request body. If you skip the UI and call the endpoint directly, you'd need to construct the items array yourself.
- **Path resolution in `inbound_routes.py`** uses `parents[4]` to find repo root. If you move that file, fix the count.
- **Old screens still mount.** `#/`, `#/jobs`, `#/jobs/new`, `#/jobs/:id`, `#/jobs/:id/review` all still work and hit the dormant DB pipeline. They're not in the Phase 4 scope — ignore them.

---

## How to start the next chat

Open the chat in this same project directory and paste:

> Read `docs/claude_code_phase4_e2e_handoff.md` and help me run through the test plan. I'll drop fresh photos and report what I see.

That's it. The CLAUDE.md at repo root will load automatically and orient Claude on the rest.
