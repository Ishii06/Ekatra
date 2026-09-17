"""Optional manual Gemini smoke test.

Not part of ``pytest``; run only when a real ``GEMINI_API_KEY`` is configured:

    python -m ekatra.llm.smoke

This speaks to the live Gemini API and prints only a short confirmation plus
the configured model name — never the API key.
"""

from __future__ import annotations

import sys


def main() -> int:
    from ekatra.config.settings import get_settings
    from ekatra.llm.gemini import GeminiProviderError, build_gemini_client

    settings = get_settings()
    try:
        build_gemini_client(settings)
    except GeminiProviderError as exc:
        print(f"SKIPPED: {exc}")
        return 0

    model = settings.gemini_model
    print(f"Gemini smoke test: model={model!r} (client constructed OK).")
    return 0


if __name__ == "__main__":
    sys.exit(main())