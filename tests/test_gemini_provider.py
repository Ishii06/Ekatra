"""Pre-M9: Google Gemini LLM provider migration tests.

These tests never make a real Gemini API call: the provider is exercised with
the google-genai client mocked/patched. A live smoke test exists separately as
``python -m ekatra.llm.smoke`` and is never part of ``pytest``.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from ekatra.config import Settings, get_settings

PROJECT = "Build a simple todo application."


def _no_key() -> Settings:
    return Settings(_env_file=None, gemini_api_key="", gemini_model="gemini-3.5-flash")


# -- 1. Gemini configuration loads -----------------------------------------


class TestGeminiConfiguration:
    def test_defaults_are_gemini(self):
        settings = _no_key()
        assert settings.llm_provider == "gemini"
        assert settings.gemini_api_key == ""
        assert settings.gemini_model == "gemini-3.5-flash"
        assert settings.has_api_key() is False

    def test_cached_settings_are_gemini(self):
        settings = get_settings()
        assert settings.gemini_api_key == ""
        assert settings.has_api_key() is False

    def test_model_is_runtime_configurable(self):
        settings = Settings(_env_file=None, gemini_api_key="x", gemini_model="gemini-3.8-flash")
        assert settings.has_api_key() is True
        assert settings.gemini_model == "gemini-3.8-flash"


# -- 2. Missing API key handled --------------------------------------------


class TestMissingApiKeyHandling:
    def test_build_client_requires_key(self):
        from ekatra.llm.gemini import GeminiProviderError, build_gemini_client

        with pytest.raises(GeminiProviderError):
            build_gemini_client(_no_key())

    def test_generate_text_requires_key(self):
        from ekatra.llm.gemini import GeminiProviderError, generate_text

        with pytest.raises(GeminiProviderError):
            generate_text("hello", settings=_no_key())

    def test_documented_agent_llm_strategy_requires_key(self, monkeypatch):
        from ekatra.agents.roles import BackendDeveloperAgent
        from ekatra.tasks import TaskManager

        monkeypatch.setattr(get_settings(), "gemini_api_key", "")
        agent = BackendDeveloperAgent("BACKEND-1", strategy="llm")
        task = TaskManager().create(role="backend", description="x")
        result = agent.execute(task)
        assert result.success is False
        assert "GEMINI_API_KEY" in result.output


# -- 3. Mock execution works without a key ---------------------------------


class TestMockExecutionWithoutKey:
    def test_mock_agent_executes_without_key(self, monkeypatch):
        from ekatra.agents.roles import BackendDeveloperAgent
        from ekatra.tasks import TaskManager

        monkeypatch.setattr(get_settings(), "gemini_api_key", "")
        agent = BackendDeveloperAgent("BACKEND-1")
        result = agent.execute(
            TaskManager().create(role="backend", description="x")
        )
        assert result.success is True
        assert "implemented" in result.output.lower()


# -- 4. Gemini client init uses the configured env var ---------------------


class TestClientInitialization:
    def test_build_client_passes_configured_key(self, monkeypatch):
        import google.genai

        captured: dict[str, object] = {}

        def fake_client(api_key=None, **_: object) -> object:
            captured["api_key"] = api_key
            return object()

        monkeypatch.setattr(google.genai, "Client", fake_client)
        from ekatra.llm.gemini import build_gemini_client

        client = build_gemini_client(
            Settings(_env_file=None, gemini_api_key="AIza-test-placeholder")
        )
        assert captured["api_key"] == "AIza-test-placeholder"
        assert client is not None

    def test_generate_text_uses_configured_model(self, monkeypatch):
        captured: dict[str, object] = {}

        class FakeResponse:
            text = "mock gemini output"

        class FakeClient:
            class models:
                @staticmethod
                def generate_content(*, model: str, contents: str) -> FakeResponse:
                    captured["model"] = model
                    captured["contents"] = contents
                    return FakeResponse()

        monkeypatch.setattr(
            "ekatra.llm.gemini.build_gemini_client",
            lambda settings: FakeClient(),
        )
        from ekatra.llm.gemini import generate_text

        out = generate_text("ping", settings=_no_key())
        assert captured == {"model": "gemini-3.5-flash", "contents": "ping"}
        assert out == "mock gemini output"


# -- 5. No OpenAI provider in active source --------------------------------


class TestNoOpenAiProviderInSource:
    def test_active_source_has_no_openai_references(self):
        src_root = Path(__file__).resolve().parents[1] / "src"
        forbidden = re.compile(
            r"openai|OPENAI|ChatOpenAI|langchain_openai", re.IGNORECASE
        )
        offenders: list[str] = []
        for path in sorted(src_root.rglob("*.py")):
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if forbidden.search(line):
                    offenders.append(f"{path.relative_to(src_root)}:{lineno}: {line.strip()}")
        assert not offenders, offenders


# -- 6. No secret in serialized config / experiment records ----------------


class TestNoSecretInSerialization:
    def test_experiment_record_payload_has_no_api_key_fields(self):
        from ekatra.observability.experiment import ExperimentRecord

        payload = json.dumps(ExperimentRecord().to_dict())
        assert "gemini_api_key" not in payload
        assert "api_key" not in payload

    def test_configured_key_never_enters_snapshots_or_records(self, monkeypatch):
        from ekatra.graph import run
        from ekatra.observability.experiment import ExperimentRecord
        from ekatra.state import snapshot_state

        secret = "AIza-supersecret-token-000"
        monkeypatch.setattr(get_settings(), "gemini_api_key", secret)

        state = run({"project_description": PROJECT})
        snap = json.dumps(snapshot_state(state))
        assert secret not in snap
        assert "gemini_api_key" not in snap

        payload = json.dumps(ExperimentRecord().to_dict())
        assert secret not in payload
        assert "gemini_api_key" not in payload

    def test_record_secret_guard_now_checks_gemini_key(self, monkeypatch):
        from ekatra.observability.experiment import ExperimentRecord

        secret = "AIza-guard-test-key-777"
        monkeypatch.setattr(get_settings(), "gemini_api_key", secret)
        assert not ExperimentRecord().contains_secrets()
        assert ExperimentRecord(
            raw_events=[{"type": "tool_executed", "content": secret}]
        ).contains_secrets()


# -- 7. Agent interfaces unchanged ------------------------------------------


class TestAgentInterfacesUnchanged:
    def test_execute_signature_unchanged(self):
        from ekatra.agents.base import Agent

        sig = inspect.signature(Agent.execute)
        assert list(sig.parameters) == ["self", "task"]

    def test_result_and_role_shape_unchanged(self):
        from ekatra.agents.base import AgentExecutionResult, Role

        fields = list(AgentExecutionResult.__dataclass_fields__)
        assert fields == ["agent_id", "task_id", "success", "output", "messages", "data"]
        assert [r.value for r in Role] == [
            "project_manager", "architect", "frontend", "backend", "qa", "security",
        ]