"""
Application settings loaded from environment variables.

Inputs:  environment variables (or .env file via pydantic-settings)
Outputs: a singleton Settings instance at module level

Required env vars:
  DATABASE_URL      — PostgreSQL connection string
  GEMINI_API_KEY    — Google Gemini API key (unused in mock mode)

Optional env vars:
  STORAGE_BASE_PATH — base directory for images/exports/logs (default: ./storage)
  LOG_LEVEL         — Python log level string (default: INFO)
  USE_MOCK_GEMINI   — set "true" to force mock Gemini client (default: true)
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The canonical .env lives at the repo root, not inside backend/. Resolve an
# absolute path to it so pydantic-settings finds it regardless of the cwd
# uvicorn is launched from (dev.bat starts uvicorn inside backend/, so a
# relative ".env" would miss the real file).
#   parents: [0]=core, [1]=service_photo, [2]=src, [3]=backend, [4]=repo root
_REPO_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    # --- Database ---
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/service_photo_dev"

    # --- Gemini ---
    GEMINI_API_KEY: str = "placeholder-not-needed-for-mock"

    # --- Storage ---
    STORAGE_BASE_PATH: str = "./storage"

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    # --- Gemini mode ---
    # Set USE_MOCK_GEMINI=false in the environment to use the real client.
    USE_MOCK_GEMINI: bool = True

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT_ENV),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


# Module-level singleton — import this everywhere instead of instantiating Settings directly.
settings = Settings()
