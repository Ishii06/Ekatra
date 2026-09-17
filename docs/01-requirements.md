# Ekatra — Requirements

> This document defines the implementation requirements for Ekatra.
> OpenCode must read this before implementing or modifying project functionality.

---

## 1. Core System Requirements

Ekatra must be able to:

* Accept a software project description.
* Analyze the requirements through the Project Manager.
* Decompose requirements into executable tasks.
* Track task dependencies and priorities.
* Assign tasks to appropriate agent roles.
* Execute tasks through specialized agents.
* Track task success, failure, retries, and completion.
* Maintain the current state of agents and tasks.
* Record relevant execution and orchestration events.

---

## 2. Core Agent Roles

The initial implementation must contain only these six roles:

1. **Project Manager** — planning, requirement analysis, task decomposition.
2. **Architect** — system architecture and technical design.
3. **Frontend Developer** — frontend implementation.
4. **Backend Developer** — backend implementation.
5. **QA / Testing** — testing and defect identification.
6. **Security** — security analysis and vulnerability identification.

Do not introduce additional agent roles unless explicitly requested.

Multiple instances of a role may exist in the adaptive system.

Example:

```text
Backend Pool
├── Backend-1
├── Backend-2
└── Backend-3
```

---

## 3. Task Requirements

Every task should maintain structured metadata including:

```text
id
role
description
priority
complexity
dependencies
risk
status
assigned_agent
retry_count
timestamps
```

Task lifecycle:

```text
PENDING
   ↓
ASSIGNED
   ↓
RUNNING
   ↓
COMPLETED
```

Failure path:

```text
RUNNING
   ↓
FAILED
   ↓
RETRY
   ↓
RUNNING
```

Tasks with unresolved dependencies must not be executed.

---

## 4. Agent Requirements

Agents must have explicit roles and responsibilities.

Agents should maintain a lifecycle similar to:

```text
CREATED → IDLE → ACTIVE → COMPLETED → IDLE
                                      ↓
                                 TERMINATED
```

The system must know which agents are:

* Available
* Active
* Busy
* Completed
* Terminated

An active agent must not be terminated while executing a task.

---

## 5. Adaptive Orchestration Requirements

**Adaptive orchestration is the primary research functionality of Ekatra.**

The system must dynamically respond to changes in development workload and risk.

The orchestration loop is:

```text
OBSERVE
   ↓
ANALYZE
   ↓
DECIDE
   ↓
ALLOCATE
   ↓
EXECUTE
   ↓
EVALUATE
   ↓
ADAPT
   ↺
```

The system must support these adaptive actions:

```text
CONTINUE
SPAWN
TERMINATE
REASSIGN
PRIORITIZE
```

---

## 6. Workload Requirements

The adaptive controller must monitor workload using measurable system information.

Initial workload model:

```text
Workload =
    0.40 × Queue Length
  + 0.30 × Task Complexity
  + 0.20 × Execution Delay
  + 0.10 × Failure Rate
```

All input values must be normalized before calculating the score.

The resulting workload score should be represented on a **0–100 scale**.

Initial experimental interpretation:

```text
< 40       → Continue
40–70      → Monitor
> 70       → Consider spawning
```

These values are **configurable experimental parameters**, not scientifically established constants.

OpenCode must keep the weights and thresholds configurable rather than hardcoding them throughout the codebase.

---

## 7. Risk Requirements

The system must monitor development risk.

Potential risk indicators include:

* Security findings
* Authentication/authorization issues
* Suspicious code
* Failed security checks
* Repeated task failures
* High-risk tasks

Risk should be represented on a **0–100 scale**.

Elevated risk may trigger:

* Security-agent allocation
* Increased task priority
* Additional review
* Task reassignment

Risk thresholds must remain configurable.

---

## 8. Dynamic Agent Scaling

The adaptive system must support runtime agent scaling.

### Spawn

When workload or risk justifies additional capacity:

```text
Backend Queue
     ↓
High Workload
     ↓
Adaptive Controller
     ↓
SPAWN Backend-2
     ↓
New task allocation
```

### Termination

When additional capacity is no longer required:

```text
Workload decreases
       ↓
Agent becomes unnecessary
       ↓
Agent released / terminated
```

Every spawn and termination decision must be logged with its reason and relevant system state.

---

## 9. Resource Reallocation

The adaptive controller must be capable of changing how available agent resources are assigned.

Examples:

* Reassigning a task from an overloaded agent.
* Prioritizing a blocked/high-risk task.
* Allocating another agent to a heavily loaded role.
* Releasing an unnecessary agent.

The goal is **dynamic resource allocation**, not simply creating more agents.

---

## 10. Deterministic Controller

The adaptive controller must remain separate from LLM reasoning.

### LLM responsibilities

The LLM may handle:

* Requirement understanding
* Planning
* Task decomposition
* Technical reasoning
* Agent-specific task execution

### Deterministic controller responsibilities

The controller must handle:

* Workload calculation
* Risk calculation
* Threshold evaluation
* Spawn decisions
* Termination decisions
* Reassignment decisions
* Resource allocation

Do not allow unrestricted LLM output to directly control agent spawning or termination.

---

## 11. Fixed Baseline

Ekatra must have a fixed-agent baseline for experimental comparison.

Example:

```text
1 Project Manager
1 Architect
1 Frontend Developer
1 Backend Developer
1 QA Agent
1 Security Agent
```

The fixed baseline must **not dynamically scale its agent count**.

Where practical, both systems should use the same:

* Workload
* Task definitions
* Agent responsibilities
* LLM/model
* Experimental environment
* Evaluation metrics

The primary difference should be the orchestration strategy.

---

## 12. Logging Requirements

The system must log important events, including:

```text
Project creation
Task creation
Task assignment
Task start
Task completion
Task failure
Retry
Agent creation
Agent activation
Agent termination
Task reassignment
Workload calculation
Risk calculation
Adaptive decision
```

Adaptive decisions should record enough information to answer:

```text
What happened?
Why did the controller react?
What decision was made?
What changed afterward?
```

---

## 13. Evaluation Data

The implementation must collect enough data to compare fixed and adaptive execution.

At minimum, support measurement of:

* Total completion time
* Task completion time
* Queue waiting time
* Active agent count
* Average active agents
* Agent utilization
* Number of spawned agents
* Number of terminated agents
* Number of reallocations
* Task failures
* Retry count
* Quality/test results

Do not claim that the adaptive approach is better before experiments are performed.

---

## 14. Configuration

Experimental parameters must be configurable.

This includes:

* Workload weights
* Workload thresholds
* Risk thresholds
* Maximum agents per role
* Retry limits
* Model configuration
* Experiment settings

Avoid scattering configuration values throughout the implementation.

---

## 15. Testing Requirements

Core deterministic components must have tests.

At minimum, test:

* Task state transitions
* Dependency handling
* Workload calculation
* Risk calculation
* Agent allocation
* Agent spawning
* Agent termination
* Task reassignment
* Adaptive decisions

Adaptive behavior must have tests demonstrating that different system states can produce different orchestration decisions.

---

## 16. Security Requirements

* Never hardcode API keys.
* Load secrets from environment variables.
* Keep `.env` out of Git.
* Do not expose API keys in logs.
* Do not commit credentials or generated secrets.

---

## 17. Implementation Constraints

OpenCode must follow these constraints:

1. Do not redesign the architecture without a clear reason.
2. Do not add unnecessary dependencies.
3. Do not add unnecessary agent roles.
4. Keep deterministic orchestration separate from LLM reasoning.
5. Prefer simple implementations over premature abstractions.
6. Preserve working functionality when making changes.
7. Write tests for new core functionality.
8. Keep experimental parameters configurable.
9. Log adaptive decisions.
10. Make changes incrementally rather than implementing the entire system at once.

---

## 18. Definition of Done

A feature is considered complete when:

* It works as intended.
* Relevant tests pass.
* It follows the existing architecture.
* Important state changes are observable through logs.
* It does not unnecessarily break existing functionality.
* Its behavior can be demonstrated through a reproducible test or experiment.

For adaptive features specifically, **code containing an adaptive function is not sufficient**.

The implementation must demonstrate actual behavior such as:

```text
High workload
     ↓
Controller detects condition
     ↓
SPAWN
     ↓
New agent becomes available
     ↓
Task allocation changes
```

This observable behavior is essential because adaptive orchestration is the central research focus of Ekatra.
