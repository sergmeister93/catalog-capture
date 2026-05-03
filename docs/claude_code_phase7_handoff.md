# Phase 7 Handoff — Service Photo POC / Catalog Capture

_Last updated: 2026-04-19, at the close of Phase 6G._

This document covers **(a)** the small open nits carried out of Phase 6, and **(b)** the candidate directions for Phase 7. Nothing here is committed work — confirm direction with Sergey before starting any item.

---

## Where we are

- **Phase 6 is closed.** The product is branded **Catalog Capture**, the nav reads **Upload / Review / Batch History**, the design system in [`frontend/src/index.css`](../frontend/src/index.css) is the canonical token source, and all user-facing copy has been scrubbed of vendor names, system keys, bracketed flags, and raw file paths (see the humanizer helpers at the bottom of [`frontend/src/screens/InboundScreen.tsx`](../frontend/src/screens/InboundScreen.tsx)).
- **Backend**: 47/47 pytest passing. Dormant `/jobs` DB-backed pipeline still mounted; active `/inbound` filesystem pipeline powers the UX.
- **Pricing**: single-pass — Gemini returns extraction + grounded pricing in one call via the `google-genai` SDK with `types.Tool(google_search=types.GoogleSearch())`. Re-running analysis is the only way to refresh pricing.
- **Frontend typecheck**: clean.
- **Reference docs**: [`CLAUDE.md`](../CLAUDE.md), [`docs/00_project_documentation.md`](00_project_documentation.md), [`docs/progress.md`](progress.md), [`docs/03_ui_design.md`](03_ui_design.md) (revision 2.0 appended).

---

## Small open nits (carryover from Phase 6G)

These are **low-priority**. Bundle any subset into a polish PR if you have a quiet session; none block Phase 7 work.

1. **Screen-local inline styles shadow the new globals.** `PrepScreen.tsx` still has `batchNameInputStyle` and `fieldLabelStyle` constants; `InboundScreen.tsx` has `inputStyle`, `textareaStyle`, `readonlyStyle`, `sectionHeaderStyle`, `fieldLabelStyle`, `smallBtnStyle`, `cardHeaderStyle`, `cardBodyStyle`, `imageColumnStyle`, `imageStyle`, `contentColumnStyle`, `approvedBadgeStyle`, `schemaWarnBadgeStyle`, `apiErrorBadgeStyle`, `warningsStyle`, `sourcesTableStyle`, `sourceRowStyle`, `pricingNotesStyle`, `stickyFooterStyle`. Many of these now duplicate (and in places subtly override) what's in `index.css`. A follow-up refactor could:
   - replace the local input/textarea styles with the global element selectors (they already match the global `40px` / `radius-md` look),
   - swap the per-screen sticky footer for the global `.action-bar` class,
   - move the `approvedBadgeStyle` family to `.status-pill--success` / `--warning` / `--error`.

   Not a correctness issue — purely consolidation.

2. **`stickyFooterStyle` still paints onto `--brand-dark`.** The Review-screen footer is a dark bar with white text. The rest of the v2 system uses the translucent `.action-bar` pattern (white-on-blur). Consider whether the dark footer should stay (it's a deliberate "you are about to commit" signal) or migrate to `.action-bar` for consistency with the rest of the chrome. Check with Sergey.

3. **Fonts load from Google Fonts CDN.** `index.css` `@import`s Inter + Manrope from `fonts.googleapis.com`. If Catalog Capture is ever deployed into an enterprise air-gapped environment, self-host the woff2 files and drop the `@import`. The system-font stack fallback keeps things working offline, but Manrope degrades to the system default, which undoes the wordmark polish.

4. **Export semantics vs. button label.** The footer CTA is now `Export Approved Items`, but the underlying `handleApproveAllAndExport` bulk-approves everything first, then exports every item. If a reviewer leaves a card intentionally unapproved, it still ships in the CSV. Two possible fixes for Phase 7:
   - **Rename the button** to `Approve All & Export` (match behavior to label) — undoes part of the copy polish but is honest.
   - **Tighten the behavior** so the button only exports cards with `approved === true` at click time. Any unapproved card is skipped (or blocks export with an inline warning).

   Sergey's stated intent during Phase 5 was "pricing errors do not block export"; the analogous rule for approvals isn't written down yet. Ask him.

5. **`docs/03_ui_design.md` revision 2.0** is an **appendix** to the original spec, not a rewrite. If v2 becomes the long-term baseline, consider rewriting the whole file so the "Revision 2.0" section becomes the primary content and the v1 spec moves to a historical footer.

6. **`inbound/` directory / `#/inbound` route** are still the internal names. Phase 6F deliberately only renamed display strings. If at any point Sergey wants internal parity ("the route should match the nav"), plan it as a separate pass — touching the backend route, frontend module (`api/inbound.ts`), hash router, and all call sites is a non-trivial coordinated change.

---

## Phase 7 candidate directions

Listed rough-cheapest first. None have been committed; list exists so Sergey can pick the next push.

### A. Promote the in-memory `_jobs` registry to SQLite

**Why**: the extraction job state (`_jobs` dict in [`backend/src/service_photo/api/inbound_routes.py`](../backend/src/service_photo/api/inbound_routes.py)) lives in RAM. A backend restart drops any in-flight job state — completed JSONs on disk remain authoritative, but progress reporting vanishes and Upload→Review handoffs mid-flight break.

**Scope**:
- New SQLite DB (single file, gitignored) with one `extraction_jobs` table mirroring the in-memory shape (job_id PK, status, total, completed, succeeded, failed, current_image, started_at_utc, finished_at_utc, model, error, batch_name, results JSON).
- Replace the dict + lock with a thin SQLite repo. No ORM needed — stdlib `sqlite3` is enough for a single-writer POC.
- Keep the response shapes identical so the frontend needs no changes.

**Effort**: small (1 session). No risk to the pricing / extraction path itself.

### B. Export gate: per-card approved-only

See nit #4 above. If Sergey confirms the intent: modify `handleApproveAllAndExport` so the payload only includes `approved === true` cards, block the click when `approvedCount === 0`, and update the disabled helper text.

**Effort**: tiny (afternoon).

### C. Confidence scoring per field

**Why**: reviewers currently have only the `Pricing Notes` callout and the `AI Warnings` list to flag uncertain data. Per-field confidence (e.g. from the schema validator + Gemini's own hedging) would let the UI visually flag which spec fields need the closest look.

**Scope**:
- Extend `contracts/gemini_response_schema.json` with optional per-field `_confidence` siblings (or a flat `confidences: { "overview.product_name": 0.94, ... }` dict — ask Sergey which reads cleaner).
- Prompt Gemini to emit scores alongside values (or derive them from visible-evidence heuristics).
- Frontend: small `<ConfidenceDot>` next to low-confidence field labels; filter/sort in the list view.

**Effort**: medium (~2 sessions). Prompt engineering is the unknown.

### D. Multi-reviewer approval queue

**Why**: "one reviewer approves each card, then exports" is single-user today. A real ops team would want (1) multiple reviewers, (2) assignment / claim semantics, (3) an audit trail.

**Scope**: substantial — needs real user auth, a DB (Postgres, not SQLite), RBAC, and the old `/jobs` pipeline's status-history model dusted off and repurposed. Most of the machinery already exists in the dormant DB pipeline; this could be the project that un-dormants it.

**Effort**: large (multi-session). Start with an ADR covering which pieces of the old `/jobs` pipeline get resurrected vs. rebuilt.

### E. Marketplace posting integrations

**Why**: CSV export is a hand-off to whatever marketplace the user lists on. Direct posting (eBay Sell API, Shopify Admin API, Reverb) would close the loop.

**Scope**: per-marketplace auth, per-marketplace field mapping, image upload, draft-vs-publish states, idempotency. Real project. Needs its own scoping document before any code.

**Effort**: very large. Don't start until Sergey confirms this is the direction.

### F. Self-host the fonts

See nit #3. One-session cleanup once Sergey decides self-hosting is in scope.

### G. Self-host migration — move Catalog Capture to the home Ubuntu mini-PC

**Why**: today the app only runs on Sergey's Windows PC via `dev.bat`. His wife needs access from her personal Mac. Goal is a single-user web app behind email auth, hosted on the GMKtec mini-PC he already owns.

**Status**: full tech spec lives in [`docs/05_self_host_migration_spec.md`](05_self_host_migration_spec.md) (drafted 2026-05-03). Includes target architecture, deployment topology, auth model (Cloudflare Tunnel + Cloudflare Access), secrets handling, backup plan, and a 7-phase migration checklist (M0 → M7). Read that document before doing any implementation work — this entry is just a pointer.

**Decisions already locked in** (do not re-debate without Sergey):
- Self-hosting on the GMKtec, not a VPS (chose learning value over ops simplicity).
- Cloudflare Tunnel for inbound (no port forwarding, no public IP).
- Cloudflare Access for auth (no app-side auth code).
- Ubuntu Server 24.04 LTS, Docker + Compose, two app containers (backend uvicorn + frontend nginx) plus `cloudflared`.
- Single user; multi-user is Phase 7D, separate.

**Effort**: medium-to-large but mostly ops, not code. ~1 weekend if Sergey already has the domain bought. The actual code changes are small (Dockerfiles, nginx.conf, compose, Makefile, one likely refactor of `core/config.py`'s env-file resolver).

**Open questions** are catalogued in §10 of the spec — the most important ones for Sergey to answer before implementation: domain name, backup destination, and whether to bundle Phase 7A (SQLite for `_jobs`) into the migration (recommendation: don't).

**Interaction with other Phase 7 directions**:
- Phase 7A (SQLite for `_jobs`) is **complementary** — could land before or after the migration, doesn't change the deployment topology. The spec recommends shipping the migration first.
- Phase 7D (multi-reviewer queue) is **superseded** by this for auth — once Cloudflare Access is in place, Phase 7D can either keep using CFA emails as identity or layer real app-side auth on top.
- Phases 7B / 7C / 7E / 7F are **independent** and can ship before or after.

---

## How to spin up (unchanged from Phase 6)

```bat
dev.bat
```

- launches backend (`uvicorn service_photo.main:app --reload` from `backend/`) and frontend (`npm run dev` from `frontend/`) in two cmd windows,
- opens the default browser to `http://localhost:5173/#/`.

**Before running**: check for stacked uvicorn/Vite processes from a prior relaunch (`tasklist | grep python` / `grep node`) and kill duplicates with `taskkill //F //PID <pid>`. `dev.bat` does not clean up prior processes; stale listeners will load-balance requests and make code edits look like they "don't apply." See gotcha #7 in [`CLAUDE.md`](../CLAUDE.md).

**Backend env**: `.env` at repo root, containing `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-2.5-flash`, `DATABASE_URL=...`, `USE_MOCK_GEMINI=false`. `core/config.py` resolves this via absolute path (`Path(__file__).resolve().parents[4] / ".env"`) — do not regress to a relative path.

**Tests**:
```
cd backend
pytest
```
Expect 47/47 passing. Frontend typecheck: `cd frontend && npm run typecheck`.

---

## Rules of engagement for Phase 7

These are standing instructions carried from prior phases; re-stated here so the next session doesn't have to re-discover them.

1. **Confirm before starting.** Every candidate above needs Sergey's go-ahead. Don't pick from the menu unilaterally.
2. **Respect the display-name vs. internal-name split.** `Catalog Capture` / `Upload` / `Review` / `Batch History` are display strings. `inbound/`, `#/inbound`, `api/inbound.ts`, `/api/v1/inbound/*` are internal. Don't conflate the two in a single PR.
3. **No raw vendor/system strings in new UI.** Use the humanizers in `InboundScreen.tsx`, or add new helpers for new categories. The rule in [`docs/03_ui_design.md`](03_ui_design.md) revision 2.0 is load-bearing.
4. **Design tokens live in `index.css`.** Don't hardcode colors, radii, shadows, or type sizes in component styles. If you find yourself wanting a value that isn't a token, add the token.
5. **Don't delete the dormant `/jobs` pipeline.** Even if it looks unused — Phase 7D may revive it. It still passes all 47 tests; keep it green.
6. **POC rules still apply.** No new dependencies without asking. Comment heavily. Simple over clever. Docstring at top of every new script / module.
