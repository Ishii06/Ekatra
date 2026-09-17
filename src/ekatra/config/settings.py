"""Application configuration loaded from environment variables.

Secrets such as ``GEMINI_API_KEY`` are read from the environment or from a
local ``.env`` file. The application remains importable and testable when no
API key is present.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime configuration for Ekatra.

    Values are read from environment variables first, then from ``.env`` in
    the project root.
    """

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM provider selection (ADR-006). Empty string means no LLM calls.
    llm_provider: str = "gemini"

    # Gemini credentials (ADR-006). Empty string means no LLM calls are made.
    gemini_api_key: str = ""

    # Gemini model configuration (remains runtime-configurable for experiments).
    gemini_model: str = "gemini-2.5-flash"
    model_temperature: float = 0.2

    # Retry limit for failed tasks (experimental parameter).
    max_task_retries: int = 3

    # Adaptive workflow limits.
    max_adaptive_rounds: int = 8

    def has_api_key(self) -> bool:
        """Return True when the configured LLM provider's API key is present."""
        return bool(self.gemini_api_key.strip())


def get_settings() -> Settings:
    """Return a cached application settings instance."""
    settings = get_settings.__dict__.get("_cached")
    if settings is None:
        settings = Settings()
        get_settings.__dict__["_cached"] = settings
    return settings


__all__ = ["Settings", "get_settings"]