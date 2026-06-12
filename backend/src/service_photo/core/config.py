"""
Application settings loaded from environment variables.

Inputs:  environment variables (and optionally an .env file)
Outputs: a singleton Settings instance at module level

Required env vars:
  GEMINI_API_KEY    — Google Gemini API key

Optional env vars:
  APP_DATA_DIR      — base directory for input_images/, inbound/, exports/,
                      and catalog.db. Defaults to the repo root for local
                      dev. On hosted deployments (e.g. Railway) point at a
                      persistent volume like /data.
  ENV_FILE          — absolute path to a dotenv file. Overrides the default
                      lookup. Use this on hosted deployments where there is
                      no repo root layout.
  LOG_LEVEL         — Python log level string (default: INFO)

Env-file resolution order:
  1. ENV_FILE env var, if set and the file exists.
  2. Repo-root .env (parents[4] of this file), if it exists. Preserves the
     dev.bat / local-dev workflow on Windows.
  3. None — rely entirely on real environment variables (this is the normal
     case on Railway / any container host that injects vars directly).
"""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# parents: [0]=core, [1]=service_photo, [2]=src, [3]=backend, [4]=repo root.
# This still works for the local Windows dev flow. In a container the layout
# is different and this path simply won't exist — the resolver below falls
# through to None, and the container relies on real env vars (Railway-style)
# or an explicit ENV_FILE override.
_REPO_ROOT_GUESS = Path(__file__).resolve().parents[4]
_REPO_ROOT_ENV = _REPO_ROOT_GUESS / ".env"


def _resolve_env_file() -> str | None:
    """Pick the dotenv file to load, or return None if we should rely on
    process environment variables only."""
    explicit = os.environ.get("ENV_FILE")
    if explicit:
        explicit_path = Path(explicit)
        if explicit_path.is_file():
            return str(explicit_path)
        # Explicit override that doesn't exist is almost certainly a config
        # mistake worth surfacing — but pydantic-settings will silently no-op
        # on a missing file, so just return the path and let it ignore.
        return str(explicit_path)
    if _REPO_ROOT_ENV.is_file():
        return str(_REPO_ROOT_ENV)
    return None


class Settings(BaseSettings):
    # --- Gemini ---
    # Placeholder default keeps imports working in test runs that never make
    # a real API call (inbound tests stub at the run_extraction level).
    GEMINI_API_KEY: str = "placeholder-not-set"

    # --- Storage ---
    # Base directory for the inbound pipeline's filesystem state and the
    # SQLite store (catalog.db).
    # Local default: the repo root (so input_images/, inbound/, exports/
    # land in the repo as they always have).
    # Hosted default (set in the Dockerfile / Railway env): /data.
    APP_DATA_DIR: str = str(_REPO_ROOT_GUESS)

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    # --- Gemini call hardening (Phase 7 production-hardening pass) ---
    # Per-request timeout. Grounded (web-search) calls can legitimately take
    # 60-90s; anything past this is treated as a hung call and aborted so the
    # extraction job can't wedge at "running" forever.
    GEMINI_TIMEOUT_SECONDS: int = 150
    # How many times to re-try a single image's Gemini call after a transient
    # failure (rate limit, 5xx, timeout) before recording it as failed.
    # Total attempts = 1 + GEMINI_MAX_RETRIES.
    GEMINI_MAX_RETRIES: int = 2

    # --- Gemini speed/cost tuning (Phase 7 throughput pass) ---
    # gemini-2.5-flash ships with "dynamic thinking" ON by default: the model
    # spends an unbounded number of internal reasoning tokens before answering,
    # which is both slow (often the biggest chunk of a 30s call) and billed at
    # the output-token rate. For this workload (structured extraction from a
    # clear product photo) we cap it.
    #   0  = thinking disabled entirely (fastest, cheapest — the default here)
    #   >0 = cap thinking at that many tokens (e.g. 512 if pricing quality
    #        ever looks worse with thinking fully off)
    #   -1 = restore Gemini's dynamic default (no cap)
    GEMINI_THINKING_BUDGET: int = 0

    # Longest edge (pixels) an image may have before we downscale it client-side
    # prior to upload. Professional camera shots are 4000-8000px / multi-MB;
    # Gemini tiles images into 768px crops, so anything beyond ~2 tiles per edge
    # buys no extraction accuracy — it just inflates upload time and prompt
    # tokens. 1536 = two tiles per edge, plenty to read engraved model names.
    # Set 0 to disable downscaling and send original bytes.
    GEMINI_MAX_IMAGE_EDGE_PX: int = 1536

    # --- Extraction concurrency ---
    # How many images to process in parallel during one extraction run.
    # Each image is an independent Gemini call, so this directly divides
    # wall-clock time for a batch. Paid-tier 2.5-flash allows ~1000 RPM, so
    # the real ceiling is far above this; keep it single-digit to stay polite
    # and leave headroom for retries. 1 = sequential (the original behavior).
    EXTRACTION_CONCURRENCY: int = 6

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Module-level singleton — import this everywhere instead of instantiating Settings directly.
settings = Settings()


# Convenience: resolved Path for the data directory. Created on demand by the
# routes that write into it (so a fresh container or volume just works).
APP_DATA_PATH = Path(settings.APP_DATA_DIR).resolve()
