"""LLM provider integrations for Ekatra.

Providers follow the ``build_<provider>_client(settings)`` + ``generate_text``
convention so the agent abstraction can stay provider-agnostic. Currently only
Google Gemini is implemented (``docs/decisions/ADR-006-gemini.md``); the mock
and tool execution strategies never touch this package.
"""

from __future__ import annotations

from ekatra.llm.gemini import GeminiProviderError, build_gemini_client, generate_text

__all__ = ["GeminiProviderError", "build_gemini_client", "generate_text"]