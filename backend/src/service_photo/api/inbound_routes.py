"""
Inbound-folder routes — filesystem-backed, no database.

These endpoints serve the new UI flow where each photo is its own product
listing. The Gemini extraction CLI (scripts/run_gemini_extraction.py) drops
one JSON per image into <repo>/inbound/. The UI reads them via these routes,
lets a human edit + approve each card, and finally exports an approved
selection to a single CSV in <repo>/exports/.

This intentionally bypasses the existing /jobs DB pipeline. We may unify them
later, but for now keep them isolated so changes here don't break the 47/47
backend test suite.

Endpoints:
  GET  /api/v1/inbound                       — list every extraction artifact
  GET  /api/v1/inbound/input-images          — list files in input_images/ (for Prep)
  GET  /api/v1/inbound/images/{filename}     — serve an image by filename
  GET  /api/v1/inbound/batches               — group artifacts by batch
  POST /api/v1/inbound/extract               — kick off Gemini over input_images/
  GET  /api/v1/inbound/extract/{job_id}      — poll extraction progress/status
  POST /api/v1/inbound/export                — write an approved-set CSV

Filesystem layout (all paths relative to the repo root):
  inbound/    — one extraction_<timestamp>__<image-stem>.json per image
  input_images/ — the source photos those extractions came from
  exports/    — written CSVs land here (created on demand, gitignored)
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

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

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


# --- Schemas -----------------------------------------------------------------

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


class ExportItem(BaseModel):
    """One card's approved + edited content, ready for CSV serialization."""
    extraction_id: str
    image_files: list[str]
    response: dict
    # Optional pricing block. Included when the user has run Phase 5 enrichment
    # for this card and (possibly) edited the numbers. Absence means the
    # pricing columns on this row will be blank, not an error.
    pricing: dict | None = None


class ExportRequest(BaseModel):
    items: list[ExportItem]
    approved_by: str | None = None


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
    - Per-file size capped at _MAX_UPLOAD_BYTES.
    - On filename collision, append `-1`, `-2`, … before the suffix.
    """
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
            raise HTTPException(status_code=400, detail={"error": "invalid_filename", "message": "Bad path."})

    if not candidate.is_file():
        raise HTTPException(
            status_code=404,
            detail={"error": "image_not_found", "message": f"No image named '{filename}' in input_images/."},
        )

    return FileResponse(candidate)


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


# Guarded in-memory job registry. A lock protects reads and writes so the
# polling endpoint never sees a half-updated state (Python dict ops are
# mostly atomic, but we mutate multiple fields per tick).
_jobs: dict[str, ExtractionJob] = {}
_jobs_lock = threading.Lock()


def _now_iso() -> str:
    """Seconds-precision UTC ISO8601 timestamp, matches other endpoints."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _mutate_job(job_id: str, mutator) -> None:
    """
    Apply `mutator(job)` to the registered job under the lock. If the job
    is missing we silently no-op — should never happen because we only call
    this from the worker thread we just spawned.
    """
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        mutator(job)


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
        )
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
    job = ExtractionJob(
        job_id=job_id,
        status="queued",
        total=len(images),
        started_at_utc=started_at_utc,
    )
    with _jobs_lock:
        _jobs[job_id] = job

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
    """Return the current state of an extraction job. 404 if unknown."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"No extraction job with id {job_id}."},
        )
    # Return a copy so later mutations by the worker thread don't surprise us
    # mid-serialization. Pydantic v2 copy is deep enough for our field types.
    return job.model_copy(deep=True)


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
    _mutate_job(job_id, lambda j: _set(j, status="running"))

    def _on_image_start(index: int, total: int, image_name: str) -> None:
        # Record what we're about to call Gemini for, and ensure 'total' is
        # right. (We set it at registration too — this is belt-and-suspenders
        # in case the folder changed between discovery and execution.)
        _mutate_job(job_id, lambda j: _set(j, current_image=image_name, total=total))

    def _on_image_done(index: int, total: int, result: ImageResult) -> None:
        def apply(j: ExtractionJob) -> None:
            j.results.append(ExtractionImageStatus(
                image_name=result.image_name,
                success=result.success,
                duration_ms=result.duration_ms,
                api_error=result.api_error,
                schema_valid=result.schema_valid,
                schema_error=result.schema_error,
            ))
            j.completed += 1
            if result.success:
                j.succeeded += 1
            else:
                j.failed += 1
            # Clear current_image between images so the UI doesn't show a
            # stale label during the brief gap before the next call starts.
            j.current_image = None
        _mutate_job(job_id, apply)

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
        # Fatal run-level failure — we never got far enough to produce per-image results.
        _mutate_job(
            job_id,
            lambda j: _set(j, status="failed", error=str(exc), finished_at_utc=_now_iso(), current_image=None),
        )
        return
    except Exception as exc:  # pragma: no cover — last-resort safety net
        _mutate_job(
            job_id,
            lambda j: _set(
                j,
                status="failed",
                error=f"unexpected error: {exc!r}",
                finished_at_utc=_now_iso(),
                current_image=None,
            ),
        )
        return

    # Happy path: flip to completed and stamp the finish time + model.
    _mutate_job(
        job_id,
        lambda j: _set(
            j,
            status="completed",
            finished_at_utc=_now_iso(),
            model=summary.model,
            current_image=None,
        ),
    )


def _set(obj, **fields) -> None:
    """
    Tiny helper: set several attributes on a pydantic model instance in one
    call, so the lambdas passed to _mutate_job stay readable.
    """
    for key, value in fields.items():
        setattr(obj, key, value)


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
def export_inbound(body: ExportRequest) -> ExportResponse:
    """
    Write one CSV row per submitted item to exports/listings_<UTC-timestamp>.csv.

    Each item carries its (possibly edited) Gemini response. We flatten the
    nested response structure into the columns from csv_export_schema.md.
    Fields that don't exist in our per-image artifact (job_number, item_category,
    approved_by) are filled from request metadata or left blank.

    No DB writes happen — this is the POC's "save the approved set" action.
    """
    if not body.items:
        raise HTTPException(
            status_code=400,
            detail={"error": "no_items", "message": "Export request must include at least one item."},
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

    for item in body.items:
        row = _build_csv_row(
            item=item,
            approved_by=body.approved_by,
            exported_at_iso=exported_at_iso,
        )
        writer.writerow(row)

    csv_path.write_text(buffer.getvalue(), encoding="utf-8", newline="")

    return ExportResponse(
        # Report the path relative to APP_DATA_PATH so it stays meaningful in
        # both local dev (data dir = repo root) and hosted (data dir = /data).
        csv_path=str(csv_path.relative_to(APP_DATA_PATH)).replace("\\", "/"),
        csv_filename=csv_filename,
        row_count=len(body.items),
        exported_at_utc=exported_at_iso,
    )


# --- CSV row assembly --------------------------------------------------------

def _build_csv_row(item: ExportItem, approved_by: str | None, exported_at_iso: str) -> dict:
    """
    Flatten one ExportItem.response (the nested Gemini shape) into the flat
    column dict the CSV writer expects. Applies the spec's transformation rules
    in passing (trim, line-break flatten, blank-normalize).
    """
    response = item.response or {}
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
    pricing = item.pricing or {}
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
        "job_number": item.extraction_id,
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
        # Provenance
        "approved_at": exported_at_iso,
        "approved_by": approved_by or "",
        "exported_at": exported_at_iso,
    }

    # Apply the spec's normalization rules to every value.
    return {col: _normalize_cell(col, raw_row.get(col)) for col in CSV_COLUMNS}


def _normalize_cell(column: str, value: object) -> str:
    """
    Apply the CSV spec's transformation rules:
      - None / empty / whitespace-only → blank
      - Long-form fields get newlines flattened to single spaces
      - Numbers serialize as plain decimal strings
      - Everything else gets trimmed
    """
    if value is None:
        return ""

    if isinstance(value, bool):
        # bool is a subclass of int — handle explicitly so True doesn't print "1".
        return "true" if value else "false"

    if isinstance(value, (int, float)):
        # Plain decimal string, no scientific notation, no units.
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

    return text
