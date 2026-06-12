# syntax=docker/dockerfile:1.6
# ---------------------------------------------------------------------------
# Catalog Capture — single-image production container for Railway.
#
# Layout:
#   Stage 1 (frontend-build) — node:20-alpine, runs `npm ci && npm run build`
#                              to produce frontend/dist.
#   Stage 2 (runtime)        — python:3.12-slim, installs the FastAPI
#                              backend and copies the built frontend
#                              alongside it. uvicorn serves both /api/* and
#                              the SPA from one process.
#
# Why one container, not two:
#   - Railway charges per service and per running replica; one image is
#     simpler and cheaper for a single-user POC.
#   - Same-origin frontend → backend means no CORS configuration to babysit.
#   - The in-memory _jobs dict in inbound_routes.py forces single-worker
#     uvicorn anyway, so there's no horizontal-scaling story to give up.
#
# Persistent storage:
#   The container expects /data to be a mounted Railway Volume. APP_DATA_DIR
#   defaults to /data so input_images/, inbound/, exports/ all land there.
#   Without a volume, uploads and CSVs are lost on every redeploy.
#
# Required env vars at runtime (set in Railway):
#   GEMINI_API_KEY   — your Google AI Studio key (real Gemini calls)
#   USE_MOCK_GEMINI  — "false" for real Gemini, "true" for mock
#   PORT             — Railway injects this; uvicorn binds to it below
# Optional:
#   APP_DATA_DIR     — defaults to /data (set here as ENV)
#   GEMINI_MODEL     — e.g. gemini-2.5-flash
#   LOG_LEVEL        — INFO (default) / DEBUG
# ---------------------------------------------------------------------------

# ---------- Stage 1: build the React/Vite frontend -------------------------
FROM node:20-alpine AS frontend-build
WORKDIR /build

# Copy manifest first for better Docker layer caching on dep-only changes.
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

# Now the rest of the frontend source.
COPY frontend/ ./
RUN npm run build
# Output lands in /build/dist (Vite default).


# ---------- Stage 2: backend runtime + bundled frontend --------------------
FROM python:3.12-slim AS runtime

# Avoid .pyc clutter and unbuffered logs (so `railway logs` shows everything).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_DATA_DIR=/data \
    FRONTEND_DIST_DIR=/app/frontend_dist

WORKDIR /app

# OS deps:
#   - libpq5 supports psycopg2-binary at import time (the dormant /jobs
#     pipeline still imports SQLAlchemy + psycopg2 at startup, even though
#     no DB is required for the active /inbound flow).
#   - tini is a tiny init that reaps zombie processes and forwards signals
#     correctly so Railway's restart / shutdown flows are clean.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 tini \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching).
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/src ./backend/src
RUN pip install --upgrade pip \
 && pip install ./backend

# The dormant /jobs pipeline (api/routes.py → submit_service.py) loads
# contracts/gemini_response_schema.json at import time by walking parent
# directories. Drop a copy at the filesystem root so the walk finds it
# regardless of where the package is installed. Cheap (~10 KB), and stops
# the import chain from blowing up startup even though nothing in the
# active /inbound flow actually uses these contracts at runtime.
COPY contracts /contracts

# Drop the built frontend in next to the backend.
COPY --from=frontend-build /build/dist /app/frontend_dist

# Create the data dir as a fallback for local docker runs without a volume.
# In Railway this gets shadowed by the mounted volume.
RUN mkdir -p /data/input_images /data/inbound /data/exports

EXPOSE 8000

# Container-level liveness probe against the app's /healthz endpoint.
# Uses Python's stdlib (no curl in slim images). start-period covers the
# uvicorn + import-time startup window.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,os,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/healthz', timeout=4).status == 200 else 1)"

# Single worker is mandatory: api/inbound_routes.py keeps extraction job
# state in an in-process dict (_jobs). Multiple workers would silently
# round-robin polling requests across processes and "lose" jobs. If/when
# _jobs is promoted to SQLite (Phase 7A), this can be raised.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "uvicorn service_photo.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
