"""
Gemini integration factory.

get_gemini_client() returns the correct client based on settings.USE_MOCK_GEMINI.
Import this from the service layer instead of importing clients directly.
"""

from service_photo.integrations.gemini_interface import GeminiClientInterface


def get_gemini_client() -> GeminiClientInterface:
    from service_photo.core.config import settings

    if settings.USE_MOCK_GEMINI:
        from service_photo.integrations.mock_gemini import MockGeminiClient
        return MockGeminiClient()
    else:
        from service_photo.integrations.real_gemini import RealGeminiClient
        return RealGeminiClient()
