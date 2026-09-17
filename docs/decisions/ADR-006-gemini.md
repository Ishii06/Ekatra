# ADR-006: Use Google Gemini as the LLM Provider

## Status

**Accepted.**

## Decision

Route LLM-backed agent reasoning through the **Google Gemini** API using the
official `google-genai` SDK, replacing the OpenAI integration adopted in
[ADR-002](./ADR-002-openai.md).

The provider is wrapped in a thin `ekatra.llm.gemini` module so the rest of
the codebase (Agent abstraction, graph, controller, observability) never
imports Google SDK types directly.

## Reason

Ekatra requires LLM capabilities for requirement understanding, planning, task
decomposition, agent reasoning, and software-development tasks. The original
prototype selected OpenAI via LangChain (ADR-002); those SDKs were never wired
into active source code. The team standardized on Gemini via the first-party
`google-genai` SDK for the following reasons:

* Single first-party SDK (`from google import genai`) with environment-driven
  `GEMINI_API_KEY` configuration.
* No third-party orchestration wrapper needed for the provider call path;
  LangGraph remains the workflow orchestrator and is untouched.
* Gemini 2.5 Flash (`gemini-3.5-flash`) is a stable, GA model offering the
  best price-performance for agentic use cases.

## Configuration

* `LLM_PROVIDER=gemini` — the only implemented provider.
* `GEMINI_API_KEY=...` — read from the environment or `.env`; an empty value
  means no LLM calls are made (mock/tools strategies remain fully functional).
* `GEMINI_MODEL=gemini-3.5-flash` — default model; runtime-configurable for
  experiments, as before.

The key is never logged, never serialized into experiment records, snapshots,
or observability events, and never committed. `.env` remains gitignored.

## Consequences

* The `Agent` base-class interface is unchanged; the existing `llm` strategy
  now routes through `ekatra.llm.gemini.generate_text` and raises
  `GeminiProviderError` when no key is configured.
* `langchain-openai` and `openai` were removed from `requirements.txt`;
  `langgraph` and `langchain-core` are retained.
* `pytest` must never require a live Gemini call; provider behavior is tested
  with the SDK client mocked. A real API smoke test is available separately as
  `python -m ekatra.llm.smoke`.

## Important

The LLM is not responsible for deterministic agent scaling decisions (see
ADR-002).