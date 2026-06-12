"""
Real Gemini client.

Calls the Google Gemini API with the extraction prompt and a list of local image
files, then returns the parsed JSON response as a dict (suitable for validating
against contracts/gemini_response_schema.json).

Inputs:
    - image_paths: list of absolute or relative paths to image files (jpg/png/webp)
    - prompt:      the extraction prompt text (loaded by the caller)

Outputs:
    - dict that should validate against the Gemini response schema. Schema
      validation itself is the caller's responsibility — this client only
      handles transport, multimodal request shaping, and JSON parsing.

SDK note:
    Uses `google-genai` (package name, import as `from google import genai`) —
    the new official Google SDK for the Gemini API. The older `google-generativeai`
    (0.5.x) did not support the native `google_search` grounding tool on Gemini
    2.x models, which Phase 5 single-pass pricing requires. Migrated to
    `google-genai` specifically so `tools=[Tool(google_search=GoogleSearch())]`
    would work on gemini-2.5-flash.

Environment:
    - GEMINI_API_KEY must be set (loaded from .env via pydantic-settings).
    - GEMINI_MODEL is read from settings if available, otherwise defaults to
      "gemini-2.5-flash". Override at construction time via the model_name arg.
"""

import json
import logging
import mimetypes
import os
import re
import time
from pathlib import Path

from service_photo.integrations.gemini_interface import (
    GeminiClientInterface,
    GeminiClientError,
)
from service_photo.core.config import settings

# Path to the Gemini extraction prompt template (used as a fallback if the caller
# doesn't pass an explicit prompt — see analyse_images for behavior).
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "listing_extraction_v1.md"

# Default model. Flash is fast/cheap for iteration; swap to gemini-2.5-pro for
# the final pass if quality demands it.
DEFAULT_MODEL = "gemini-2.5-flash"

logger = logging.getLogger(__name__)

# HTTP-ish status codes we treat as transient and worth retrying: rate limit
# plus the usual server-side hiccups. Anything else (400 bad request, 403 auth)
# fails immediately — retrying won't fix those.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Backoff schedule (seconds) between retry attempts. Index = retry number.
# Kept short — the caller is a user-facing progress UI, not a batch job.
_RETRY_BACKOFF_SECONDS = [3, 8, 15]

# Image MIME types Gemini's vision models accept. Anything not on this list will
# be rejected before the API call to avoid wasting a request.
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}


class RealGeminiClient(GeminiClientInterface):
    """
    Real Gemini API client via the `google-genai` SDK. Sends the prompt and
    inline image bytes in one multimodal request, then parses the JSON text
    response.

    The prompt instructs Gemini to return raw JSON without code fences, but we
    defensively strip ```json ... ``` fences in case the model includes them
    anyway.
    """

    def __init__(self, model_name: str | None = None) -> None:
        # Lazy import so the rest of the app (and the mock client path) does not
        # require google-genai to be importable at module load.
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise ImportError(
                "google-genai is required for RealGeminiClient. "
                "Install it via `pip install google-genai` or re-run `pip install -e '.[dev]'` "
                "from the backend directory."
            ) from exc

        api_key = settings.GEMINI_API_KEY
        if not api_key or api_key == "placeholder-not-needed-for-mock":
            raise GeminiClientError(
                "GEMINI_API_KEY is not set. Add it to .env at the repo root before "
                "instantiating RealGeminiClient."
            )

        # Store SDK handles on the instance so analyse_images can reach them
        # without re-importing. `types` holds the request-shape dataclasses
        # (Part, Tool, GoogleSearch, GenerateContentConfig).
        self._genai = genai
        self._types = genai_types
        # Client-level timeout so a hung call can't stall an extraction thread
        # forever. google-genai's HttpOptions.timeout is in MILLISECONDS.
        self._client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(
                timeout=settings.GEMINI_TIMEOUT_SECONDS * 1000,
            ),
        )
        # Allow per-instance override; otherwise read from env (GEMINI_MODEL) or use default.
        self._model_name = model_name or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL

    # ------------------------------------------------------------------ public

    @property
    def model_name(self) -> str:
        """The Gemini model id this client is configured to call."""
        return self._model_name

    def analyse_images(
        self,
        image_paths: list[str],
        prompt: str,
        enable_web_search: bool = False,
    ) -> dict:
        """
        Send `prompt` plus inline image bytes to Gemini and return the parsed
        JSON dict from the response.

        When `enable_web_search` is True the request includes the native
        Google Search grounding tool, so Gemini can do live web lookups
        (Phase 5: combined extraction + pricing in one call). Leaving it False
        sends an ungrounded request (cheaper, deterministic).

        Raises GeminiClientError for any non-success outcome (no images, bad
        MIME type, transport failure, non-JSON response).
        """
        if not image_paths:
            raise GeminiClientError("analyse_images requires at least one image path.")

        types = self._types

        # Build multimodal contents: the prompt text followed by one Part per
        # image. google-genai accepts a single list-of-parts for one turn.
        parts: list = [prompt]
        for path_str in image_paths:
            parts.append(self._image_part(path_str))

        # Only attach the grounding tool when the caller asked for it. An
        # ungrounded request just passes `config=None` (or no tools) which is
        # the cheapest/fastest path.
        if enable_web_search:
            config = types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
            )
        else:
            config = None

        response = self._generate_with_retry(parts, config)

        # response.text is a convenience accessor that joins all text parts.
        # If Gemini blocked the response (safety filter, etc.), .text returns
        # None rather than raising (google-genai behavior diverges from the
        # older SDK here — guard explicitly).
        raw_text = response.text
        if not raw_text:
            raise GeminiClientError(
                "Gemini returned no text content (possibly blocked by safety filter "
                "or the response contained only non-text parts)."
            )

        return _parse_json_response(raw_text)

    # ----------------------------------------------------------------- helpers

    def _generate_with_retry(self, parts: list, config):
        """
        Call generate_content, retrying transient failures (rate limit, 5xx,
        timeout) up to settings.GEMINI_MAX_RETRIES times with a short backoff.

        Non-transient failures (bad request, auth) raise immediately — retrying
        those just wastes time and quota. Every attempt's outcome is logged so
        hosted logs show what each image actually cost in attempts and tokens.
        """
        max_retries = max(0, settings.GEMINI_MAX_RETRIES)
        last_exc: Exception | None = None

        for attempt in range(1 + max_retries):
            t0 = time.perf_counter()
            try:
                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=parts,
                    config=config,
                )
            except Exception as exc:
                last_exc = exc
                elapsed = time.perf_counter() - t0
                if attempt < max_retries and _is_transient_error(exc):
                    delay = _RETRY_BACKOFF_SECONDS[min(attempt, len(_RETRY_BACKOFF_SECONDS) - 1)]
                    logger.warning(
                        "Gemini call failed (attempt %d/%d, %.1fs): %s — retrying in %ds",
                        attempt + 1, 1 + max_retries, elapsed, exc, delay,
                    )
                    time.sleep(delay)
                    continue
                # Out of retries, or a non-transient error: wrap and raise so
                # the caller has a single exception type to catch.
                raise GeminiClientError(f"Gemini API call failed: {exc}") from exc

            # Success — log usage so token spend per image is visible in
            # hosted logs (this is the only place cost data surfaces).
            self._log_usage(response, time.perf_counter() - t0, attempt)
            return response

        # Defensive: the loop either returns or raises, but keep the type
        # checker honest about all paths.
        raise GeminiClientError(f"Gemini API call failed: {last_exc}") from last_exc

    def _log_usage(self, response, elapsed_seconds: float, attempt: int) -> None:
        """Log one structured line of token usage for a successful call."""
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = getattr(usage, "prompt_token_count", None)
        output_tokens = getattr(usage, "candidates_token_count", None)
        total_tokens = getattr(usage, "total_token_count", None)
        logger.info(
            "gemini_call_ok model=%s elapsed_s=%.1f attempt=%d prompt_tokens=%s output_tokens=%s total_tokens=%s",
            self._model_name, elapsed_seconds, attempt + 1,
            prompt_tokens, output_tokens, total_tokens,
        )

    def _image_part(self, path_str: str):
        """
        Read one image file and return the `Part` object the google-genai SDK
        expects. Validates MIME type up front so we fail before the network call.
        """
        path = Path(path_str)
        if not path.is_file():
            raise GeminiClientError(f"Image file not found: {path}")

        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            raise GeminiClientError(
                f"Unsupported image MIME type for Gemini vision: {mime_type!r} "
                f"(file: {path.name}). Supported: {sorted(SUPPORTED_IMAGE_MIME_TYPES)}."
            )

        return self._types.Part.from_bytes(
            data=path.read_bytes(),
            mime_type=mime_type,
        )


# ---------------------------------------------------------------- module utils

def _is_transient_error(exc: Exception) -> bool:
    """
    Decide whether a Gemini SDK exception is worth retrying.

    google-genai raises google.genai.errors.APIError subclasses that carry a
    `.code` (HTTP status). Timeouts and connection drops come through as
    httpx exceptions with no code. We retry on known-transient status codes
    and on anything that looks like a network/timeout failure.
    """
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code in _RETRYABLE_STATUS_CODES
    # No status code — likely a transport-level failure (timeout, reset).
    # The class name check avoids importing httpx here just for isinstance.
    name = type(exc).__name__.lower()
    return any(token in name for token in ("timeout", "connect", "network", "transport"))

# Matches a fenced ```json ... ``` (or plain ``` ... ```) wrapper around the
# response body. Used defensively — the prompt tells Gemini not to fence.
_FENCE_PATTERN = re.compile(
    r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
)


def _parse_json_response(raw_text: str) -> dict:
    """
    Parse Gemini's text response into a JSON dict, tolerating optional code
    fences. Raises GeminiClientError if the text is not valid JSON.
    """
    text = raw_text.strip()
    fence_match = _FENCE_PATTERN.match(text)
    if fence_match:
        text = fence_match.group("body").strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GeminiClientError(
            f"Gemini response was not valid JSON: {exc.msg} "
            f"(first 200 chars: {text[:200]!r})"
        ) from exc

    if not isinstance(parsed, dict):
        raise GeminiClientError(
            f"Gemini response parsed to {type(parsed).__name__}, expected dict."
        )
    return parsed
