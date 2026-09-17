# ADR-002: Use OpenAI Models

## Status

**Superseded by [ADR-006: Use Google Gemini as the LLM Provider](./ADR-006-gemini.md).**

The OpenAI integration remains here as historical context for the prototype's
initial model choice; no OpenAI code or dependencies remain in the project.

## Decision

Use OpenAI models through the supported LangChain integration for initial agent reasoning.

## Reason

The prototype requires LLM capabilities for:

* Requirement understanding
* Planning
* Task decomposition
* Agent reasoning
* Software-development tasks

Using an existing model allows the project to focus on orchestration rather than model training.

## Configuration

API credentials must be supplied through environment variables.

The model should remain configurable so experiments can specify the model used.

## Important

The LLM is not responsible for deterministic agent scaling decisions.
