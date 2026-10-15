"""Shared test fixtures.

Tests must be deterministic and independent of the developer's local ``.env``
(which may hold a real API key), so settings never read it here.
"""

import pytest

from ekatra.config.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.__dict__.pop("_cached", None)
    yield
    get_settings.__dict__.pop("_cached", None)
