# Ekatra — Task & Agent State Model

## 1. Task State

A task follows:

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

A task may also be cancelled if explicitly required by the project workflow.

---

## 2. Task Metadata

Each task should contain:

```text
id
description
role
priority
complexity
dependencies
risk
status
assigned_agent
retry_count
created_at
started_at
completed_at
```

Optional fields may be added when genuinely required.

---

## 3. Dependency Rules

A task is executable only when all required dependencies are completed.

Example:

```text
Architecture
     ↓
Backend API
     ↓
Frontend Integration
     ↓
QA
```

The scheduler must not assign `Frontend Integration` while `Backend API` is incomplete if that dependency is required.

---

## 4. Agent State

Agent lifecycle:

```text
CREATED
   ↓
IDLE
   ↓
ACTIVE
   ↓
COMPLETED
   ↓
IDLE
   ↓
TERMINATED
```

`ACTIVE` means the agent is currently executing a task.

`IDLE` means the agent is available for work.

`TERMINATED` means the runtime instance is no longer available.

---

## 5. State Ownership

State transitions should be controlled by the appropriate system component.

```text
Task Manager
→ task state

Agent Manager
→ agent state

Adaptive Controller
→ allocation decision
```

Do not allow individual LLM agents to arbitrarily modify global orchestration state.

---

## 6. State History

Important transitions should be logged.

Example:

```text
Task-14
PENDING → ASSIGNED
assigned_agent = Backend-2

Task-14
ASSIGNED → RUNNING

Task-14
RUNNING → COMPLETED
```

This history is useful for debugging and evaluation.
