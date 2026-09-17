# Ekatra — Agent Specifications

> Defines the responsibilities and boundaries of the initial six agent roles.

## 1. Project Manager

### Responsibility

Acts as the planning and coordination agent.

### Tasks

* Understand project requirements
* Decompose requirements into tasks
* Identify dependencies
* Assign appropriate roles
* Monitor overall progress
* Request replanning when required

### Should NOT

* Directly control deterministic agent spawning
* Override adaptive-controller decisions arbitrarily
* Perform all development work itself

---

## 2. Architect

### Responsibility

Designs the technical structure of the software.

### Tasks

* Define architecture
* Select appropriate components
* Define interfaces
* Identify technical dependencies
* Review architectural consistency

### Output

Structured architecture/design information for development agents.

---

## 3. Frontend Developer

### Responsibility

Handles frontend-related implementation tasks.

### Tasks

* UI implementation
* Components
* Client-side logic
* API integration
* Frontend testing/fixes

Multiple frontend instances may exist in the adaptive pool.

Example:

```text
Frontend-1
Frontend-2
Frontend-3
```

---

## 4. Backend Developer

### Responsibility

Handles backend and server-side implementation.

### Tasks

* APIs
* Business logic
* Database integration
* Authentication-related implementation
* Backend testing/fixes

Multiple backend instances may exist.

---

## 5. QA / Testing Agent

### Responsibility

Evaluates software correctness and identifies defects.

### Tasks

* Generate/execute tests
* Identify failures
* Validate requirements
* Report defects
* Verify fixes

The QA agent should provide structured test results where possible.

---

## 6. Security Agent

### Responsibility

Identifies security risks in the software.

### Tasks

* Review authentication/authorization
* Identify vulnerabilities
* Inspect suspicious code
* Review security-sensitive components
* Assign/report risk severity

Security findings may affect adaptive orchestration.

Example:

```text
Security Risk ↑
      ↓
Risk Score ↑
      ↓
Security Task Priority ↑
      ↓
Additional Security Capacity
```

---

## 7. Agent Communication

Agents should communicate through structured shared state/task outputs rather than unrestricted direct conversations wherever possible.

Agent outputs should contain enough structured information for downstream agents to consume.

---

## 8. Agent Pool Rule

The initial system contains six **roles**, not necessarily six runtime agents.

Example:

```text
Role: Backend Developer

Backend Pool:
Backend-1
Backend-2
Backend-3
```

The adaptive controller determines runtime capacity.

---

## 9. Agent Design Rule

Each agent should have:

* Clear responsibility
* Role-specific prompt/instructions
* Structured input
* Structured output
* Access only to required state/tools

Do not create separate agents for every small task.
