"""Google Gemini LLM provider.

Wraps the official ``google-genai`` SDK so the rest of Ekatra never imports
Google SDK types directly. The API key is always taken from configuration
(:class:`~ekatra.config.settings.Settings.gemini_api_key`, loaded from the
``GEMINI_API_KEY`` environment variable); it is never logged or serialized.

The provider raises :class:`GeminiProviderError` before any network call when
no key is configured, keeping the team runtime fully deterministic.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any, Callable

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


_TRANSIENT_MARKERS = (
    "429", "500", "502", "503", "504", "unavailable", "resource_exhausted",
    "deadline", "timed out", "timeout", "overloaded", "connection",
)


_RETRY_DELAY = re.compile(r"retry(?:Delay)?\D{0,12}(\d+(?:\.\d+)?)\s*s", re.I)


def _retry_delay(exc: Exception, attempt: int) -> float:
    """Seconds to wait: the server's suggested delay if given, else backoff."""
    match = _RETRY_DELAY.search(str(exc))
    if match:
        return min(90.0, float(match.group(1)) + 1.0)
    return min(60.0, 5.0 * (2**attempt))


def _is_transient(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def generate(
    prompt: str,
    *,
    json_mode: bool = False,
    max_output_tokens: int | None = None,
    timeout_seconds: float = 180.0,
    retries: int = 5,
    model: str | None = None,
    settings: "Settings | None" = None,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Generate text (or a JSON document) with retries on transient errors.

    Used by the real build mode. ``json_mode`` asks Gemini for a JSON response.
    Rate-limit / server / timeout errors are retried with exponential backoff;
    any other error (bad key, bad request) is raised immediately. The API key
    is never included in raised messages.
    """
    from google.genai import types

    from ekatra.config.settings import get_settings

    config = settings or get_settings()
    client = build_gemini_client(config)
    gen_config = types.GenerateContentConfig(
        temperature=config.model_temperature,
        response_mime_type="application/json" if json_mode else None,
        max_output_tokens=max_output_tokens,
        http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
    )
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = client.models.generate_content(
                model=model or config.gemini_model, contents=prompt, config=gen_config
            )
            text = getattr(response, "text", None)
            if isinstance(text, str) and text.strip():
                return text
            last = GeminiProviderError("Gemini returned an empty response")
        except Exception as exc:  # noqa: BLE001 - classified below
            if not _is_transient(exc):
                raise GeminiProviderError(_scrub(str(exc), config)) from None
            last = exc
        if attempt < retries:
            sleep(_retry_delay(last, attempt))
    raise GeminiProviderError(_scrub(f"Gemini request failed: {last}", config))


def _scrub(message: str, config: "Settings") -> str:
    key = config.gemini_api_key.strip()
    return message.replace(key, "***") if key else message


__all__ = ["GeminiProviderError", "build_gemini_client", "generate", "generate_text"]