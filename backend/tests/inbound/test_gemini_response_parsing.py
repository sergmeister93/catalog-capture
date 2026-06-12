"""
Tests for real_gemini._parse_json_response — the strict-then-lenient JSON
recovery for Gemini text responses.

Background: with thinking disabled (Phase 7T), gemini-2.5-flash is sloppier
about output discipline. Observed in production: a response opening with a
bare ``` fence but never closing it, which the strict fence regex rejects and
plain json.loads chokes on. The lenient fallback recovers one balanced JSON
object from anywhere in the text; genuinely truncated JSON must still fail.

Pure-function tests — no network, no SDK.
"""

import json

import pytest

from service_photo.integrations.real_gemini import (
    GeminiClientError,
    _parse_json_response,
)

# A small but realistic payload, in the shape the extraction returns.
PAYLOAD = {
    "schema_version": "1.0",
    "extraction_warnings": [],
    "overview": {"product_name": "Nikon D3200 DSLR", "brand": "Nikon"},
}
PAYLOAD_JSON = json.dumps(PAYLOAD, indent=2)


def test_bare_json_parses():
    assert _parse_json_response(PAYLOAD_JSON) == PAYLOAD


def test_wellformed_fence_parses():
    assert _parse_json_response(f"```json\n{PAYLOAD_JSON}\n```") == PAYLOAD


def test_opening_fence_without_closing_fence():
    # The exact production failure: response starts with ``` but Gemini never
    # closed the fence, so the strict regex (which anchors on a trailing ```)
    # doesn't match and the raw text starts with backticks.
    assert _parse_json_response(f"```\n{PAYLOAD_JSON}") == PAYLOAD


def test_trailing_prose_after_closing_fence():
    # Grounded responses sometimes append source notes after the fence.
    text = f"```json\n{PAYLOAD_JSON}\n```\nSources: ebay.com, mpb.com"
    assert _parse_json_response(text) == PAYLOAD


def test_preamble_before_json():
    text = f"Here is the extraction you asked for:\n{PAYLOAD_JSON}"
    assert _parse_json_response(text) == PAYLOAD


def test_truncated_json_still_fails():
    # Cut the payload mid-object: lenient recovery must NOT paper over a
    # half-finished extraction.
    truncated = PAYLOAD_JSON[: len(PAYLOAD_JSON) // 2]
    with pytest.raises(GeminiClientError, match="not valid JSON"):
        _parse_json_response(f"```\n{truncated}")


def test_no_json_at_all_fails():
    with pytest.raises(GeminiClientError, match="not valid JSON"):
        _parse_json_response("I could not analyse this image.")


def test_top_level_array_fails():
    # The contract is a dict; a bare array should be rejected, not coerced.
    with pytest.raises(GeminiClientError, match="expected dict"):
        _parse_json_response('[{"product_name": "Nikon"}]')
