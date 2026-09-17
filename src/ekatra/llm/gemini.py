"""Google Gemini LLM provider.

Wraps the official ``google-genai`` SDK so the rest of Ekatra never imports
Google SDK types directly. The API key is always taken from configuration
(:class:`~ekatra.config.settings.Settings.gemini_api_key`, loaded from the
``GEMINI_API_KEY`` environment variable); it is never logged or serialized.

The provider raises :class:`GeminiProviderError` before any network call when
no key is configured, keeping the team runtime fully deterministic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ekatra.config.settings import Settings


class GeminiProviderError(RuntimeError):
    """Raised when the Gemini provider cannot be used (e.g. no API key)."""


def build_gemini_client(settings: "Settings") -> Any:
    """Build a ``google.genai.Client`` from the given settings.

    The key is passed explicitly from the configured environment variable
    (``settings.gemini_api_key``) rather than relying on ambient SDK defaults.
    """
    if not settings or not settings.gemini_api_key.strip():
        raise GeminiProviderError(
            "Gemini provider requires GEMINI_API_KEY to be configured "
            "(environment or .env)."
        )
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key.strip())


def generate_text(
    prompt: str,
    *,
    model: str | None = None,
    settings: "Settings | None" = None,
) -> str:
    """Generate text with the configured Gemini model.

    Args:
        prompt: The prompt sent to the model.
        model: Override the configured model name.
        settings: Settings to use; defaults to the cached application settings.

    Returns:
        The model's text response (empty string when the response carries no
        text payload).
    """
    from ekatra.config.settings import get_settings

    config = settings or get_settings()
    client = build_gemini_client(config)
    model_name = model or config.gemini_model
    response = client.models.generate_content(model=model_name, contents=prompt)
    text = getattr(response, "text", None)
    return text if isinstance(text, str) else ""


__all__ = ["GeminiProviderError", "build_gemini_client", "generate_text"]