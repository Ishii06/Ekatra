# ADR-001: Use LangGraph

## Decision

Use LangGraph as the workflow and state orchestration framework.

## Reason

Ekatra requires:

* Stateful workflows
* Explicit agent transitions
* Conditional routing
* Shared execution state
* Iterative orchestration

LangGraph provides these capabilities without requiring Ekatra to build a workflow engine from scratch.

## Important

LangGraph is an implementation technology, not the research contribution.

The research focus remains adaptive multi-agent orchestration.
