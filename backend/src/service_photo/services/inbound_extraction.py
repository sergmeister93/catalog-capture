"""
Per-image Gemini extraction service.

Shared between the CLI script (scripts/run_gemini_extraction.py) and the
HTTP endpoint (POST /api/v1/inbound/extract). The logic is identical —
walk a folder of photos, make one Gemini call per image, write one JSON
per image under inbound/. Progress is emitted via optional callbacks so
the CLI can print and the HTTP endpoint can update shared job state.

Inputs (run_extraction):
    input_folder    — folder to scan for images (e.g. <repo>/input_images)
    output_folder   — where per-image JSONs are written (e.g. <repo>/inbound)
    model           — optional Gemini model id; None uses env/default
    purge_existing  — if True, delete existing extraction_*.json before the
                      run so re-runs fully overwrite prior state
    on_image_start  — optional (index, total, image_name) hook fired before
                      each Gemini call
    on_image_done   — optional (index, total, ImageResult) hook fired after
                      each image finishes (success or failure)

Outputs:
    ExtractionSummary (total counts + per-image results). Side effect: one
    JSON file per image in output_folder, matching the shape the Inbound
    UI expects (meta + response blocks).
"""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# These imports are fine at module scope because the backend package always
# has its deps installed (pyproject.toml). The CLI script sets sys.path
# before importing us, so these resolve there too.
from service_photo.integrations.gemini_interface import GeminiClientError
from service_photo.integrations.real_gemini import RealGeminiClient
from service_photo.core.config import settings

# --- Constants ---------------------------------------------------------------

# Repo root relative to this file: parents[0]=services, [1]=service_photo,
# [2]=src, [3]=backend, [4]=repo root. Only used as a fallback for SCHEMA_PATH
# in local dev — in a hosted container this layout doesn't exist.
REPO_ROOT = Path(__file__).resolve().parents[4]

# Prompts ship inside the installed package, so resolve relative to this file.
# parents[1] = service_photo (the package root).
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "listing_extraction_v1.md"


def _find_schema_path() -> Path:
    """Locate contracts/gemini_response_schema.json by walking up the parent
    tree from this file. Works in local dev (file lives at <repo>/contracts/)
    and in the container (Dockerfile drops a copy at /contracts/)."""
    current = Path(__file__).resolve()
    for _ in range(10):
        candidate = current.parent / "contracts" / "gemini_response_schema.json"
        if candidate.exists():
            return candidate
        current = current.parent
    # Fall back to the original repo-relative guess so the error message is
    # informative if the schema is genuinely missing.
    return REPO_ROOT / "contracts" / "gemini_response_schema.json"


SCHEMA_PATH = _find_schema_path()

# Image file extensions we pick up when scanning the input folder. Matches
# what the Gemini client supports.
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

# Filename glob for artifacts we own in the output folder (used when purging).
ARTIFACT_GLOB = "extraction_*.json"


# --- Result shapes -----------------------------------------------------------

@dataclass
class ImageResult:
    """Outcome of one image's Gemini call + JSON write."""
    image_name: str
    out_path: Path
    success: bool
    duration_ms: int
    api_error: str | None
    schema_valid: bool
    schema_error: str | None


@dataclass
class ExtractionSummary:
    """Aggregate outcome of a run over one folder."""
    total: int
    succeeded: int
    failed: int
    run_timestamp: str
    model: str
    results: list[ImageResult] = field(default_factory=list)


# --- Progress callback types -------------------------------------------------

# (index_1_based, total, image_name) -> None
OnImageStart = Callable[[int, int, str], None]
# (index_1_based, total, result) -> None
OnImageDone = Callable[[int, int, ImageResult], None]


# --- Public API --------------------------------------------------------------

def discover_images(folder: Path) -> list[Path]:
    """
    Return image files in `folder`, sorted by filename. Deterministic order
    matters so progress reporting ("3 of 5") lines up with what the user sees.
    Skips dotfiles and non-image extensions.
    """
    if not folder.is_dir():
        raise FileNotFoundError(f"Input folder does not exist: {folder}")

    files = [
        p for p in folder.iterdir()
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() in IMAGE_SUFFIXES
    ]
    files.sort(key=lambda p: p.name)
    return files


def load_prompt() -> str:
    """Read the extraction prompt template from the canonical location."""
    if not PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Prompt template not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def run_extraction(
    input_folder: Path,
    output_folder: Path,
    model: Optional[str] = None,
    purge_existing: bool = False,
    on_image_start: Optional[OnImageStart] = None,
    on_image_done: Optional[OnImageDone] = None,
    batch_name: Optional[str] = None,
    batch_started_at_utc: Optional[str] = None,
) -> ExtractionSummary:
    """
    Run Gemini extraction over every image in `input_folder`. Writes one
    JSON per image to `output_folder`. Returns a summary.

    Partial success is still useful — one image failing does not abort the
    run. Failures are recorded in `meta.api_error` on their own JSON and
    counted in the summary.

    Batch metadata (`batch_name`, `batch_started_at_utc`) is stamped into each
    per-image artifact's `meta` block so the Recent Batches screen can group
    artifacts back into the run that produced them. The filesystem is the
    source of truth — there's no separate batches table.
    """
    images = discover_images(input_folder)
    if not images:
        raise FileNotFoundError(
            f"No image files found in {input_folder} "
            f"(looked for: {sorted(IMAGE_SUFFIXES)})"
        )

    prompt = load_prompt()

    # Instantiate once, reuse for every image. Any config/auth error fails fast.
    client = RealGeminiClient(model_name=model)

    output_folder.mkdir(parents=True, exist_ok=True)

    # Overwrite semantics: wipe prior artifacts so a re-run produces a clean
    # set of JSONs rather than accumulating runs side-by-side.
    if purge_existing:
        for old in output_folder.glob(ARTIFACT_GLOB):
            try:
                old.unlink()
            except OSError:
                # If the OS can't delete it (file in use), continue — worst
                # case the UI shows a stale card until the next run.
                pass

    run_timestamp = _utc_timestamp_for_filename()
    summary = ExtractionSummary(
        total=len(images),
        succeeded=0,
        failed=0,
        run_timestamp=run_timestamp,
        model=client.model_name,
    )

    # Process images in parallel — each is an independent Gemini call, so
    # concurrency divides the batch's wall-clock time. Bounded by
    # EXTRACTION_CONCURRENCY to stay under Gemini rate limits; 1 reproduces
    # the original strictly-sequential behavior.
    #
    # Thread-safety notes:
    #   - Each task writes its own artifact file (unique name per image), so
    #     there is no shared file state between tasks.
    #   - summary counters and the results list are only touched under
    #     `summary_lock`.
    #   - Callbacks fire from worker threads. The HTTP endpoint's callbacks
    #     already serialize through the _jobs lock; the CLI's print callbacks
    #     are fine because print() is atomic enough for progress lines.
    concurrency = max(1, settings.EXTRACTION_CONCURRENCY)
    total = len(images)
    summary_lock = threading.Lock()
    # Pre-size the results list so each task can slot its result at its own
    # index — keeps summary.results in deterministic filename order even
    # though tasks finish out of order.
    ordered_results: list[Optional[ImageResult]] = [None] * total

    def _task(index: int, image_path: Path) -> None:
        if on_image_start:
            on_image_start(index, total, image_path.name)

        result = _process_one_image(
            image_path=image_path,
            client=client,
            prompt=prompt,
            output_folder=output_folder,
            run_timestamp=run_timestamp,
            batch_name=batch_name,
            batch_started_at_utc=batch_started_at_utc,
        )

        with summary_lock:
            ordered_results[index - 1] = result
            if result.success:
                summary.succeeded += 1
            else:
                summary.failed += 1

        if on_image_done:
            on_image_done(index, total, result)

    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="gemini-img") as pool:
        futures = [
            pool.submit(_task, index, image_path)
            for index, image_path in enumerate(images, start=1)
        ]
        # Surface the first task-level exception (if any) instead of
        # swallowing it — _process_one_image already catches GeminiClientError
        # per image, so anything propagating here is a genuine bug.
        for future in futures:
            future.result()

    summary.results.extend(r for r in ordered_results if r is not None)
    return summary


# --- Internals ---------------------------------------------------------------

def _process_one_image(
    image_path: Path,
    client: RealGeminiClient,
    prompt: str,
    output_folder: Path,
    run_timestamp: str,
    batch_name: Optional[str] = None,
    batch_started_at_utc: Optional[str] = None,
) -> ImageResult:
    """
    One image → one Gemini call → one JSON on disk. Returns an ImageResult
    describing the outcome.
    """
    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    try:
        # Phase 5: combined pass. The prompt asks Gemini to return both
        # extraction and pricing, so we enable Google Search grounding on
        # the same call. Any web-ish failure mode now surfaces as the image's
        # api_error — there is no separate pricing retry.
        response = client.analyse_images(
            [str(image_path)],
            prompt,
            enable_web_search=True,
        )
        api_error: str | None = None
    except GeminiClientError as exc:
        # Record the failure but keep the run going — other images may succeed.
        response = None
        api_error = str(exc)

    duration_ms = int((time.perf_counter() - t0) * 1000)
    finished_at = datetime.now(timezone.utc)

    if response is not None:
        schema_valid, schema_error = _validate_against_schema(response)
    else:
        schema_valid, schema_error = False, "no response (api_error)"

    # Phase 5: Gemini now returns pricing inline with extraction. The prompt
    # asks for a top-level `pricing` key on the response; we hoist it up to
    # the artifact root so the Inbound list endpoint / UI / CSV all keep
    # reading it from the same place they did during the two-pass design.
    # Stripping it from `response` keeps the ListingResponse shape clean
    # (pricing isn't part of the draft-content layers).
    pricing_block: dict | None = None
    if isinstance(response, dict):
        raw_pricing = response.pop("pricing", None)
        if isinstance(raw_pricing, dict):
            pricing_block = raw_pricing

    out_path = output_folder / f"extraction_{run_timestamp}__{_safe_stem(image_path)}.json"
    artifact: dict = {
        "meta": {
            "started_at_utc": started_at.isoformat(),
            "finished_at_utc": finished_at.isoformat(),
            "duration_ms": duration_ms,
            "model": client.model_name,
            "prompt_path": str(PROMPT_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
            "prompt_chars": len(prompt),
            "input_folder": (
                str(image_path.parent.relative_to(REPO_ROOT)).replace("\\", "/")
                if image_path.parent.is_relative_to(REPO_ROOT) else str(image_path.parent)
            ),
            # Always a list — one element here — so the UI handles the shape
            # uniformly even if we later batch multiple images per artifact.
            "image_files": [image_path.name],
            "schema_valid": schema_valid,
            "schema_error": schema_error,
            "api_error": api_error,
            # Stamp pricing metadata when Gemini actually returned a block.
            # Kept on `meta` (not inside `pricing`) so the UI can distinguish
            # "pricing ran" from "pricing field happens to be present".
            "pricing_fetched_at_utc": finished_at.isoformat() if pricing_block else None,
            "pricing_web_search_enabled": True,
            # Batch identity — stamped by the HTTP endpoint (from the Prep
            # screen) so Recent Batches can group these artifacts. CLI runs
            # without a batch name leave both fields None.
            "batch_name": batch_name,
            "batch_started_at_utc": batch_started_at_utc,
        },
        "response": response,
    }
    if pricing_block is not None:
        artifact["pricing"] = pricing_block
    out_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return ImageResult(
        image_name=image_path.name,
        out_path=out_path,
        success=api_error is None,
        duration_ms=duration_ms,
        api_error=api_error,
        schema_valid=schema_valid,
        schema_error=schema_error,
    )


def _validate_against_schema(response: dict) -> tuple[bool, str | None]:
    """
    Validate `response` against contracts/gemini_response_schema.json.
    Non-fatal — a schema mismatch just gets recorded so the UI can flag it.
    """
    try:
        import jsonschema  # already a backend dep
    except ImportError:
        return False, "jsonschema package not installed; skipping validation."

    if not SCHEMA_PATH.is_file():
        return False, f"Schema file not found: {SCHEMA_PATH}"

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=response, schema=schema)
        return True, None
    except jsonschema.ValidationError as exc:
        return False, exc.message


def _utc_timestamp_for_filename() -> str:
    """UTC timestamp safe for Windows filenames (no colons). e.g. 2026-04-19T15-45-22Z"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


# Defense against weird image filenames when embedding them into artifact
# filenames. Strips whitespace and path separators.
_UNSAFE_STEM_CHARS = re.compile(r"[\s/\\]")


def _safe_stem(path: Path) -> str:
    return _UNSAFE_STEM_CHARS.sub("_", path.stem)
