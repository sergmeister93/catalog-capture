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

    # --- Extraction concurrency ---
    # How many images to process in parallel during one extraction run.
    # Each image is an independent Gemini call, so this directly divides
    # wall-clock time for a batch. Keep modest to stay under Gemini
    # rate limits (free tier is ~10 RPM for 2.5-flash). 1 = sequential
    # (the original behavior).
    EXTRACTION_CONCURRENCY: int = 3

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
