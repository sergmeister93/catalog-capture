# Hosted Migration — Current Status & Next-Session Handoff

_Last updated: 2026-05-03 (evening). Author: Claude (Opus 4.7), pair-programming with Sergey._

This file is the **single source of truth** for where the hosted-deployment work stands. Read this first when picking the project back up — it supersedes the planning-phase content in `01_self_host_migration_spec.md` (which described a home Ubuntu mini-PC + Cloudflare Tunnel target; the actual deployment pivoted to **Railway + Cloudflare Access** for lower friction).

---

## TL;DR

- ✅ **Railway deployment is LIVE.** The container is running on the `catalog-capture` service in Railway project `accurate-liberation`, region `us-west2`, mounted volume at `/data`, env vars set (`GEMINI_API_KEY`, `USE_MOCK_GEMINI=false`, `GEMINI_MODEL=gemini-2.5-flash`). End-to-end smoke test passed against real Gemini: upload → extract → review → export → CSV downloads to browser.
- ✅ **CSV download works in the browser.** `GET /api/v1/inbound/exports/{filename}` (PR #1, merged) lets the user pull exported CSVs into Chrome's Downloads folder. The CSV also persists on the volume.
- ✅ **"Clear Data" button shipped.** `DELETE /api/v1/inbound/data` + button on the Upload screen (PR #2, merged) gives the user a single-click full reset of `input_images/`, `inbound/`, `exports/`, plus the two browser-side localStorage keys. Endpoint has no server-side auth — relies on Cloudflare Access.
- ❌ **Cloudflare Access is not wired up yet.** The Railway URL is currently public — anyone who finds it can use the app and burn Gemini credits. **This is the next concrete step.** Blocked on a domain decision (see "What's left" below).

---

## What shipped during the migration push (chronological)

### Round 1 — containerization (committed before the Railway deploy)

| Path | Purpose |
|---|---|
| `Dockerfile` | Multi-stage build: `node:20-alpine` builds the Vite frontend → `python:3.12-slim` installs the backend, copies the `dist/` next to it, runs uvicorn `--workers 1` under `tini`. Defaults `APP_DATA_DIR=/data`, `FRONTEND_DIST_DIR=/app/frontend_dist`. |
| `.dockerignore` | Excludes `node_modules/`, `_local_data/`, `input_images/`, `inbound/`, `exports/`, `storage/`, `test_data/`, `.env`, etc. |
| `backend/src/service_photo/core/config.py` | Added `APP_DATA_DIR` setting (default = repo root for local dev, `/data` in container). Exposes `APP_DATA_PATH`. |
| `backend/src/service_photo/api/inbound_routes.py` | `INBOUND_DIR` / `INPUT_IMAGES_DIR` / `EXPORTS_DIR` resolve under `APP_DATA_PATH`. |
| `backend/src/service_photo/main.py` | Optional SPA-serving: if `FRONTEND_DIST_DIR` exists, mount `/assets` and a SPA catch-all so a single uvicorn process serves both the React app and `/api/*`. Eliminates CORS. |
| `backend/src/service_photo/services/inbound_extraction.py` | `PROMPT_PATH` resolves package-relative; `SCHEMA_PATH` walks parents to find `contracts/gemini_response_schema.json`. |
| `backend/pyproject.toml` | Added `[tool.setuptools.package-data]` so `prompts/*.md` ships inside the installed wheel. |
| `README.md` | "Hosted Railway Deployment" section. |
| `.gitignore` | Added `_local_data/` and broad media excludes. |

### Round 2 — Railway shake-down (new commits made *during* the deploy session)

Three PRs (one direct push, two PRs):

1. **`94198e9` — Fix unanchored gitignore that excluded service_photo/exports source package** (direct push to `main`).
   `.gitignore` had `exports/` as an unanchored pattern, which matched both the user-data `exports/` at repo root AND the source-code `backend/src/service_photo/exports/`. The source package was silently never staged. Local Docker builds worked because they copied from disk; Railway's clean checkout crashed at import with `ModuleNotFoundError: No module named 'service_photo.exports'`. Fix: anchored runtime-storage patterns to repo root (`/exports/`, `/inbound/`, `/input_images/`, `/storage/`, `/_local_data/`) and `git add`-ed the two missing files.

2. **PR #1 (merged) — Add CSV download endpoint for hosted deployments.**
   `GET /api/v1/inbound/exports/{filename}` streams the CSV with `Content-Disposition: attachment`. Path-traversal defense mirrors the existing `/inbound/images/{filename}` pattern. Frontend triggers the download via a hidden `<a download>` click after the export POST returns. CSVs still persist on the volume.

3. **PR #2 (merged) — Add Clear Data button on Upload screen for hosted volume reset.**
   `DELETE /api/v1/inbound/data` purges every direct child file in `input_images/`, `inbound/`, `exports/` (skips subdirs defensively, keeps the dirs themselves). Returns counts. Upload screen gets a "Clear Data" button next to "Check for Images," gated by `window.confirm`. Frontend also wipes the two localStorage keys (`service-photo:active-extraction-v1`, `service-photo:inbound-review-state-v2`). **No server-side auth on the endpoint — relies on the Cloudflare Access layer planned next.**

### Bugs discovered & fixed during the Railway shake-down (do not reintroduce)

1. **Dormant `/jobs` pipeline blocks startup if `contracts/` is missing.** `services/submit_service.py` walks parent dirs at import time. The Dockerfile `COPY contracts /contracts` so the walk-up succeeds.
2. **Prompts not in the installed package.** Fixed via `package-data` in `pyproject.toml`.
3. **Inbound extraction used a repo-root-relative prompt path.** Replaced with package-relative resolution.
4. **Unanchored `.gitignore` patterns shadowed source dirs.** See round 2, item 1 above. **Generalizable lesson:** any folder name in `.gitignore` without a leading `/` matches *anywhere* in the tree. Always anchor runtime-storage patterns to repo root.

---

## Current Railway state (verified live)

- **Project:** `accurate-liberation` (auto-generated nickname; rename in project settings if desired)
- **Service:** `catalog-capture`
- **Region:** `us-west2`
- **Volume:** `catalog-capture-volume` mounted at `/data`, 1 GB allocated
- **Replicas:** 1 (do not raise — `_jobs` is in-process)
- **Auto-deploy:** main branch, on every push
- **Public URL:** generated via Settings → Networking → Generate Domain (port 8080). The exact URL is in Railway; not pinned in this doc since it changes if regenerated.
- **Env vars set:** `GEMINI_API_KEY`, `USE_MOCK_GEMINI=false`, `GEMINI_MODEL=gemini-2.5-flash`. `PORT` injected by Railway. All others use Dockerfile defaults.

---

## What's left

### Step A: Smoke-test the Clear Data button on the live URL (~2 minutes)

PR #2 is merged; Railway will have redeployed by the start of the next session. Confirm it works end-to-end:
1. Upload a test photo, run extraction, export.
2. Click "Clear Data" → cancel → verify nothing changes.
3. Click "Clear Data" → accept → verify alert shows accurate counts and the thumbnail list empties.
4. Refresh the page → verify state stayed cleared (volume actually purged).
5. Upload again → verify uploads still work after a clear (directories were preserved, only contents removed).

### Step B: Cloudflare Access (the auth wall)

**Blocked on a domain decision.** Cloudflare Access requires a hostname inside a Cloudflare-managed zone. Putting Access in front of `*.up.railway.app` directly is **not supported**.

Options to unblock:
- **(B1) Existing Cloudflare-managed domain.** Add a CNAME like `capture.<domain>` → Railway-provided target. Set up Access with a self-hosted application policy. Identity provider = One-time PIN (email magic link). Allow rule = email allowlist (Sergey + wife). ~10 minutes once the domain is in place.
- **(B2) New domain at Cloudflare Registrar.** ~$10/yr. Add to Cloudflare, then proceed with B1.
- **(B3) Defer entirely.** Rely on URL obscurity for the short term. Risky if the URL ever leaks.

**Open question for next session:** does Sergey have an existing Cloudflare-managed domain? Confirm before writing the Access steps.

### Step C: optional polish (only if Sergey asks)

- Custom domain on Railway via CNAME (handled as part of B above).
- Switch from `--workers 1` after promoting `_jobs` to SQLite (the original Phase 7A item).
- Backups: cron + rclone the `/data` volume contents to OneDrive if Railway's volume durability isn't trusted.
- Auto-purge `input_images/` on successful export (richer than the all-or-nothing Clear Data button).

---

## Required env vars on Railway (reference)

| Variable | Required? | Default in Dockerfile | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | yes | _(none)_ | Set in Railway Variables, never commit |
| `USE_MOCK_GEMINI` | yes | `true` | **Must be `false`** for real Gemini calls |
| `GEMINI_MODEL` | recommended | _(reads `gemini-2.5-flash` in `real_gemini.py`)_ | Match what `real_gemini.py` expects |
| `APP_DATA_DIR` | no | `/data` | Override only if mounting the volume elsewhere |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` for verbose logs |
| `ENV_FILE` | no | _(unset)_ | Use only if you'd rather load from a dotenv file |
| `FRONTEND_DIST_DIR` | no | `/app/frontend_dist` | Path inside the image |
| `PORT` | injected by Railway | _(falls back to 8000)_ | uvicorn binds to `${PORT:-8000}` |

**Not required:** `DATABASE_URL`. The active `/inbound` pipeline is filesystem-only.

---

## Required Railway volume (reference)

| Mount path | Contents |
|---|---|
| `/data` | `input_images/`, `inbound/`, `exports/` (created on demand by the app) |

Without this volume, every redeploy wipes user data.

---

## Key gotchas to remember (cumulative — Phase M)

1. **Single uvicorn worker is mandatory.** `_jobs` is in-process. Documented in the Dockerfile and README.
2. **`.env` is gitignored** and was never pushed. The key lives only in `.env` locally and Railway Variables in production.
3. **Local Docker testing uses `_local_data/`** at the project root as the volume mount.
4. **Render-vs-data dirs.** The container reads/writes inside `/data`, not inside the repo. Locally with `dev.bat`, the app uses repo-root paths because `APP_DATA_DIR` defaults to the repo root.
5. **Don't reintroduce CORS config** in `main.py`. Single-origin SPA serving is the design.
6. **Anchor `.gitignore` runtime-storage patterns to repo root.** Unanchored folder names match anywhere in the tree and silently exclude same-named source packages. (Bit us with `exports/`; same trap exists for any future folder.)
7. **`_SAFE_CSV_FILENAME` regex + resolved-path containment is the path-traversal pattern.** Used by `/inbound/images/{filename}` and `/inbound/exports/{filename}`. Reuse it for any future filename-in-URL endpoint.
8. **`DELETE /inbound/data` has no server-side auth.** Relies on Cloudflare Access. If the Access layer is delayed, treat this endpoint as the same risk surface as the rest of the app.

---

## Handover bundle staleness

Files `05_inbound_routes.py`, `06_config.py`, and `07_backend_pyproject.toml` in this folder are **stale** — they reflect the pre-migration shape. Always read the live files at:
- `backend/src/service_photo/api/inbound_routes.py`
- `backend/src/service_photo/core/config.py`
- `backend/pyproject.toml`

---

## Kickoff prompt for the next session

Paste this into a fresh Claude session when you're ready to wire up Cloudflare Access:

> I'm continuing the hosted migration of Catalog Capture. The Railway deployment is live and end-to-end verified — upload, extract (real Gemini), review, export-with-browser-download all work. Read `docs/handover/10_hosted_migration_status.md` first; it's the source of truth.
>
> Two things to do this session:
>
> 1. Quick smoke-test of the merged "Clear Data" button on the live URL (upload → export → clear → verify counts + that uploads still work after).
> 2. Then walk me through Cloudflare Access setup, treating me as a non-developer. Before you start, ask whether I have an existing Cloudflare-managed domain — that decision shapes the steps.
>
> Don't write code unless deployment surfaces a real bug. The app is feature-complete for this phase.
