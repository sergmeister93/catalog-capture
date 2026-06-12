"""
FastAPI application entry point for the Service Photo POC.

Run with:
  cd backend
  uvicorn service_photo.main:app --reload --host 0.0.0.0 --port 8000

API base URL: http://localhost:8000/api/v1
Interactive docs: http://localhost:8000/docs
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from service_photo.core.config import settings
# Import the review schemas module first so its bottom-of-file model_rebuild()
# runs BEFORE api.routes imports trigger FastAPI's @router decorator, which
# builds a TypeAdapter for ReviewPayload and needs its forward refs resolved.
from service_photo.schemas import review as _review_schema  # noqa: F401
from service_photo.api.routes import router
from service_photo.api.inbound_routes import router as inbound_router

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log startup configuration and prepare the SQLite durability layer."""
    logger.info("Service Photo POC starting up")
    logger.info("Database: %s", settings.DATABASE_URL.split("@")[-1])
    logger.info("Gemini mode: %s", "mock" if settings.USE_MOCK_GEMINI else "real")
    logger.info("Storage path: %s", settings.STORAGE_BASE_PATH)
    # Create the inbound-pipeline SQLite schema (jobs, review state, audit)
    # up front so the first request doesn't pay the DDL cost and a bad
    # APP_DATA_DIR surfaces as a startup failure, not a mid-session 500.
    from service_photo.services import inbound_store
    inbound_store.init_db()
    logger.info("Inbound SQLite store ready: %s", inbound_store.DB_PATH)
    yield
    logger.info("Service Photo POC shutting down")


app = FastAPI(
    title="Service Photo POC API",
    version="0.1.0",
    description="AI-assisted used-camera listing workflow: photos → Gemini draft → human review → CSV export.",
    lifespan=lifespan,
)

# Mount all routes under /api/v1 to match the OpenAPI server definition.
app.include_router(router, prefix="/api/v1")
# Inbound flow (filesystem-backed, no DB) — same prefix, separate router.
app.include_router(inbound_router, prefix="/api/v1")


# Liveness probe for the hosting platform (Railway healthcheck, Docker
# HEALTHCHECK). Registered BEFORE the SPA catch-all below so it always
# resolves to this handler. Deliberately does no I/O — it answers "is the
# process serving requests", not "is every dependency healthy".
@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict:
    return {"status": "ok", "version": app.version}


# --- Optional: serve the built frontend from the same origin ----------------
# In hosted mode (Railway, Docker, etc.) we ship the Vite build alongside the
# backend so a single uvicorn process serves both /api/* and the SPA. This
# eliminates the CORS surface entirely — the browser only ever talks to one
# origin.
#
# Resolution order for the static dir:
#   1. FRONTEND_DIST_DIR env var (explicit override).
#   2. /app/frontend_dist (where the Dockerfile copies the build).
#   3. <repo>/frontend/dist (handy for local `vite build` testing).
# If none of those exist we silently skip mounting — local dev (`dev.bat`)
# uses the Vite dev server on :5173 and proxies /api to :8000, so the
# backend doesn't need to serve any static assets.
def _resolve_frontend_dist() -> Path | None:
    explicit = os.environ.get("FRONTEND_DIST_DIR")
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path("/app/frontend_dist"))
    # Repo-root layout fallback for local docker testing without overrides.
    candidates.append(Path(__file__).resolve().parents[3] / "frontend" / "dist")
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    return None


_FRONTEND_DIST = _resolve_frontend_dist()
if _FRONTEND_DIST is not None:
    logger.info("Serving frontend from %s", _FRONTEND_DIST)
    # Mount Vite's hashed static assets under /assets (the Vite default
    # output dir). Anything else hits the SPA catch-all below.
    assets_dir = _FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def _serve_index() -> FileResponse:
        return FileResponse(_FRONTEND_DIST / "index.html")

    # SPA catch-all — anything that isn't /api/*, /docs, /openapi.json, or a
    # known static asset returns index.html so client-side hash routing works
    # on a hard refresh.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith(("api/", "docs", "openapi.json", "redoc")):
            raise HTTPException(status_code=404)
        # Serve a real file if it happens to exist at the top level (favicon,
        # manifest, etc.) — otherwise fall through to index.html.
        candidate = _FRONTEND_DIST / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Unwrap structured error details.

    Our routes raise `HTTPException(detail={"error": "...", "message": "..."})`
    because the OpenAPI contract specifies error responses with top-level
    `error` + `message` fields. FastAPI's default handler would wrap that
    dict inside `{"detail": ...}`, which would break the contract. This
    handler passes structured dict details through as-is, and falls back
    to the standard `{"detail": ...}` shape for simple string details.
    """
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Return a structured error response for unhandled exceptions."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "message": "An unexpected error occurred."},
    )
