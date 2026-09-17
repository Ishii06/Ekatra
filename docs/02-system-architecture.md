# Ekatra — System Architecture

> This document defines the high-level architecture. OpenCode must follow this structure unless a change is explicitly discussed and documented.

## 1. Architecture Overview

Ekatra consists of five major layers:

```text
User / Project Input
        ↓
Project Manager / Planning
        ↓
Task & State Management
        ↓
Agent Orchestration
        ↓
Specialized Agent Pools
        ↓
Execution / Evaluation
        ↓
Observation & Metrics
        ↓
Adaptive Controller
        ↺
```

The adaptive controller forms a feedback loop around the execution system.

---

## 2. Major Components

### Project Manager

Responsible for:

* Understanding project requirements
* Creating a development plan
* Decomposing work into tasks
* Identifying dependencies
* Assigning appropriate roles

The Project Manager may use an LLM for reasoning.

---

### Task Manager

Responsible for:

* Creating tasks
* Maintaining task state
* Tracking dependencies
* Managing priorities
* Tracking retries
* Recording timestamps

The Task Manager should remain deterministic.

---

### Agent Manager

Responsible for:

* Maintaining agent pools
* Creating agent instances
* Assigning tasks
* Tracking agent states
* Releasing/terminating agents

---

### Adaptive Controller

Responsible for:

* Observing system state
* Calculating workload
* Calculating risk
* Selecting adaptive actions
* Triggering resource reallocation

The controller must use deterministic logic for measurable orchestration decisions.

---

### Specialized Agents

Initial roles:

```text
Project Manager
Architect
Frontend Developer
Backend Developer
QA / Testing
Security
```

Developer, QA, and Security roles may have multiple runtime instances.

---

### Execution Layer

Responsible for executing agent tasks and collecting:

* Outputs
* Success/failure
* Execution time
* Errors
* Retry information

Actual code execution/tool integration may be introduced incrementally.

---

### Observability Layer

Collects:

* Task events
* Agent events
* Workload values
* Risk values
* Adaptive decisions
* Timing information
* Experiment metrics

---

## 3. State Flow

```text
Requirement
    ↓
Project Manager
    ↓
Task Graph / Queue
    ↓
Scheduler
    ↓
Agent Pool
    ↓
Execution
    ↓
Result
    ↓
State Update
    ↓
Observation
    ↓
Adaptive Controller
    ↓
Resource Allocation
    ↺
```

---

## 4. Hybrid Control Architecture

Ekatra intentionally separates:

```text
LLM Layer
    ↓
Reasoning / Planning

Deterministic Layer
    ↓
Measurement / Decisions / Allocation
```

The LLM should not directly decide arbitrary agent creation or termination.

This separation improves:

* Reproducibility
* Debugging
* Experimentation
* Interpretability

---

## 5. LangGraph

LangGraph shall be used as the workflow/state orchestration framework.

It should represent the major workflow stages and state transitions.

However, LangGraph itself is **not the research contribution**.

The research contribution is the adaptive orchestration logic implemented around the workflow.

---

## 6. Initial Implementation Principle

Start with a simple architecture.

Do not introduce:

* Distributed infrastructure
* Microservices
* Message brokers
* Complex databases
* Kubernetes
* Unnecessary agent frameworks

unless a later requirement genuinely requires them.

The prototype should remain easy to run locally and easy to evaluate.
