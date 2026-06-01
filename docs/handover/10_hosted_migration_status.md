# Hosted Migration — Final Status

_Last updated: 2026-05-03 (late evening). Author: Claude (Opus 4.7), pair-programming with Sergey._

**Phase M is COMPLETE.** This file is the historical record of how the hosted deployment came together. It supersedes the planning-phase content in `01_self_host_migration_spec.md` (which described a home Ubuntu mini-PC + Cloudflare Tunnel target; the actual deployment pivoted to **Railway + Cloudflare Access** for lower friction).

---

## TL;DR

- ✅ **Railway deployment is LIVE.** The container is running on the `catalog-capture` service in Railway project `accurate-liberation`, region `us-west2`, mounted volume at `/data`, env vars set (`GEMINI_API_KEY`, `USE_MOCK_GEMINI=false`, `GEMINI_MODEL=gemini-2.5-flash`). End-to-end smoke test passed against real Gemini: upload → extract → review → export → CSV downloads to browser.
- ✅ **CSV download works in the browser.** `GET /api/v1/inbound/exports/{filename}` (PR #1, merged) lets the user pull exported CSVs into Chrome's Downloads folder. The CSV also persists on the volume.
- ✅ **"Clear Data" button shipped.** `DELETE /api/v1/inbound/data` + button on the Upload screen (PR #2, merged) gives the user a single-click full reset of `input_images/`, `inbound/`, `exports/`, plus the two browser-side localStorage keys. Endpoint has no server-side auth — relies on Cloudflare Access (now in place).
- ✅ **Cloudflare Access is LIVE.** Live URL is `https://app.catalog-capture.com`. Zero Trust team `sbf322`, One-time PIN identity provider, reusable email-allowlist policy with Sergey + wife. The destructive `DELETE /inbound/data` is now gated.

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

Phase M is closed. Optional polish items kicked to a future session (only if Sergey asks):

- Switch from `--workers 1` after promoting `_jobs` to SQLite (the original Phase 7A item).
- Backups: cron + rclone the `/data` volume contents to OneDrive if Railway's volume durability isn't trusted.
- Auto-purge `input_images/` on successful export (richer than the all-or-nothing Clear Data button).
- Self-host Inter/Manrope fonts to drop the Google Fonts CDN dependency (cosmetic, only matters if Sergey ever wants an air-gapped build).
- Consider replacing One-time PIN with Google OAuth as the IDP if the OTP delivery flakiness recurs (better UX, requires a Google Cloud OAuth client).

### How Step B (Cloudflare Access) actually shipped

For the historical record. Sergey resolved the domain blocker by registering `catalog-capture.com` at **Cloudflare Registrar** (~$10/yr, expires May 2027). The end-to-end click path was:

1. **Railway custom domain.** Service → Settings → Networking → Custom Domain → enter `app.catalog-capture.com`, port 8080. Railway invoked the one-click Cloudflare DNS authorization, which auto-creates the CNAME (`app` → `<railway-target>.up.railway.app`, **proxied / orange cloud**) and the `_railway-verify` TXT record. SSL/TLS mode in Cloudflare set to **Full (strict)** — Railway issues a valid Let's Encrypt cert for the custom hostname, so strict works.
2. **Zero Trust team.** First visit to `one.dash.cloudflare.com` prompted for a team name (chose `sbf322`) and plan (Free, covers up to 50 users).
3. **Identity provider.** One-time PIN was already present as the default in **Integrations → Identity providers**. No external IDP added.
4. **Reusable policy.** **Access controls → Policies → Create.** Named `Catalog Capture allowlist`, Action: Allow, Session: 1 month, Include rule: Selector = Emails, values = the owner + collaborator email addresses (two entries). The new Cloudflare One UI requires policies to be created as reusable objects *before* attaching them to apps; the inline-policy flow is gone.
5. **Self-hosted application.** **Access controls → Applications → Add application → Self-hosted.** Name `catalog-capture.com`, public hostname destination = subdomain `app` + domain `catalog-capture.com`. In the application Configure page, attached the `Catalog Capture allowlist` policy via the Access Policies section.

### OTP delivery quirk to remember

During setup, the One-time PIN emails took unusually long to arrive — the login page showed "A code has been emailed to you" but Gmail received nothing for several minutes despite multiple Resend clicks. Cloudflare's status page only listed a "delayed audit logs" incident, not OTP delivery. It eventually started working on its own. If a future user (e.g., wife on a fresh device) hits the same issue:

- Search Gmail for `from:noreply@notify.cloudflare.com` and just `cloudflare` (broader, no `from:` prefix).
- Check Promotions and Updates tabs (separate from "All Mail").
- Try Resend a couple times.
- If still no email after 30 min, the pragmatic pivot is replacing the IDP with Google OAuth — UX is better anyway (one click, no codes). Requires a Google Cloud OAuth 2.0 client (~15 min of setup) but doesn't depend on Cloudflare's mail pipe.

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

Phase M is closed; there's no specific next session queued. If Sergey decides to start any of the optional-polish items above, draft a fresh prompt that names the specific item and points the new session at this doc + the project's `CLAUDE.md`.
