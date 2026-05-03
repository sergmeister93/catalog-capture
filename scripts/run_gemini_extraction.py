"""
Run a Gemini vision extraction against a folder of test images and save one
JSON per image under ./inbound/.

What this script does:
  1. Loads .env from the repo root (so GEMINI_API_KEY is picked up).
  2. Delegates to service_photo.services.inbound_extraction.run_extraction,
     which scans the input folder, calls Gemini per image, validates each
     response against the schema, and writes one JSON per image to inbound/.
  3. Prints per-image progress + a final summary line.

This script and the POST /api/v1/inbound/extract endpoint share the same
underlying service, so behaviour is identical whether you launch it from
the CLI or from the UI.

Inputs:
    --folder PATH        Folder of input images (default: ./input_images)
    --model MODEL_ID     Gemini model id (default: env GEMINI_MODEL or gemini-2.5-flash)
    --output-dir PATH    Where to write the JSONs (default: ./inbound)
    --purge              Delete existing extraction_*.json in output-dir first
                         (default: off, so CLI runs accumulate by default)

Outputs:
    One JSON file per image under <output-dir>/. Filename:
        extraction_<UTC-timestamp>__<image-stem>.json
    Each has shape: { "meta": { ... }, "response": { ... } | null }

Usage (from repo root, with backend .venv active):
    py scripts/run_gemini_extraction.py
    py scripts/run_gemini_extraction.py --folder test_data/sample_images
    py scripts/run_gemini_extraction.py --model gemini-2.5-pro
    py scripts/run_gemini_extraction.py --purge
"""

import argparse
import sys
from pathlib import Path

# --- Path setup --------------------------------------------------------------
# This script lives at <repo>/scripts/. Compute the repo root and add the
# backend src/ to sys.path so we can import service_photo.* without installing.
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_SRC = REPO_ROOT / "backend" / "src"
sys.path.insert(0, str(BACKEND_SRC))

# Load .env from the repo root before importing anything that reads settings.
# pydantic-settings will also try, but its working-directory default may not
# resolve correctly when this script is invoked from anywhere.
ENV_FILE = REPO_ROOT / ".env"
if ENV_FILE.is_file():
    # Minimal hand-rolled .env loader so we don't pull in python-dotenv as a
    # direct dep. Handles KEY=VALUE lines, ignores comments and blanks.
    import os
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Don't overwrite anything already set in the real environment.
        os.environ.setdefault(key, value)

# These imports must come AFTER the .env load and sys.path insert.
from service_photo.integrations.gemini_interface import GeminiClientError  # noqa: E402
from service_photo.services.inbound_extraction import (  # noqa: E402
    ImageResult,
    run_extraction,
)

# --- Defaults ---------------------------------------------------------------

DEFAULT_INPUT_FOLDER = REPO_ROOT / "input_images"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "inbound"


# --- Main -------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a per-image Gemini extraction over a folder of photos. "
                    "Each image becomes one product listing — one Gemini call per image, "
                    "one JSON file per image in inbound/."
    )
    parser.add_argument("--folder", type=Path, default=DEFAULT_INPUT_FOLDER,
                        help=f"Folder of input images (default: {DEFAULT_INPUT_FOLDER})")
    parser.add_argument("--model", type=str, default=None,
                        help="Override Gemini model id (default: env GEMINI_MODEL or gemini-2.5-flash)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"Where to write the JSONs (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--purge", action="store_true",
                        help="Delete any existing extraction_*.json in --output-dir before this run.")
    args = parser.parse_args()

    # Progress hooks — print before each call and after each result. Same info
    # the UI shows, just in a terminal.
    def on_start(index: int, total: int, image_name: str) -> None:
        print(f"[{index}/{total}] {image_name}")

    def on_done(index: int, total: int, result: ImageResult) -> None:
        if result.success:
            label = "schema OK" if result.schema_valid else f"schema FAIL: {result.schema_error}"
            print(f"    OK ({result.duration_ms} ms) — {label}")
        else:
            print(f"    FAILED ({result.duration_ms} ms) — {result.api_error}")
        rel = _relative_or_abs(result.out_path, REPO_ROOT)
        print(f"    -> {rel}\n")

    try:
        summary = run_extraction(
            input_folder=args.folder,
            output_folder=args.output_dir,
            model=args.model,
            purge_existing=args.purge,
            on_image_start=on_start,
            on_image_done=on_done,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc))
    except (GeminiClientError, ImportError) as exc:
        raise SystemExit(f"Failed to initialise Gemini client: {exc}")

    print(
        f"Done. {summary.succeeded} succeeded, {summary.failed} failed, "
        f"{summary.total} total. Model: {summary.model}."
    )

    # Non-zero only when every image failed — partial success is still useful.
    return 1 if summary.succeeded == 0 else 0


def _relative_or_abs(path: Path, root: Path) -> str:
    """Return `path` relative to `root` if possible, else the absolute form."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
