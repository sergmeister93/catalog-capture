"""
Mock Gemini client for local development and testing.

Returns a deterministic, schema-valid combined payload for a Canon EOS R6
camera body — extraction fields (overview / description / specs / accessories)
plus a pricing block. This allows the full backend + UI workflow to be
exercised without a real Gemini API key or live web search.

The response is valid against contracts/gemini_response_schema.json (which
now includes an optional top-level `pricing` block).
"""

from service_photo.integrations.gemini_interface import GeminiClientInterface


class MockGeminiClient(GeminiClientInterface):
    """
    Returns a hardcoded Canon EOS R6 draft response with pricing.

    `enable_web_search` is accepted but ignored — the mock always returns the
    same payload. Pretending to do web grounding would add complexity without
    adding value for local dev.
    """

    def analyse_images(
        self,
        image_paths: list[str],
        prompt: str,
        enable_web_search: bool = False,
    ) -> dict:
        # Deterministic combined response for a Canon EOS R6 body. The
        # `pricing` block is produced in the same call as the extraction —
        # same shape a real grounded Gemini call would return.
        return {
            "schema_version": "1.0",
            "extraction_warnings": [
                "Serial number not clearly visible in provided images.",
                "Battery compartment label partially obscured."
            ],
            "overview": {
                "product_name": "Canon EOS R6 Mirrorless Camera Body",
                "brand": "Canon",
                "model": "EOS R6",
                "product_family": "EOS R",
                "variant": None,
                "mount_type": "Canon RF",
                "serial_number_visible": None,
                "condition_summary": "Used camera body with light visible cosmetic wear on exterior surfaces. Sensor area appears clean.",
                "confidence_notes": "Brand and model confirmed via visible body markings. Serial number not legible in images."
            },
            "description": {
                "short_title": "Canon EOS R6 Mirrorless Camera Body",
                "description_text": (
                    "Used Canon EOS R6 mirrorless camera body shown with light cosmetic wear. "
                    "Body markings are clear and legible. Sold as pictured."
                ),
                "visible_wear_notes": "Light surface wear visible on the body exterior near the grip and rear dial area.",
                "key_selling_points": (
                    "Popular full-frame mirrorless body. Clean overall presentation. "
                    "Canon RF mount for access to Canon's full RF lens lineup."
                ),
                "confidence_notes": "Condition assessment based on visible surfaces only; internal electronics not verifiable from images."
            },
            "specifications": {
                "sensor_format": "Full Frame",
                "megapixels": 20.1,
                "lens_mount": "Canon RF",
                "focal_length": None,
                "aperture": None,
                "iso_range": "100-102400 (expandable to 204800)",
                "shutter_range": "30s to 1/8000s",
                "video_capabilities": "4K UHD up to 60fps, Full HD up to 120fps",
                "storage_media": "SD / CFexpress Type B (dual slot)",
                "connectivity": "Wi-Fi, Bluetooth",
                "weight_grams": 680,
                "other_specifications": {
                    "battery_type": "LP-E6NH",
                    "screen_size": "3.0 in vari-angle"
                },
                "confidence_notes": "Specifications sourced from Canon EOS R6 published specs; not all verified from images alone."
            },
            "accessories": {
                "included_accessories_text": "Body cap visible. Battery present in compartment.",
                "inferred_accessories_text": "LP-E6NH battery and LC-E6 charger likely included based on typical bundle.",
                "missing_typical_accessories_text": "Original box and shoulder strap not visible in images.",
                "confidence_notes": "Accessory observations based on visible items only. Inferred items not confirmed."
            },
            # Phase 5 — pricing inline with extraction. Real Gemini produces
            # this via Google Search grounding; the mock just returns a plausible
            # Canon R6 snapshot so the UI and CSV path work offline.
            "pricing": {
                "product": "Canon EOS R6 Body (mock)",
                "pricing": {
                    "ebay_sold_avg": 1195.00,
                    "mpb_retail": 1299.00,
                    "keh_retail": 1349.00,
                    "bh_used": 1249.00,
                },
                "market_valuation": {
                    "fair_price": 1225.00,
                    "deal_threshold": 1099.00,
                },
                "market_summary": (
                    "Used R6 bodies have softened roughly 10% since the R6 Mark II's "
                    "release, settling around $1,200 on the secondary market. Expect "
                    "further gradual decline through 2026 as Mk II inventory grows."
                ),
                "sources": [
                    {
                        "platform": "eBay",
                        "url": "https://www.ebay.com/itm/mock-listing-1",
                        "price": 1150.00,
                        "title": "Canon EOS R6 Body — Excellent, low shutter count",
                        "condition": "Excellent",
                        "observed_at": None,
                    },
                    {
                        "platform": "MPB",
                        "url": "https://www.mpb.com/mock-listing-2",
                        "price": 1299.00,
                        "title": "Canon EOS R6 — Like New",
                        "condition": "Like New",
                        "observed_at": None,
                    },
                ],
                "uncertainty_tags": [],
            },
        }
