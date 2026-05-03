# Self-Host Migration Spec — Catalog Capture

_Status: **draft**, opened 2026-05-03. Author: Claude (Opus 4.7), in collaboration with Sergey._
_Purpose: this is the **technical spec** for moving Catalog Capture off Sergey's Windows PC and onto a home-hosted Ubuntu mini-PC, accessible by Sergey's wife from her personal Mac. It is intentionally written so it can be handed to GPT (or any other model / human) for Phase 2 planning without needing the rest of this repo._

---

## 1. Goal & non-goals

### Goal
Stand up Catalog Capture as a **single-user web app**, hosted on Sergey's home Ubuntu mini-PC, reachable from his wife's personal MacBook over the internet, behind email-based authentication. Same workflow as today (drop photos → run Gemini → review → export CSV), just remote.

### Non-goals (defer to a later phase)
- Multi-user / RBAC (Phase 7D in the existing handoff covers this)
- Mobile-friendly UI
- Marketplace API integration (Phase 7E)
- High availability / failover
- Automated CI/CD pipeline (manual `git pull && docker compose up -d --build` is fine for now)
- Migrating the dormant DB-backed `/jobs` pipeline (it's not in the active UX)

---

## 2. Decisions already made (do not re-debate without Sergey)

| Decision | Choice | Why |
|---|---|---|
| **Hosting target** | Home: GMKtec G3 PRO (i3-10110U, 16GB, 512GB) running Ubuntu Server | Sergey wants the learning value of self-hosting; rejects VPS for now |
| **Inbound networking** | **Cloudflare Tunnel** (`cloudflared` daemon initiates outbound TLS to Cloudflare; no port forwarding, no public IP exposure) | Residential ISP + dynamic IP, want zero firewall changes, want free TLS |
| **Authentication** | **Cloudflare Access** in front of the tunnel, email magic-link, allowlist = Sergey's email + wife's email | App has no built-in auth; CFA is zero-code, lowest friction, covers the single-user POC scope |
| **Wife's device** | Her **personal** MacBook (not work-managed) | Removes corporate firewall / IT-policy constraints |
| **Container runtime** | Docker + Docker Compose (v2, the `docker compose` plugin) | Standard, well-documented, matches Sergey's intermediate skill level |
| **OS** | Ubuntu Server 24.04 LTS (no desktop) | Long support, large hosting community, Sergey is comfortable with apt-based distros |
| **No new app dependencies** | Same Python deps in `backend/pyproject.toml`, same npm deps in `frontend/package.json` | POC rule from CLAUDE.md — "no new dependencies without asking" |

---

## 3. Target architecture

```
┌────────────────────────┐                      ┌──────────────────────────────────────────────┐
│   Wife's MacBook       │                      │   GMKtec mini-PC  (Ubuntu Server 24.04 LTS)  │
│   (Safari / Chrome)    │                      │                                              │
│                        │   HTTPS (TLS by CF)  │   ┌────────────────────────────────────┐     │
│   https://capture.     │ ───────────────────► │   │  cloudflared (Cloudflare Tunnel)    │     │
│   <yourdomain>.com     │                      │   │  outbound-only TLS to CF edge       │     │
└────────────────────────┘                      │   └──────────────┬─────────────────────┘     │
              │                                 │                  │ proxies to                 │
              │ auth via                        │                  ▼                            │
              ▼                                 │   ┌────────────────────────────────────┐     │
     ┌───────────────────┐                      │   │  nginx (frontend container)         │     │
     │ Cloudflare Access │  email magic-link    │   │  serves Vite-built static assets    │     │
     │ allowlist:        │ ◄────────────────────┤   │  + reverse-proxies /api/* → backend │     │
     │  sergey@…         │                      │   └──────────────┬─────────────────────┘     │
     │  wife@…           │                      │                  │ /api/v1/*                  │
     └───────────────────┘                      │                  ▼                            │
                                                │   ┌────────────────────────────────────┐     │
                                                │   │  backend container (uvicorn)        │     │
                                                │   │  FastAPI app                        │     │
                                                │   └──────────────┬─────────────────────┘     │
                                                │                  │ bind-mounts                │
                                                │                  ▼                            │
                                                │   ┌────────────────────────────────────┐     │
                                                │   │  /opt/catalog-capture/data/         │     │
                                                │   │    input_images/                    │     │
                                                │   │    inbound/                         │     │
                                                │   │    exports/                         │     │
                                                │   │    .env                             │     │
                                                │   └────────────────────────────────────┘     │
                                                └──────────────────────────────────────────────┘
```

### Why this shape
- **Two containers, not one**: keeps the frontend's nginx config independent of the backend image; matches the existing dev-time split (`localhost:5173` + `localhost:8000`); lets us rebuild the React bundle without restarting Python.
- **nginx, not Vite, in production**: Vite's dev server is not a production server. Vite builds a static bundle; nginx serves it and reverse-proxies `/api/*` to uvicorn so the browser only ever talks to one origin (no CORS surface).
- **No PostgreSQL**: the active `/inbound` pipeline is filesystem-only. The dormant `/jobs` pipeline needs Postgres but the UI doesn't expose it. Skip Postgres in the prod compose file. (If Phase 7A — promote `_jobs` to SQLite — lands first, that's still file-based and adds nothing here.)
- **Bind mounts, not named volumes**: makes backups trivial (rsync `/opt/catalog-capture/data/`) and lets Sergey poke at the files from SSH without `docker exec`.
- **Cloudflare Tunnel inside the compose file**: keeps the whole stack reproducible; one `docker compose up -d` brings the public URL back after a reboot.

---

## 4. Component inventory & changes required

| Component | Current state | Change for migration |
|---|---|---|
| **Backend (`backend/`)** | Runs via `uvicorn ... --reload` from `dev.bat` | Add `backend/Dockerfile` (python:3.12-slim base, install via `pip install -e .`, run `uvicorn ... --host 0.0.0.0 --port 8000` with `--workers 1`, no `--reload`) |
| **Frontend (`frontend/`)** | Runs via Vite dev server | Add `frontend/Dockerfile` (multi-stage: node:20-alpine builder runs `npm ci && npm run build`; nginx:alpine serves `dist/` + custom `nginx.conf` reverse-proxying `/api/` to `backend:8000`) |
| **`dev.bat`** | Windows launcher, double-click | Leave alone (still useful for local dev). Add a Linux equivalent: `Makefile` with `make up` / `make down` / `make logs` / `make rebuild` targets that wrap `docker compose` |
| **`.env`** | Repo root, absolute-path-resolved by `core/config.py` | Move to `/opt/catalog-capture/data/.env` on the server. Bind-mount it read-only into the backend container at the same relative path the resolver expects (`/app/.env` if `/app` is the working dir — verify the `parents[4]` math holds in the container layout, or override with `ENV_FILE` if the resolver is changed to honor it) |
| **`input_images/`, `inbound/`, `exports/`** | Repo-relative folders | Bind-mount from `/opt/catalog-capture/data/{input_images,inbound,exports}` to the same paths inside the backend container |
| **CORS config in `main.py`** | Allows `localhost:5173` | Add the public hostname (`https://capture.<yourdomain>.com`) to the allowed origins. Or — better — drop CORS entirely once nginx serves both origins as one (frontend at `/`, API at `/api/`) |
| **Upload size limit** | FastAPI accepts up to 25 MB/file (app-level cap) | nginx default `client_max_body_size` is 1 MB. **Must override** to `30M` in `nginx.conf` or uploads silently fail |
| **`_jobs` in-memory dict** | Single-process state in `inbound_routes.py` | No change — but this is why backend container must run `--workers 1`. Document it. (Phase 7A would fix this.) |
| **`scripts/run_gemini_extraction.py`** | CLI fallback, run from Windows | Optional: keep working by `docker exec catalog-capture-backend python -m scripts.run_gemini_extraction`. Document in README |
| **Path separators** | Backend uses `pathlib`, should be portable | Audit any `\\`-hardcoded paths. Spot-check `core/config.py` and `inbound_extraction.py` |

---

## 5. Authentication: Cloudflare Access

The app itself stays auth-less. CFA enforces auth at the edge — every request to `capture.<yourdomain>.com` is intercepted by Cloudflare, which checks for a valid CFA session cookie and otherwise sends the user through a magic-link flow.

**Setup steps** (Cloudflare dashboard, no code):
1. Add domain to Cloudflare (free plan is enough). Switch nameservers at your registrar.
2. Cloudflare Zero Trust → Access → Applications → "Add a self-hosted application".
3. Application domain: `capture.<yourdomain>.com`.
4. Identity provider: One-time PIN (email). No SSO needed for two users.
5. Policy: "Allow", with rule = `Emails` includes `sergey@…` and `wife@…`.
6. Session duration: 30 days (so wife isn't re-auth'ing weekly).

**What this gets us**:
- TLS handled by Cloudflare (no Let's Encrypt cert renewal on the box).
- Brute-force / scanner traffic never reaches the mini-PC.
- Adding a third user = one click in the dashboard, no code change.

**What it does NOT get us**:
- Per-user data segregation in the app (still single shared filesystem). Fine for single-user; revisit if Phase 7D lands.
- Audit log of who edited what (still no app-level identity).

---

## 6. Domain & DNS

- **Need a domain.** ~$10–15/year. Suggested registrars: Cloudflare Registrar (at-cost pricing, no markup, integrates trivially with the rest of this stack), Porkbun, Namecheap.
- Subdomain pattern: `capture.<yourdomain>.com`. Keep the apex available for other future projects.
- DNS record: CNAME `capture` → `<tunnel-id>.cfargotunnel.com` (auto-created when you set up the tunnel via the dashboard).

---

## 7. Secrets & config

| Secret | Where today | Where after migration |
|---|---|---|
| `GEMINI_API_KEY` | `.env` at repo root on Windows | `/opt/catalog-capture/data/.env` on Ubuntu, bind-mounted read-only into backend container, **chmod 600**, owner = the unprivileged user the backend runs as |
| Cloudflare Tunnel credentials | n/a | `/opt/catalog-capture/data/cloudflared/cert.pem` + tunnel JSON, bind-mounted into the `cloudflared` container |
| Database password | `.env` (`DATABASE_URL`) | Drop from `.env` if Postgres isn't in the prod compose. Keep `USE_MOCK_GEMINI=false`, `GEMINI_MODEL=gemini-2.5-flash` |

**Rule**: secrets never enter a built image, never get committed, and never appear in `docker inspect` (so prefer bind-mounted files over `environment:` blocks for the API key).

---

## 8. Backups

The data that matters: `/opt/catalog-capture/data/{input_images,inbound,exports,.env}`. Code is in git; containers are reproducible.

**Recommendation** (lightweight): nightly `cron` job that `tar.gz`'s `data/` and uploads to either:
- A second drive on the mini-PC (cheap, no cloud cost, but no off-site protection), **or**
- Rclone → OneDrive (Sergey already uses OneDrive — he's already in `OneDrive\Claude Projects\…`). One-time `rclone config`, then a 5-line cron script.

**Retention**: 14 daily snapshots, 8 weekly. ~10 GB total even with thousands of images.

Test restores quarterly. A backup you've never restored is a wish, not a backup.

---

## 9. Phased migration plan

Each phase is a **stopping point** — Sergey can pause between phases and the prior state still works.

### Phase M0 — Prereqs (off-server)
- Buy domain.
- Create Cloudflare account, add domain, switch nameservers, wait for propagation.
- Create Zero Trust account (free tier).

### Phase M1 — Server bring-up
- Install Ubuntu Server 24.04 LTS on the GMKtec (USB installer).
- Static LAN IP via router DHCP reservation (so SSH always lands on the same address).
- SSH key-only auth, disable password login, install `ufw` with default-deny inbound except 22 from LAN.
- Install Docker Engine + Compose plugin (official `get.docker.com` script).
- Create unprivileged user `capture`, add to `docker` group, `mkdir -p /opt/catalog-capture/{app,data}`.

### Phase M2 — Containerize the app (do this on Windows first, commit to repo)
- Write `backend/Dockerfile`.
- Write `frontend/Dockerfile` + `frontend/nginx.conf`.
- Write `docker-compose.yml` at repo root with three services: `backend`, `frontend`, `cloudflared`.
- Write `Makefile` with `up`/`down`/`logs`/`rebuild`/`shell-backend` targets.
- Test locally on Windows: `docker compose up --build`, hit `http://localhost/` (frontend container on port 80), confirm it can call `/api/v1/inbound` end-to-end.
- Commit. Do not push to the server yet.

### Phase M3 — Cloudflare Tunnel
- `cloudflared tunnel login` (browser flow, one-time).
- `cloudflared tunnel create catalog-capture` → produces tunnel UUID + credentials JSON.
- DNS route: `cloudflared tunnel route dns catalog-capture capture.<yourdomain>.com`.
- Tunnel config (in `data/cloudflared/config.yml`) routes all hostnames to `http://frontend:80`.
- Test by running `cloudflared tunnel run catalog-capture` locally pointed at the local compose stack — confirm `https://capture.<yourdomain>.com` reaches the app over the public internet.

### Phase M4 — Cloudflare Access
- Add the Access application + email allowlist policy as in §5.
- Re-test from a browser where you're not logged into either email — confirm magic link arrives, login works, app loads after.

### Phase M5 — Deploy to the mini-PC
- `git clone` the repo to `/opt/catalog-capture/app`.
- Copy `.env` and `cloudflared/` credentials into `/opt/catalog-capture/data/` (out-of-band — `scp` from the Windows box).
- Optionally rsync existing `inbound/` and `exports/` to preserve Sergey's prior runs.
- `make up`. Confirm `https://capture.<yourdomain>.com` works from outside the LAN (turn off Wi-Fi on phone, use cellular).

### Phase M6 — Hardening & ops
- Backups (§8): write the cron + rclone script, test a restore.
- Auto-restart: `restart: unless-stopped` on every compose service. Confirm the stack comes back after a `sudo reboot`.
- Log rotation: Docker's default `json-file` driver grows unbounded. Set `max-size: 10m`, `max-file: 5` in `/etc/docker/daemon.json`.
- Update strategy: write a one-page runbook (`docs/runbook_self_host.md`) covering "deploy a code change", "rotate Gemini key", "restore from backup", "kick the tunnel".

### Phase M7 — Cutover & decommission
- Hand wife the URL, walk her through the magic-link flow once.
- After a week of stable use, stop running `dev.bat` on the Windows box. Keep the repo clone there for emergency local fallback / future development.

---

## 10. Risks & open questions for Phase 2 planning (the GPT handoff)

These are things this spec **does not yet answer** — Sergey should hand them to GPT (or back to Claude) for the next round.

| # | Risk / Question | Why it matters | Suggested resolution path |
|---|---|---|---|
| R1 | **Residential ISP TOS.** Some US residential ISPs (Comcast, Verizon Fios, others) prohibit "running servers." Cloudflare Tunnel masks the inbound connection — there are no inbound ports — so this is mostly a paper risk, but worth a one-line check of Sergey's ISP TOS. | Could result in service disruption if ISP enforces. | Read the ISP's residential TOS once. If unclear, the tunnel makes detection unlikely; document and move on. |
| R2 | **Power / internet outages.** Home connection is not 99.9% uptime. | Wife can't review listings during outages. | Acceptable for POC. Future: small UPS (~$80) for the mini-PC + router; revisit VPS if this becomes painful. |
| R3 | **`_jobs` in RAM = single uvicorn worker.** Running multiple workers will silently break progress polling. | Limits throughput to one extraction job at a time. | Document in compose file as a comment. Phase 7A fixes properly. |
| R4 | **`.env` path resolution math (`parents[4]`) is fragile in a container.** The resolver was written assuming `backend/src/service_photo/core/config.py` lives 4 levels under repo root. Container layout may differ. | App fails to find `GEMINI_API_KEY` — same failure mode as Phase 4 bug #5. | Either reproduce the same directory depth in the image, or refactor `core/config.py` to honor an `ENV_FILE` env var with a sensible default. Recommend the latter — small change, much more portable. |
| R5 | **No image / file size enforcement at the proxy layer today.** | A malicious or buggy upload could fill `/opt/catalog-capture/data/`. | nginx `client_max_body_size 30M` is necessary anyway; also set a disk-usage alert (`df` cron). Single-user scope makes this low-priority. |
| R6 | **Wife's first-time onboarding.** | She's never seen the app. | Sergey should plan a 15-minute screen share for the first session. The UX is already polished (Phase 6G); the only new concept is the magic-link auth. |
| R7 | **Domain name choice.** | Bikeshed-able, blocks Phase M0. | Suggest something forgettable but yours (`capture-<lastname>.com` or similar). Use Cloudflare Registrar for one-throat-to-choke. |
| R8 | **Backup destination.** | Open. | Recommend OneDrive via rclone (Sergey already pays for it). GPT can scope the rclone setup. |
| R9 | **Should the migration include Phase 7A (SQLite job state) as a prereq?** | If yes, the migration becomes a 2-piece change. | Recommend **no** — ship the migration first with the in-memory caveat documented. Adding SQLite is a separate, orthogonal change that doesn't touch the deployment topology. |
| R10 | **Per-image / per-batch size growth.** | Camera photos are ~5–15 MB each; a year of use could accumulate hundreds of GB. | 512 GB on the mini-PC is plenty for POC. Add a `du -sh` to the backup cron; if growth is faster than expected, set a retention policy on `input_images/` (move to cold storage after N days). |

---

## 11. Files this spec implies creating (none yet exist)

When the implementation phase starts, expect these new files:

```
backend/Dockerfile
frontend/Dockerfile
frontend/nginx.conf
docker-compose.yml          (repo root)
Makefile                    (repo root)
docs/runbook_self_host.md   (operational playbook — written during Phase M6)
```

And these existing files will be touched:

```
backend/src/service_photo/core/config.py   (likely refactored for ENV_FILE override — see R4)
backend/src/service_photo/main.py           (CORS — see §4)
.gitignore                                  (add cloudflared credentials, data/)
README.md                                   (point to this spec + the runbook)
```

---

## 12. Out of scope (to be explicit)

- Migrating the dormant `/jobs` Postgres pipeline. Not in active UX.
- Multi-environment (staging vs. prod). One environment.
- CI/CD. Manual `git pull && make rebuild` on the server.
- Observability (Prometheus / Grafana / Sentry). `docker logs` is enough.
- Secret rotation automation. Manual when needed.
- Mobile responsiveness. Desktop only.

---

## Appendix A — Comprehensive handoff bundle (what to share with GPT)

If you're handing this project to a fresh model for Phase 2 implementation planning, share these files (in this order):

1. **This spec** — `docs/05_self_host_migration_spec.md` (you are here)
2. **Project root context** — `CLAUDE.md` (workflow, gotchas, contracts pointers)
3. **Existing Phase 7 menu** — `docs/claude_code_phase7_handoff.md` (so GPT sees what else is on the table and doesn't double-scope)
4. **Project narrative** — `docs/00_project_documentation.md` (full context for what the app does)
5. **Active backend route module** — `backend/src/service_photo/api/inbound_routes.py` (shows the in-memory `_jobs` pattern, the upload endpoint, the extraction trigger)
6. **Backend config** — `backend/src/service_photo/core/config.py` (the `parents[4]` env-file resolver — see R4)
7. **Backend deps** — `backend/pyproject.toml`
8. **Frontend deps** — `frontend/package.json`
9. **Current Windows launcher** — `dev.bat` (so GPT sees what the Linux equivalent is replacing)

Optional, only if GPT asks:
- `contracts/openapi_service_photo_poc.yaml` (full API surface)
- `docs/03_ui_design.md` (design system — only relevant if the migration touches UI)

**Do not** share the dormant `/jobs` pipeline files (`api/routes.py`, `services/export_service.py`, etc.) — they're out of scope and will distract.
