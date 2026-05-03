"""
Abstract Gemini client interface.

Any Gemini implementation (mock or real) must implement GeminiClientInterface.
The submit service calls this interface without knowing which client is in use.
"""

from abc import ABC, abstractmethod


class GeminiClientInterface(ABC):
    """
    Contract for Gemini AI clients.

    analyse_images() receives a list of image file paths (ordered by image_order)
    and returns a dict that validates against contracts/gemini_response_schema.json.

    Raises GeminiClientError on API-level failures.
    """

    @abstractmethod
    def analyse_images(
        self,
        image_paths: list[str],
        prompt: str,
        enable_web_search: bool = False,
    ) -> dict:
        """
        Submit images to Gemini and return the structured draft response dict.

        Args:
            image_paths:        Ordered list of local filesystem paths (or storage
                                paths) for the job's images.
            prompt:             The extraction prompt text loaded from the template.
            enable_web_search:  When True the concrete client should attach the
                                Google Search grounding tool so Gemini can do live
                                web lookups as part of the same call. Used by the
                                inbound flow to produce combined extraction +
                                pricing in a single pass. Mock clients ignore this.

        Returns:
            A dict that validates against gemini_response_schema.json.

        Raises:
            GeminiClientError: When the API call fails or returns an unexpected error.
        """
        ...


class GeminiClientError(Exception):
    """Raised when the Gemini API call fails (network, quota, unexpected response)."""
    pass
