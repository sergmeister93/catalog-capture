"""
Inbound-folder routes — filesystem artifacts + SQLite review/job state.

These endpoints serve the new UI flow where each photo is its own product
listing. Gemini extraction drops one JSON per image into inbound/ (the
immutable "draft" layer). Human review state — edits, approvals, the audit
trail, and extraction-job progress — lives in SQLite at
<APP_DATA_PATH>/catalog.db (see services/inbound_store.py), which is what
lets uvicorn run multiple workers and survive restarts.

This intentionally bypasses the dormant /jobs Postgres pipeline.

Endpoints:
  GET    /api/v1/inbound                          — list artifacts + saved review state
  GET    /api/v1/inbound/input-images             — list files in input_images/ (for Prep)
  POST   /api/v1/inbound/input-images             — drag-and-drop upload
  GET    /api/v1/inbound/images/{filename}        — serve an image by filename
  GET    /api/v1/inbound/batches                  — group artifacts by batch
  POST   /api/v1/inbound/extract                  — kick off Gemini over input_images/
  GET    /api/v1/inbound/extract/{job_id}         — poll extraction progress/status
  PUT    /api/v1/inbound/review/{extraction_id}   — save a card's edited content
  POST   /api/v1/inbound/review/{extraction_id}/approve   — approve a card
  DELETE /api/v1/inbound/review/{extraction_id}/approve   — remove approval
  POST   /api/v1/inbound/export                   — write a CSV of approved cards
  GET    /api/v1/inbound/exports/{filename}       — download a written CSV
  DELETE /api/v1/inbound/data                     — full reset (files + DB)

Filesystem layout (under APP_DATA_PATH):
  inbound/      — one extraction_<timestamp>__<image-stem>.json per image
  input_images/ — the source photos those extractions came from
  exports/      — written CSVs land here (created on demand, gitignored)
  catalog.db    — SQLite: jobs, review state, audit trail, export records
"""

import csv
import io
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from service_photo.services import inbound_store
from service_photo.services.inbound_extraction import (
    IMAGE_SUFFIXES,
    ImageResult,
    discover_images,
    run_extraction,
)
from service_photo.integrations.gemini_interface import GeminiClientError
from service_photo.core.config import APP_DATA_PATH

# --- Path setup ---------------------------------------------------------------
# Inbound state lives under APP_DATA_PATH (settings.APP_DATA_DIR).
# Local dev: repo root, so input_images/, inbound/, exports/ stay where they
#            always were and dev.bat keeps working.
# Hosted (Railway): /data — a mounted persistent volume — so uploads, Gemini
#            artifacts, and exports survive container restarts.
# REPO_ROOT is kept as the original repo-root anchor (used only to compute
# relative paths in API responses, not to read or write files).
REPO_ROOT = Path(__file__).resolve().parents[4]
INBOUND_DIR = APP_DATA_PATH / "inbound"
INPUT_IMAGES_DIR = APP_DATA_PATH / "input_images"
EXPORTS_DIR = APP_DATA_PATH / "exports"

# Filename-safe stem pattern for incoming filenames (defense against path
# traversal in the image-serving route). Allows letters, digits, dot, dash,
# underscore — covers everything our extraction script writes.
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+$")

router = APIRouter()


def _actor(request: Request) -> str:
    """Identity for the audit trail.

    In hosted mode every request passes through Cloudflare Access, which
    injects the authenticated user's email in this header — so we get a real
    "who did this" for free, with zero auth code. Local dev has no Access
    layer, so fall back to a fixed marker.
    """
    return request.headers.get("Cf-Access-Authenticated-User-Email") or "local-dev"


# --- Schemas -----------------------------------------------------------------

class ReviewState(BaseModel):
    """Server-stored review state for one card (was browser localStorage)."""
    edited_response: dict = Field(..., description="The human-edited copy of the Gemini response")
    edited_pricing: dict | None = Field(None, description="Edited pricing block, or null when the item has none")
    approved: bool
    approved_at_utc: str | None = None
    approved_by: str | None = None
    updated_at_utc: str


class InboundItem(BaseModel):
    """One extraction artifact, ready for the UI to render as a card."""
    extraction_id: str = Field(..., description="Filename without .json — stable id for the card")
    file_name: str = Field(..., description="Full filename of the artifact in inbound/")
    image_files: list[str] = Field(..., description="Source image filenames (always one in per-image mode)")
    image_urls: list[str] = Field(..., description="URLs the browser can use to load each source image")
    meta: dict = Field(..., description="The 'meta' block from the artifact (timestamps, model, validation flags)")
    response: dict | None = Field(None, description="The Gemini response, or null if the API call failed")
    # Phase 5 (single-pass): pricing is returned in the same Gemini call as
    # extraction. Absent when Gemini declined to produce one (e.g. identity
    # was too uncertain). There is no separate `pricing_error` field anymore —
    # a failed pricing is indistinguishable from a failed extraction, so the
    # existing `meta.api_error` path covers it.
    pricing: dict | None = Field(None, description="Pricing block from the combined extraction call, or null when Gemini returned none.")
    # Phase 7A: the saved review state (edits + approval), or null when the
    # card has never been edited or approved. Replaces browser localStorage.
    review: ReviewState | None = Field(None, description="Server-stored review state, or null if untouched.")


class InboundListResponse(BaseModel):
    items: list[InboundItem]
    inbound_dir: str = Field(..., description="Filesystem path being listed (informational)")


class InputImageFile(BaseModel):
    """One file in input_images/ — used by the Prep screen thumbnail list."""
    file_name: str
    file_size_bytes: int
    image_url: str = Field(..., description="URL the browser can GET to render a thumbnail")


class InputImagesResponse(BaseModel):
    files: list[InputImageFile]
    input_dir: str


class UploadedFileResult(BaseModel):
    """Per-file outcome of a drag-and-drop upload."""
    original_name: str
    saved_name: str | None = Field(None, description="Filename actually written to disk (may differ from original on collision)")
    file_size_bytes: int | None = None
    image_url: str | None = None
    ok: bool
    error: str | None = None


class UploadInputImagesResponse(BaseModel):
    results: list[UploadedFileResult]
    input_dir: str


class BatchSummary(BaseModel):
    """One extraction run (a Prep-initiated batch), assembled from per-image artifacts."""
    batch_id: str = Field(..., description="Stable id — the URL-safe batch_started_at_utc timestamp")
    batch_name: str | None
    started_at_utc: str | None
    image_count: int
    succeeded: int
    failed: int
    image_files: list[str]
    model: str | None


class BatchesResponse(BaseModel):
    batches: list[BatchSummary]


class ReviewSaveRequest(BaseModel):
    """Body for PUT /inbound/review/{extraction_id} — the card's current
    edited content. Approval state is NOT settable here; use the approve
    endpoints so every approval lands in the audit trail explicitly."""
    response: dict = Field(..., description="The full edited copy of the Gemini response")
    pricing: dict | None = Field(None, description="The edited pricing block, or null when the item has none")


class ApproveRequest(BaseModel):
    """Body for POST /inbound/review/{extraction_id}/approve.

    Carries the content currently on the reviewer's screen so approving a
    never-edited card still snapshots exactly what the human signed off on.
    """
    response: dict | None = Field(None, description="Current edited response (snapshotted at approval)")
    pricing: dict | None = Field(None, description="Current edited pricing block, if any")


class ExportRequest(BaseModel):
    """Body for POST /inbound/export.

    Phase 7A contract change: the client sends only the *ids* it wants in the
    CSV. Content comes from the server-stored, approved review snapshots —
    never from the request — so the export is exactly what was approved.
    """
    extraction_ids: list[str] = Field(..., description="Approved cards to include in the CSV")


class ExportResponse(BaseModel):
    csv_path: str = Field(..., description="Repo-relative path to the written CSV")
    csv_filename: str
    row_count: int
    exported_at_utc: str


# --- GET /api/v1/inbound ------------------------------------------------------

@router.get("/inbound", response_model=InboundListResponse)
def list_inbound() -> InboundListResponse:
    """
    Return every extraction artifact in inbound/, newest first.

    Each artifact is parsed and re-shaped into an `InboundItem` so the UI
    doesn't need to know the on-disk JSON structure. Files that fail to parse
    are skipped silently — corruption shouldn't stop the rest from rendering.
    """
    if not INBOUND_DIR.is_dir():
        # The folder is created on-demand by the extraction script; if it
        # doesn't exist yet, return an empty list (not a 404).
        return InboundListResponse(items=[], inbound_dir=str(INBOUND_DIR))

    # One DB read for the whole listing — review rows are keyed by
    # extraction_id, which is the artifact filename stem.
    reviews = inbound_store.get_all_reviews()

    items: list[InboundItem] = []
    json_files = sorted(INBOUND_DIR.glob("extraction_*.json"), reverse=True)
    for path in json_files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Skip unreadable / malformed files rather than failing the request.
            continue

        meta = raw.get("meta") or {}
        response = raw.get("response")
        image_files = list(meta.get("image_files") or [])
        review = reviews.get(path.stem)

        items.append(InboundItem(
            extraction_id=path.stem,
            file_name=path.name,
            image_files=image_files,
            image_urls=[f"/api/v1/inbound/images/{name}" for name in image_files],
            meta=meta,
            response=response,
            # Pricing is lifted up to the artifact root by the extraction
            # service. Absent when Gemini returned no pricing for this item.
            pricing=raw.get("pricing"),
            review=ReviewState(**review) if review else None,
        ))

    return InboundListResponse(items=items, inbound_dir=str(INBOUND_DIR))


# --- GET /api/v1/inbound/input-images ----------------------------------------

@router.get("/inbound/input-images", response_model=InputImagesResponse)
def list_input_images() -> InputImagesResponse:
    """
    List photos currently sitting in input_images/, for the Prep screen's
    left rail. Returns filenames + sizes, plus a URL each thumbnail can use
    (the existing /inbound/images/{filename} route, which already defends
    against path traversal).

    Empty folder returns an empty list (not a 404) — the UI renders that as
    "drop photos into input_images/ and hit Refresh".
    """
    if not INPUT_IMAGES_DIR.is_dir():
        return InputImagesResponse(files=[], input_dir=str(INPUT_IMAGES_DIR))

    files: list[InputImageFile] = []
    for path in sorted(INPUT_IMAGES_DIR.iterdir(), key=lambda p: p.name):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        files.append(InputImageFile(
            file_name=path.name,
            file_size_bytes=size,
            image_url=f"/api/v1/inbound/images/{path.name}",
        ))

    return InputImagesResponse(files=files, input_dir=str(INPUT_IMAGES_DIR))


# --- POST /api/v1/inbound/input-images ---------------------------------------

# Cap per-file upload size to keep a runaway client from filling the disk.
# 25 MB comfortably fits a ~20 MP JPEG or HEIC; anything larger is almost
# certainly a mistake (e.g. a raw .ARW/.CR2 file we can't feed to Gemini anyway).
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Cap the number of files in a single upload request. Generous for the real
# workflow (a batch is typically 5-30 photos) while bounding worst-case
# memory/disk per request.
_MAX_FILES_PER_UPLOAD = 50


def _sniff_image_format(data: bytes) -> str | None:
    """
    Identify the actual image format from the file's leading bytes (magic
    numbers). Returns a short format tag or None if the bytes don't match
    any format we accept. This is the content-level companion to the
    extension whitelist — an .exe renamed to .jpg passes the extension
    check but fails here.

    Formats covered (mirrors IMAGE_SUFFIXES):
      JPEG       — FF D8 FF
      PNG        — 89 50 4E 47 0D 0A 1A 0A
      WebP       — "RIFF" .... "WEBP"
      HEIC/HEIF  — ISO-BMFF: size + "ftyp" at offset 4, brand in a known set
    """
    if len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis",
                     b"mif1", b"msf1", b"avif"):
            return "heif"
    return None


def _unique_destination(directory: Path, original_name: str) -> Path:
    """
    Resolve a collision-free path under `directory` for an incoming filename.

    Strips the leading directory portion of `original_name` (browsers send
    just the basename, but defense-in-depth), then appends `-1`, `-2`, …
    before the suffix on collision. Example: `foo.jpg` → `foo-1.jpg`.
    """
    # Take just the basename — never trust client-supplied paths.
    stem_name = Path(original_name).name
    candidate = directory / stem_name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        alt = directory / f"{stem}-{counter}{suffix}"
        if not alt.exists():
            return alt
        counter += 1


@router.post("/inbound/input-images", response_model=UploadInputImagesResponse)
async def upload_input_images(
    files: list[UploadFile] = File(..., description="One or more image files to drop into input_images/"),
) -> UploadInputImagesResponse:
    """
    Accept drag-and-drop uploads from the Prep screen and write them into
    input_images/. One response row per file so the UI can show per-file
    success/failure without aborting the whole batch on a single bad file.

    Rules enforced here:
    - Filename must be a safe basename (letters, digits, dot, dash, underscore)
      after stripping any directory portion. Anything else is rejected.
    - Extension must be an image suffix we know how to feed to Gemini.
    - File content must pass a magic-byte check for a supported image format
      (extension alone is spoofable).
    - Per-file size capped at _MAX_UPLOAD_BYTES; request capped at
      _MAX_FILES_PER_UPLOAD files.
    - On filename collision, append `-1`, `-2`, … before the suffix.
    """
    if len(files) > _MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "too_many_files",
                "message": f"At most {_MAX_FILES_PER_UPLOAD} files per upload request.",
            },
        )

    INPUT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    results: list[UploadedFileResult] = []
    for upload in files:
        original = upload.filename or ""
        basename = Path(original).name

        # Validate filename shape before touching disk.
        if not basename or not _SAFE_FILENAME.match(basename):
            results.append(UploadedFileResult(
                original_name=original,
                ok=False,
                error="filename contains characters that aren't letters, digits, dot, dash, or underscore",
            ))
            continue
        if Path(basename).suffix.lower() not in IMAGE_SUFFIXES:
            results.append(UploadedFileResult(
                original_name=original,
                ok=False,
                error=f"unsupported file type (allowed: {', '.join(sorted(IMAGE_SUFFIXES))})",
            ))
            continue

        # Read the body into memory — fine at our 25 MB cap. We stop early
        # if the client exceeds the cap to avoid OOMing on a rogue upload.
        data = await upload.read()
        if len(data) == 0:
            results.append(UploadedFileResult(
                original_name=original,
                ok=False,
                error="empty file",
            ))
            continue
        if len(data) > _MAX_UPLOAD_BYTES:
            results.append(UploadedFileResult(
                original_name=original,
                ok=False,
                error=f"file exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
            ))
            continue

        # Content check: the extension whitelist above only inspects the
        # filename. Verify the leading bytes actually look like an image
        # format we accept, so arbitrary content can't land on the volume
        # just by being renamed to .jpg.
        if _sniff_image_format(data) is None:
            results.append(UploadedFileResult(
                original_name=original,
                ok=False,
                error="file content does not match a supported image format (JPEG, PNG, WebP, HEIC)",
            ))
            continue

        destination = _unique_destination(INPUT_IMAGES_DIR, basename)
        try:
            destination.write_bytes(data)
        except OSError as exc:
            results.append(UploadedFileResult(
                original_name=original,
                ok=False,
                error=f"write failed: {exc}",
            ))
            continue

        results.append(UploadedFileResult(
            original_name=original,
            saved_name=destination.name,
            file_size_bytes=len(data),
            image_url=f"/api/v1/inbound/images/{destination.name}",
            ok=True,
        ))

    return UploadInputImagesResponse(results=results, input_dir=str(INPUT_IMAGES_DIR))


# --- GET /api/v1/inbound/batches ---------------------------------------------

@router.get("/inbound/batches", response_model=BatchesResponse)
def list_batches() -> BatchesResponse:
    """
    Group inbound/ artifacts by batch. A batch is defined by the pair
    (meta.batch_name, meta.batch_started_at_utc) stamped at extraction time.

    Artifacts with no batch metadata (e.g. older CLI runs pre-Phase 6) are
    grouped under a synthetic "Legacy extractions" batch keyed by an empty
    timestamp — they still appear in the list, just without a name.

    Batches are returned newest-first (most recent run at the top).
    """
    if not INBOUND_DIR.is_dir():
        return BatchesResponse(batches=[])

    groups: dict[str, dict] = {}
    for path in INBOUND_DIR.glob("extraction_*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        meta = raw.get("meta") or {}
        batch_name = meta.get("batch_name")
        started_at = meta.get("batch_started_at_utc")
        # Use the started-at timestamp as the batch id; fall back to an empty
        # bucket for legacy artifacts with no batch metadata.
        batch_id = started_at or "__legacy__"

        bucket = groups.setdefault(batch_id, {
            "batch_id": batch_id,
            "batch_name": batch_name,
            "started_at_utc": started_at,
            "image_count": 0,
            "succeeded": 0,
            "failed": 0,
            "image_files": [],
            "model": meta.get("model"),
        })
        bucket["image_count"] += 1
        # Treat presence of a Gemini response + no api_error as success.
        if raw.get("response") is not None and not meta.get("api_error"):
            bucket["succeeded"] += 1
        else:
            bucket["failed"] += 1
        for name in (meta.get("image_files") or []):
            if name not in bucket["image_files"]:
                bucket["image_files"].append(name)

    # Newest batches first; legacy bucket sinks to the bottom because its
    # started_at is the empty string.
    summaries = sorted(
        (BatchSummary(**b) for b in groups.values()),
        key=lambda s: s.started_at_utc or "",
        reverse=True,
    )
    return BatchesResponse(batches=summaries)


# --- GET /api/v1/inbound/images/{filename} -----------------------------------

@router.get("/inbound/images/{filename}")
def get_inbound_image(filename: str):
    """
    Serve one source image from input_images/.

    Defends against path traversal by requiring the filename to match a strict
    safe-character pattern AND by resolving the final path and confirming it
    stays inside INPUT_IMAGES_DIR.
    """
    if not _SAFE_FILENAME.match(filename):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_filename", "message": "Filename contains disallowed characters."},
        )

    candidate = (INPUT_IMAGES_DIR / filename).resolve()
    try:
        # Python 3.9+: Path.is_relative_to handles the containment check cleanly.
        if not candidate.is_relative_to(INPUT_IMAGES_DIR.resolve()):
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_filename", "message": "Filename resolves outside the input_images/ folder."},
            )
    except AttributeError:
        # Belt-and-suspenders for older Pythons; we target 3.12 so this is dead code.
        if not str(candidate).startswith(str(INPUT_IMAGES_DIR.resolve())):
            raise HTTPException(status_code=400, detail={"error": "invalid_filename", "message": "Bad path."}) from None

    if not candidate.is_file():
        raise HTTPException(
            status_code=404,
            detail={"error": "image_not_found", "message": f"No image named '{filename}' in input_images/."},
        )

    return FileResponse(candidate)


# --- GET /api/v1/inbound/exports/{filename} ----------------------------------
#
# Streams a written CSV back to the browser as a download. The export POST
# still writes to the Railway volume at /data/exports/ (durable record); this
# endpoint is what lets the UI trigger a "save to Downloads" in Chrome.

# CSV filenames are produced by us (listings_<UTC>.csv), but the input still
# comes through the URL so we apply the same safe-filename + containment check
# we use for /inbound/images/ to defend against path traversal.
_SAFE_CSV_FILENAME = re.compile(r"^[A-Za-z0-9._-]+\.csv$")


@router.get("/inbound/exports/{filename}")
def download_inbound_export(filename: str):
    """Stream one CSV from exports/ as an attachment download."""
    if not _SAFE_CSV_FILENAME.match(filename):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_filename", "message": "Filename must be a simple .csv name."},
        )

    candidate = (EXPORTS_DIR / filename).resolve()
    if not candidate.is_relative_to(EXPORTS_DIR.resolve()):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_filename", "message": "Filename resolves outside the exports/ folder."},
        )
    if not candidate.is_file():
        raise HTTPException(
            status_code=404,
            detail={"error": "export_not_found", "message": f"No export named '{filename}'."},
        )

    # FileResponse with `filename=` adds Content-Disposition: attachment for us.
    return FileResponse(candidate, media_type="text/csv", filename=filename)


# --- DELETE /api/v1/inbound/data ---------------------------------------------
#
# Full reset for the hosted POC: wipes every file the app has ever written to
# the persistent volume (input_images/, inbound/, exports/). The directories
# themselves are kept so the app keeps writing to the same paths after the
# clear. No DB rows to clean up — the active pipeline is filesystem-only.
#
# This is destructive and irreversible. The frontend gates it behind a
# window.confirm, but we don't add server-side guards (no auth, no soft-
# delete) because the whole app is gated by Cloudflare Access in hosted mode.

class ClearDataResponse(BaseModel):
    """Counts of files removed from each managed directory, plus the total
    number of database rows wiped (jobs, review state, audit, export records)."""
    input_images_deleted: int
    inbound_deleted: int
    exports_deleted: int
    db_rows_deleted: int


def _purge_dir_contents(directory: Path) -> int:
    """
    Delete every direct child file in `directory`. Returns the count removed.
    Skips subdirectories defensively (none should exist today, but if they
    appear later we don't want to recurse into something unexpected).
    """
    if not directory.exists():
        return 0
    removed = 0
    for entry in directory.iterdir():
        if entry.is_file():
            entry.unlink()
            removed += 1
    return removed


@router.delete("/inbound/data", response_model=ClearDataResponse)
def clear_all_data() -> ClearDataResponse:
    """Wipe input_images/, inbound/, exports/ on the volume AND every SQLite
    table (jobs, review state, audit trail, export records). Full reset."""
    db_counts = inbound_store.clear_all_tables()
    return ClearDataResponse(
        input_images_deleted=_purge_dir_contents(INPUT_IMAGES_DIR),
        inbound_deleted=_purge_dir_contents(INBOUND_DIR),
        exports_deleted=_purge_dir_contents(EXPORTS_DIR),
        db_rows_deleted=sum(db_counts.values()),
    )


# --- Extraction job tracking (POST /extract + GET /extract/{job_id}) ---------
#
# State is in-memory — a dict keyed by job_id. Good enough for a POC: a server
# restart loses in-flight progress, but on-disk JSONs are the source of truth
# for anything that actually finished. If we later need durability, move this
# to SQLite or a small JSON file and keep the same shape.

# Valid values for ExtractionJob.status. "queued" is the brief moment between
# POST /extract returning and the worker thread picking up.
ExtractionStatus = Literal["queued", "running", "completed", "failed"]


class ExtractionImageStatus(BaseModel):
    """One image's outcome within a job — populated as the run progresses."""
    image_name: str
    success: bool
    duration_ms: int
    api_error: str | None = None
    schema_valid: bool
    schema_error: str | None = None


class ExtractionJob(BaseModel):
    """Full state of one extraction run. Returned by the poll endpoint."""
    job_id: str
    status: ExtractionStatus
    total: int = Field(..., description="Total images to process (0 until discovery)")
    completed: int = Field(0, description="Images finished (success + failure)")
    succeeded: int = 0
    failed: int = 0
    current_image: str | None = Field(None, description="Name of the image currently being processed, if any")
    started_at_utc: str
    finished_at_utc: str | None = None
    model: str | None = None
    # Fatal error that stopped the entire run (distinct from per-image api_error).
    error: str | None = None
    # Per-image results, appended as each image finishes.
    results: list[ExtractionImageStatus] = Field(default_factory=list)


class ExtractStartResponse(BaseModel):
    job_id: str
    status: ExtractionStatus
    total: int = Field(..., description="Image count discovered up front (0 if discovery failed)")


class ExtractStartRequest(BaseModel):
    """
    Body for POST /inbound/extract. Both fields are optional so older clients
    (and the CLI-style "just run it" use case) keep working with `POST` + `{}`.

    batch_name: freeform label the Prep screen captured. Written into every
      resulting artifact's `meta.batch_name` so Recent Batches can group them.
    """
    batch_name: str | None = Field(
        None,
        description="Human-entered label for this run (e.g. 'Nikon Z9 body + accessories').",
        max_length=120,
    )


def _now_iso() -> str:
    """Seconds-precision UTC ISO8601 timestamp, matches other endpoints."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.post("/inbound/extract", response_model=ExtractStartResponse, status_code=202)
def start_extraction(body: ExtractStartRequest | None = None) -> ExtractStartResponse:
    """
    Kick off a Gemini extraction over every image in input_images/.

    Synchronous steps (fast): discover images, register a job, spawn a thread.
    Async work (the thread): call Gemini per image, update job state, write
    JSONs to inbound/. The client polls GET /inbound/extract/{job_id} to
    render progress.

    Re-run semantics: `purge_existing=True` wipes inbound/extraction_*.json
    before writing the new batch, so the UI reflects only the latest run.
    (Sergey's call — seamless E2E wants a clean slate each time.)

    Batch metadata: the Prep screen submits a batch_name. The timestamp we
    generate here becomes the batch's stable id (also URL-safe). Both land
    in every produced artifact's `meta` block, so Recent Batches can
    reconstruct the grouping without a DB.
    """
    # 1. Discover images synchronously so the client learns "total" immediately.
    try:
        images = discover_images(INPUT_IMAGES_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "input_folder_missing", "message": str(exc)},
        ) from exc
    if not images:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "no_images_found",
                "message": f"No image files in {INPUT_IMAGES_DIR}. Drop photos there and retry.",
            },
        )

    # 2. Register a job in the queued state so the client can poll immediately.
    #    The batch_started_at_utc is also the batch_id — stable across artifacts
    #    from this run so Recent Batches can group them back together.
    started_at_utc = _now_iso()
    job_id = uuid.uuid4().hex
    # Normalize batch name: trim whitespace; treat empty as None.
    batch_name = (body.batch_name.strip() if body and body.batch_name else None) or None
    try:
        # Only one extraction may run at a time: the run purges inbound/
        # before writing, so two concurrent runs would delete each other's
        # artifacts and double the Gemini spend. The store enforces the
        # check-and-register atomically (BEGIN IMMEDIATE), which holds even
        # across multiple uvicorn worker processes.
        inbound_store.create_job(
            job_id=job_id,
            total=len(images),
            started_at_utc=started_at_utc,
            batch_name=batch_name,
        )
    except inbound_store.ActiveJobError as exc:
        active = exc.active_job
        raise HTTPException(
            status_code=409,
            detail={
                "error": "extraction_already_running",
                "message": (
                    "An extraction is already in progress "
                    f"({active['completed']} of {active['total']} images done). "
                    "Wait for it to finish before starting another."
                ),
            },
        ) from exc

    # 3. Spawn a daemon thread — we don't await it, FastAPI returns 202 now.
    #    Daemon=True so a dev-server Ctrl+C doesn't hang on an in-flight run.
    thread = threading.Thread(
        target=_run_extraction_thread,
        args=(job_id, batch_name, started_at_utc),
        name=f"extraction-{job_id[:8]}",
        daemon=True,
    )
    thread.start()

    return ExtractStartResponse(job_id=job_id, status="queued", total=len(images))


@router.get("/inbound/extract/{job_id}", response_model=ExtractionJob)
def get_extraction_status(job_id: str) -> ExtractionJob:
    """Return the current state of an extraction job. 404 if unknown.

    Reads from SQLite, so polling works no matter which uvicorn worker
    handles the request, and a finished job's record survives restarts.
    The store also flips orphaned jobs (server died mid-run, heartbeat went
    stale) to 'failed' on read, so the UI never spins forever.
    """
    job = inbound_store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"No extraction job with id {job_id}."},
        )
    return ExtractionJob(**job)


def _run_extraction_thread(
    job_id: str,
    batch_name: str | None,
    batch_started_at_utc: str,
) -> None:
    """
    Worker entrypoint — runs in a daemon thread spawned by start_extraction.
    Calls the shared extraction service with progress callbacks that feed
    back into the job registry. Catches any exception so a crash here still
    transitions the job to 'failed' instead of leaving it 'running' forever.
    """
    # Flip queued → running. Worker is now alive.
    inbound_store.update_job(job_id, status="running")

    # The run is about to purge inbound/*.json (purge_existing=True below),
    # which orphans any saved review rows — their artifacts are gone. Clear
    # them now so the Review screen starts fresh with the new batch. The
    # append-only audit trail is deliberately kept.
    inbound_store.delete_all_reviews()

    def _on_image_start(index: int, total: int, image_name: str) -> None:
        # Record what we're about to call Gemini for, and ensure 'total' is
        # right. (We set it at registration too — this is belt-and-suspenders
        # in case the folder changed between discovery and execution.)
        inbound_store.update_job(job_id, current_image=image_name, total=total)

    def _on_image_done(index: int, total: int, result: ImageResult) -> None:
        # One transaction: insert the per-image row and bump the job counters.
        # current_image clears automatically when the last image lands —
        # mid-run it always points at *some* in-flight image (images run in
        # parallel under EXTRACTION_CONCURRENCY), which is what the progress
        # banner wants.
        inbound_store.record_image_result(
            job_id=job_id,
            image_name=result.image_name,
            success=result.success,
            duration_ms=result.duration_ms,
            api_error=result.api_error,
            schema_valid=result.schema_valid,
            schema_error=result.schema_error,
        )

    try:
        summary = run_extraction(
            input_folder=INPUT_IMAGES_DIR,
            output_folder=INBOUND_DIR,
            purge_existing=True,
            on_image_start=_on_image_start,
            on_image_done=_on_image_done,
            batch_name=batch_name,
            batch_started_at_utc=batch_started_at_utc,
        )
    except (GeminiClientError, FileNotFoundError, ImportError) as exc:
        # Fatal run-level failure — we never got far enough to produce
        # per-image results.
        inbound_store.update_job(
            job_id,
            status="failed",
            error=str(exc),
            finished_at_utc=_now_iso(),
            current_image=None,
        )
        return
    except Exception as exc:  # pragma: no cover — last-resort safety net
        inbound_store.update_job(
            job_id,
            status="failed",
            error=f"unexpected error: {exc!r}",
            finished_at_utc=_now_iso(),
            current_image=None,
        )
        return

    # Happy path: flip to completed and stamp the finish time + model.
    inbound_store.update_job(
        job_id,
        status="completed",
        finished_at_utc=_now_iso(),
        model=summary.model,
        current_image=None,
    )


# --- Review endpoints (Phase 7A — replaces browser localStorage) ---------------

# extraction_ids are artifact filename stems (extraction_<UTC>__<image-stem>),
# so the same safe-character rule used for image filenames applies.
def _require_artifact(extraction_id: str) -> None:
    """400/404 unless `extraction_id` names a real artifact in inbound/.

    Keeps junk rows out of review_items: you can only review a card that
    actually exists on disk right now.
    """
    if not _SAFE_FILENAME.match(extraction_id):
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_extraction_id", "message": "Extraction id contains disallowed characters."},
        )
    if not (INBOUND_DIR / f"{extraction_id}.json").is_file():
        raise HTTPException(
            status_code=404,
            detail={"error": "extraction_not_found", "message": f"No extraction artifact named '{extraction_id}'."},
        )


@router.put("/inbound/review/{extraction_id}", response_model=ReviewState)
def save_review(extraction_id: str, body: ReviewSaveRequest, request: Request) -> ReviewState:
    """Persist a card's edited content server-side (audit event: 'edited')."""
    _require_artifact(extraction_id)
    stored = inbound_store.save_review(
        extraction_id=extraction_id,
        edited_response=body.response,
        edited_pricing=body.pricing,
        actor=_actor(request),
    )
    return ReviewState(**stored)


@router.post("/inbound/review/{extraction_id}/approve", response_model=ReviewState)
def approve_review(extraction_id: str, body: ApproveRequest, request: Request) -> ReviewState:
    """Mark a card approved, snapshotting the content the reviewer saw."""
    _require_artifact(extraction_id)
    try:
        stored = inbound_store.set_approval(
            extraction_id=extraction_id,
            approved=True,
            actor=_actor(request),
            edited_response=body.response,
            edited_pricing=body.pricing,
        )
    except ValueError as exc:
        # No stored row AND no content in the body — nothing to snapshot.
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_content", "message": str(exc)},
        ) from exc
    return ReviewState(**stored)


@router.delete("/inbound/review/{extraction_id}/approve", response_model=ReviewState)
def unapprove_review(extraction_id: str, request: Request) -> ReviewState:
    """Remove a card's approval (content is left untouched)."""
    _require_artifact(extraction_id)
    try:
        stored = inbound_store.set_approval(
            extraction_id=extraction_id,
            approved=False,
            actor=_actor(request),
        )
    except ValueError as exc:
        # Un-approving a card that has no review row at all.
        raise HTTPException(
            status_code=404,
            detail={"error": "review_not_found", "message": f"No review state for '{extraction_id}'."},
        ) from exc
    return ReviewState(**stored)


# --- POST /api/v1/inbound/export ---------------------------------------------

# Column order — copied verbatim from contracts/csv_export_schema.md so the
# downstream CSV format stays stable as we evolve the in-memory shape.
CSV_COLUMNS = [
    "job_number",
    "item_category",
    "product_name",
    "brand",
    "model",
    "product_family",
    "variant",
    "mount_type",
    "serial_number_visible",
    "condition_summary",
    "short_title",
    "description_text",
    "visible_wear_notes",
    "key_selling_points",
    "sensor_format",
    "megapixels",
    "lens_mount",
    "focal_length",
    "aperture",
    "iso_range",
    "shutter_range",
    "video_capabilities",
    "storage_media",
    "connectivity",
    "weight_grams",
    "other_specifications_json",
    "included_accessories_text",
    "inferred_accessories_text",
    "missing_typical_accessories_text",
    # --- Pricing columns (Phase 5 enrichment). Blank on rows that were never
    #     priced. Order mirrors the pricing schema top-to-bottom: recommended
    #     value first, platform observations next, narrative + sources last.
    "fair_price",
    "deal_threshold",
    "ebay_sold_avg",
    "mpb_retail",
    "keh_retail",
    "bh_used",
    "market_summary",
    "pricing_sources_json",
    "pricing_fetched_at_utc",
    # --- Provenance (always last). ---
    "approved_at",
    "approved_by",
    "exported_at",
]

# Long-form fields that get newlines flattened to single spaces per CSV spec.
_FLATTEN_NEWLINE_FIELDS = {
    "description_text",
    "visible_wear_notes",
    "key_selling_points",
    "video_capabilities",
    "included_accessories_text",
    "inferred_accessories_text",
    "missing_typical_accessories_text",
    # market_summary is a short two-sentence blurb but Gemini sometimes breaks
    # it across lines; flatten so the CSV stays single-line per row.
    "market_summary",
}


@router.post("/inbound/export", response_model=ExportResponse, status_code=201)
def export_inbound(body: ExportRequest, request: Request) -> ExportResponse:
    """
    Write one CSV row per approved card to exports/listings_<UTC-timestamp>.csv.

    Phase 7A approval gate: the client sends only extraction_ids. Content
    comes from the server-stored review snapshots, and every id must already
    be approved — an unapproved id fails the whole request with 400 (listing
    the offenders) rather than silently exporting unreviewed content. Each
    export is recorded in the exports table plus an 'exported' audit event
    per card.
    """
    if not body.extraction_ids:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_items", "message": "Export request must include at least one extraction id."},
        )

    # De-duplicate while preserving order so a glitchy client can't write
    # the same row twice.
    requested_ids = list(dict.fromkeys(body.extraction_ids))

    approved = inbound_store.get_approved_reviews(requested_ids)
    unapproved = [eid for eid in requested_ids if eid not in approved]
    if unapproved:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "not_approved",
                "message": (
                    "These items are not approved and cannot be exported: "
                    + ", ".join(unapproved)
                ),
            },
        )

    exported_at = datetime.now(timezone.utc)
    exported_at_iso = exported_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    exported_at_filename = exported_at.strftime("%Y-%m-%dT%H-%M-%SZ")

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_filename = f"listings_{exported_at_filename}.csv"
    csv_path = EXPORTS_DIR / csv_filename

    # Build the CSV in-memory first so a write failure doesn't leave a half-file.
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()

    for extraction_id in requested_ids:
        snapshot = approved[extraction_id]
        row = _build_csv_row(
            extraction_id=extraction_id,
            response=snapshot["edited_response"],
            pricing=snapshot["edited_pricing"],
            # Real provenance now — who approved it and when, not "whoever
            # clicked export at export time".
            approved_at=snapshot["approved_at_utc"],
            approved_by=snapshot["approved_by"],
            exported_at_iso=exported_at_iso,
        )
        writer.writerow(row)

    csv_path.write_text(buffer.getvalue(), encoding="utf-8", newline="")

    # Provenance: which CSV, how many rows, which cards, who triggered it.
    inbound_store.record_export(
        csv_filename=csv_filename,
        row_count=len(requested_ids),
        exported_at_utc=exported_at_iso,
        extraction_ids=requested_ids,
        actor=_actor(request),
    )

    return ExportResponse(
        # Report the path relative to APP_DATA_PATH so it stays meaningful in
        # both local dev (data dir = repo root) and hosted (data dir = /data).
        csv_path=str(csv_path.relative_to(APP_DATA_PATH)).replace("\\", "/"),
        csv_filename=csv_filename,
        row_count=len(requested_ids),
        exported_at_utc=exported_at_iso,
    )


# --- CSV row assembly --------------------------------------------------------

def _build_csv_row(
    extraction_id: str,
    response: dict | None,
    pricing: dict | None,
    approved_at: str | None,
    approved_by: str | None,
    exported_at_iso: str,
) -> dict:
    """
    Flatten one approved review snapshot (the nested Gemini shape, possibly
    human-edited) into the flat column dict the CSV writer expects. Applies
    the spec's transformation rules in passing (trim, line-break flatten,
    blank-normalize).
    """
    response = response or {}
    overview = response.get("overview") or {}
    description = response.get("description") or {}
    specs = response.get("specifications") or {}
    accessories = response.get("accessories") or {}

    other_specs = specs.get("other_specifications")
    other_specs_json = (
        json.dumps(other_specs, separators=(",", ":"), ensure_ascii=False)
        if isinstance(other_specs, dict) and other_specs
        else ""
    )

    # --- Pricing flattening ---
    # The pricing block is optional; when absent every pricing column renders
    # blank (that's the point — mixed-priced/unpriced batches are normal).
    pricing = pricing or {}
    pricing_platforms = pricing.get("pricing") or {}
    pricing_valuation = pricing.get("market_valuation") or {}
    pricing_sources = pricing.get("sources") or []

    # Sources → compact JSON string so the CSV stays one cell. Matches how
    # other_specifications_json is handled — this is a JSON column inside CSV.
    pricing_sources_json = (
        json.dumps(pricing_sources, separators=(",", ":"), ensure_ascii=False)
        if isinstance(pricing_sources, list) and pricing_sources
        else ""
    )

    raw_row: dict[str, object] = {
        # Identity — extraction_id is our stand-in for job_number in this flow.
        "job_number": extraction_id,
        "item_category": "",  # not modeled per-image yet
        # Overview
        "product_name": overview.get("product_name"),
        "brand": overview.get("brand"),
        "model": overview.get("model"),
        "product_family": overview.get("product_family"),
        "variant": overview.get("variant"),
        "mount_type": overview.get("mount_type"),
        "serial_number_visible": overview.get("serial_number_visible"),
        "condition_summary": overview.get("condition_summary"),
        # Description
        "short_title": description.get("short_title"),
        "description_text": description.get("description_text"),
        "visible_wear_notes": description.get("visible_wear_notes"),
        "key_selling_points": description.get("key_selling_points"),
        # Specifications
        "sensor_format": specs.get("sensor_format"),
        "megapixels": specs.get("megapixels"),
        "lens_mount": specs.get("lens_mount"),
        "focal_length": specs.get("focal_length"),
        "aperture": specs.get("aperture"),
        "iso_range": specs.get("iso_range"),
        "shutter_range": specs.get("shutter_range"),
        "video_capabilities": specs.get("video_capabilities"),
        "storage_media": specs.get("storage_media"),
        "connectivity": specs.get("connectivity"),
        "weight_grams": specs.get("weight_grams"),
        "other_specifications_json": other_specs_json,
        # Accessories
        "included_accessories_text": accessories.get("included_accessories_text"),
        "inferred_accessories_text": accessories.get("inferred_accessories_text"),
        "missing_typical_accessories_text": accessories.get("missing_typical_accessories_text"),
        # Pricing
        "fair_price": pricing_valuation.get("fair_price"),
        "deal_threshold": pricing_valuation.get("deal_threshold"),
        "ebay_sold_avg": pricing_platforms.get("ebay_sold_avg"),
        "mpb_retail": pricing_platforms.get("mpb_retail"),
        "keh_retail": pricing_platforms.get("keh_retail"),
        "bh_used": pricing_platforms.get("bh_used"),
        "market_summary": pricing.get("market_summary"),
        "pricing_sources_json": pricing_sources_json,
        "pricing_fetched_at_utc": pricing.get("fetched_at_utc"),
        # Provenance — real approval data from the review row, not export time.
        "approved_at": approved_at or "",
        "approved_by": approved_by or "",
        "exported_at": exported_at_iso,
    }

    # Apply the spec's normalization rules to every value.
    return {col: _normalize_cell(col, raw_row.get(col)) for col in CSV_COLUMNS}


# Leading characters Excel / Sheets / LibreOffice interpret as a formula
# trigger. Cell text starting with one of these executes when the CSV is
# opened — and our cell text comes from a web-grounded LLM, so we don't
# control it. Prefixing a single quote is the standard OWASP mitigation:
# spreadsheets render the value as plain text (the quote itself is hidden
# in Excel; tools reading the CSV programmatically see a leading ').
_FORMULA_TRIGGER_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _escape_spreadsheet_formula(text: str) -> str:
    """Neutralize CSV formula injection by prefixing risky leading chars."""
    if text.startswith(_FORMULA_TRIGGER_CHARS):
        return "'" + text
    return text


def _normalize_cell(column: str, value: object) -> str:
    """
    Apply the CSV spec's transformation rules:
      - None / empty / whitespace-only → blank
      - Long-form fields get newlines flattened to single spaces
      - Numbers serialize as plain decimal strings
      - Everything else gets trimmed
      - Text starting with a formula trigger char (= + - @ tab CR) gets a
        leading ' so spreadsheet apps treat it as text, never as a formula.
        Real numbers (int/float) skip this — a negative price is not a formula.
    """
    if value is None:
        return ""

    if isinstance(value, bool):
        # bool is a subclass of int — handle explicitly so True doesn't print "1".
        return "true" if value else "false"

    if isinstance(value, (int, float)):
        # Plain decimal string, no scientific notation, no units. Numeric
        # values are safe by construction — no formula escaping needed.
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    text = str(value).strip()
    if not text:
        return ""

    if column in _FLATTEN_NEWLINE_FIELDS:
        # Normalize CRLF/CR → LF, then flatten LF → single space, then collapse runs.
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
        text = re.sub(r"\s+", " ", text).strip()

    return _escape_spreadsheet_formula(text)
