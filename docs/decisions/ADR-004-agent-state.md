# ADR-004: Explicit Agent State

## Decision

Maintain explicit runtime state for every agent instance.

## Reason

Adaptive orchestration requires knowing:

* Which agents exist
* Which agents are active
* Which agents are idle
* Which agents can accept work
* Which agents can be released

Therefore agent state must be represented explicitly rather than inferred only from LLM messages.

## Lifecycle

```text
CREATED
→ IDLE
→ ACTIVE
→ COMPLETED
→ IDLE
→ TERMINATED
```

## Important

Agent state belongs to the orchestration system, not to individual LLM responses.
