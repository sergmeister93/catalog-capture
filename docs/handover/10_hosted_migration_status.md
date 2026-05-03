# Hosted Migration — Current Status & Next-Session Handoff

_Snapshot: 2026-05-03. Author: Claude (Opus 4.7), pair-programming with Sergey._

This file is the **single source of truth** for where the hosted-deployment work stands. Read this first when picking the project back up — it supersedes the planning-phase content in `01_self_host_migration_spec.md` (which described a home Ubuntu mini-PC + Cloudflare Tunnel target; the actual deployment pivoted to **Railway + Cloudflare Access** for lower friction).

---

## TL;DR

- The app is **containerized and verified locally on Windows + Docker Desktop**. End-to-end run inside the container worked: upload → Gemini extraction (real, not mock) → Review → CSV export to a mounted volume.
- The repo is **pushed to a private GitHub repo** at https://github.com/sergmeister93/catalog-capture. `.env` and all runtime data folders are gitignored and verified absent from the push.
- **Railway deployment has not started yet.** That is the next concrete step.
- **Cloudflare Access has not been wired up yet.** That comes after Railway is live.

---

## What shipped in this round (code + infra)

### New files
| Path | Purpose |
|---|---|
| `Dockerfile` | Multi-stage build: `node:20-alpine` builds the Vite frontend → `python:3.12-slim` installs the backend, copies the `dist/` next to it, runs uvicorn `--workers 1` under `tini`. Defaults `APP_DATA_DIR=/data`, `FRONTEND_DIST_DIR=/app/frontend_dist`. |
| `.dockerignore` | Excludes `node_modules/`, `_local_data/`, `input_images/`, `inbound/`, `exports/`, `storage/`, `test_data/`, `.env`, etc. — keeps the build context lean and prevents secrets/data from being baked in. |

### Modified files
| Path | Change |
|---|---|
| `backend/src/service_photo/core/config.py` | Added `APP_DATA_DIR` setting (default = repo root for local dev, `/data` in container). Added `ENV_FILE` env-var override for the dotenv file. The original `parents[4]/.env` lookup is preserved as a fallback so `dev.bat` keeps working. Exposes `APP_DATA_PATH` for callers. |
| `backend/src/service_photo/api/inbound_routes.py` | `INBOUND_DIR` / `INPUT_IMAGES_DIR` / `EXPORTS_DIR` now resolve under `APP_DATA_PATH`. Export-response `csv_path` is reported relative to `APP_DATA_PATH` instead of repo root. |
| `backend/src/service_photo/main.py` | Optional SPA-serving: if `FRONTEND_DIST_DIR` (or `/app/frontend_dist`, or `<repo>/frontend/dist`) exists, mount `/assets` and a SPA catch-all so a single uvicorn process serves both the React app and `/api/*`. Eliminates CORS. Skipped silently in local dev (Vite dev server still proxies). |
| `backend/src/service_photo/services/inbound_extraction.py` | `PROMPT_PATH` now resolves relative to the package (so it survives `pip install`). `SCHEMA_PATH` walks parents to find `contracts/gemini_response_schema.json` — works in dev (repo root) and in the container (Dockerfile drops a copy at `/contracts`). |
| `backend/pyproject.toml` | Added `[tool.setuptools.package-data]` so `prompts/*.md` ships inside the installed wheel. Without this, `pip install ./backend` strips the prompts dir and the container can't find the extraction prompt. |
| `README.md` | New "Hosted Railway Deployment" section: env vars, volume mount, single-worker rationale, local Docker test command, risks. |
| `.gitignore` | Added `_local_data/`, `input_images/`, and broad media excludes (`*.mp4`, `*.mov`, `*.wav`, `*.mp3`, `handover/video_demos/`). |

### Bugs found and fixed during the local Docker shake-down (do not reintroduce)
1. **Dormant `/jobs` pipeline blocks startup if `contracts/` is missing.** `services/submit_service.py` walks parent dirs at import time looking for `contracts/gemini_response_schema.json`. The Dockerfile now `COPY contracts /contracts` so the walk-up succeeds even though the active flow doesn't need it.
2. **Prompts not in the installed package.** `prompts/listing_extraction_v1.md` is not a Python module, so it's stripped by default. Fixed via `package-data` in `pyproject.toml`.
3. **Inbound extraction used a repo-root-relative prompt path.** Replaced with a package-relative resolution (same pattern `real_gemini.py` already uses).

---

## Local verification (the bar that's been cleared)

From the project root on Windows:
```cmd
docker build -t catalog-capture .
docker run --rm -p 8000:8000 --env-file .env -v "%cd%\_local_data:/data" catalog-capture
```
Then http://localhost:8000/ loaded the app, a single image extracted successfully against real Gemini (`gemini-2.5-flash`), and the CSV landed in `_local_data/exports/`.

The `.env` file at repo root contains `GEMINI_API_KEY` (Sergey rotated the key after a leak earlier in the session) and `USE_MOCK_GEMINI=false`. It is gitignored and was never committed.

---

## What's left — pick this up next session

### Step 1: Railway deploy
1. Sign in to https://railway.app/ with the `sergmeister93` GitHub account.
2. **+ New Project → Deploy from GitHub repo → catalog-capture**. Railway autodetects the root `Dockerfile`.
3. In the service settings, add a **Volume** mounted at `/data` (1 GB is fine to start).
4. In the service Variables tab, set:
   - `GEMINI_API_KEY` = the rotated key (Sergey has it; do not paste in chat)
   - `USE_MOCK_GEMINI` = `false`
   - `GEMINI_MODEL` = `gemini-2.5-flash`
5. Wait for the build, then **Settings → Networking → Generate Domain**. Open the URL.
6. Smoke test: upload a photo, run analysis, export. Confirm the CSV appears (downloadable via the UI; on the server it sits in `/data/exports/`).

### Step 2: Cloudflare Access (auth)
1. Add your domain to Cloudflare (free plan), or skip if you'll use the raw `*.up.railway.app` URL.
2. Cloudflare Zero Trust → Access → Applications → **Add a self-hosted application**.
3. Application domain: the Railway URL (or your custom CNAME).
4. Identity provider: **One-time PIN** (email magic link).
5. Policy: Allow rule with `Emails` includes Sergey + wife.
6. Test from a browser session not logged into either email — magic link should arrive, app should load after.

### Step 3 (optional polish — only if Sergey asks)
- Custom domain on Railway (CNAME `capture.<domain>` → Railway-provided target).
- Switch from `--workers 1` after promoting `_jobs` to SQLite (Phase 7A in the original handoff). Until then, leave the worker count alone.
- Backups: cron + rclone the `/data` volume contents to OneDrive if Railway's volume durability isn't trusted.

---

## Required env vars on Railway (reference)

| Variable | Required? | Default in Dockerfile | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | yes | _(none)_ | Set in Railway Variables, never commit |
| `USE_MOCK_GEMINI` | yes | `true` | Must be `false` for real Gemini calls |
| `GEMINI_MODEL` | recommended | _(reads `gemini-2.5-flash` in `real_gemini.py`)_ | Match what `real_gemini.py` expects |
| `APP_DATA_DIR` | no | `/data` | Override only if you mount the volume elsewhere |
| `LOG_LEVEL` | no | `INFO` | `DEBUG` for verbose logs |
| `ENV_FILE` | no | _(unset)_ | Use only if you'd rather load from a dotenv file |
| `FRONTEND_DIST_DIR` | no | `/app/frontend_dist` | Path inside the image; don't change unless you also change the Dockerfile copy |
| `PORT` | injected by Railway | _(falls back to 8000)_ | uvicorn binds to `${PORT:-8000}` |

**Not required:** `DATABASE_URL`. The active `/inbound` pipeline is filesystem-only. SQLAlchemy is imported by the dormant `/jobs` pipeline at startup but never opens a connection unless those routes are hit.

---

## Required Railway volume (reference)

| Mount path | Contents |
|---|---|
| `/data` | `input_images/`, `inbound/`, `exports/` (created on demand by the app) |

Without this volume, every redeploy wipes user data.

---

## Key gotchas to remember

1. **Single uvicorn worker is mandatory.** `_jobs` is in-memory in `inbound_routes.py`. Multiple workers will silently round-robin polling requests across processes. Documented in the Dockerfile and README. Phase 7A (SQLite) is the prereq for raising worker count.
2. **`.env` is gitignored** and was never pushed. The new key (after rotation) lives only in `.env` locally and Railway Variables in production.
3. **Local Docker testing uses `_local_data/`** at the project root as the volume mount. It's gitignored. Don't confuse this with the old `exports/` folder at repo root (legacy, from pre-Docker dev runs).
4. **Render-vs-data dirs.** The container reads/writes inside `/data`, not inside the repo. Locally with `dev.bat`, the app still uses repo-root `inbound/` etc. because `APP_DATA_DIR` defaults to the repo root in that mode.
5. **Don't reintroduce CORS config** in `main.py`. The whole point of the SPA mount is single-origin; adding CORS would mean the production deployment is misconfigured.

---

## Handover bundle staleness

Files `05_inbound_routes.py` and `06_config.py` in this folder are **stale** (they reflect the pre-migration shape). They were used as planning input for the migration; they're now out of date. If you need the current source, read the live files at:
- `backend/src/service_photo/api/inbound_routes.py`
- `backend/src/service_photo/core/config.py`

`07_backend_pyproject.toml` is also stale (missing the `package-data` block).

---

## Kickoff prompt for the next session

Paste this into a fresh Claude session when you're ready to do the Railway deploy + CFA wiring:

> I'm continuing the hosted migration of Catalog Capture. The local Docker build is verified and the repo is pushed to https://github.com/sergmeister93/catalog-capture (private). Read `docs/handover/10_hosted_migration_status.md` first — it's the source of truth for where things stand. Then walk me through the Railway deployment steps one block at a time, treating me as a non-developer. After Railway is live and tested, walk me through Cloudflare Access setup the same way. Don't write any code unless the deployment surfaces a real bug — the app code is done for this phase.
