# ADR-003: Separate Adaptive Controller

## Decision

Implement adaptive orchestration as a deterministic controller separate from LLM reasoning.

## Reason

The research requires measurable and reproducible decisions based on:

* Workload
* Risk
* Queue state
* Agent availability
* Execution behavior

A deterministic controller makes these decisions easier to test, inspect, and evaluate.

## Controller Responsibilities

```text
Observe
Analyze
Decide
Allocate
```

## LLM Responsibilities

```text
Understand
Plan
Reason
Execute
```

This separation is a core architectural principle of Ekatra.
