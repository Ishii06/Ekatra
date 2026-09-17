# Ekatra — Development Rules

> These rules apply to OpenCode and any future implementation work.

## 1. Read Before Modifying

Before making architectural changes, read the relevant files in `/docs`.

At minimum:

```text
00-project-overview.md
01-requirements.md
02-system-architecture.md
```

For adaptive work, also read:

```text
04-adaptive-orchestration.md
05-task-state-model.md
```

---

## 2. Incremental Development

Do not implement the entire project from one prompt.

Work on one clearly defined feature or milestone at a time.

---

## 3. Preserve Architecture

Do not redesign working architecture without a concrete reason.

If an architectural change is necessary:

1. Explain why.
2. Identify affected components.
3. Update the relevant documentation.
4. Record the decision in `/docs/decisions/` when significant.

---

## 4. Avoid Overengineering

Do not add:

* Unnecessary frameworks
* Unnecessary agents
* Unnecessary abstractions
* Unnecessary services
* Unnecessary dependencies

Prefer the simplest implementation that satisfies the requirement.

---

## 5. Adaptive Controller

Keep deterministic adaptive logic separate from LLM reasoning.

Do not allow an LLM response to directly execute:

```text
spawn_agent()
terminate_agent()
```

without passing through the controller's defined decision logic.

---

## 6. Configuration

Do not scatter experimental values throughout the code.

Keep configurable:

* Thresholds
* Weights
* Agent limits
* Retry limits
* Model settings

---

## 7. Secrets

Never hardcode:

* API keys
* Passwords
* Tokens
* Credentials

Use environment variables.

Never commit `.env`.

---

## 8. Testing

When implementing deterministic functionality:

```text
Implement
→ Test
→ Fix
→ Re-run
```

Do not assume that code works because it compiles.

---

## 9. Logging

Important state changes and adaptive decisions must be observable through structured logs.

Avoid excessive debug output that makes experiment logs difficult to analyze.

---

## 10. Existing Code

Before modifying a file:

* Read the existing implementation.
* Understand its dependencies.
* Preserve working behavior.
* Change only what is necessary.

Do not replace working code with a completely different implementation without justification.

---

## 11. Dependencies

Before adding a dependency, determine whether the existing stack can already solve the problem.

Avoid dependency growth without a clear purpose.

---

## 12. Git

Use meaningful commits after stable milestones.

Example:

```text
feat: implement task state management
feat: add adaptive workload controller
test: add workload decision tests
fix: handle failed task retry
```

Do not commit:

```text
.env
API keys
large generated datasets
temporary files
virtual environments
```

---

## 13. Definition of Done

A task is complete when:

* Implementation works.
* Relevant tests pass.
* Architecture remains consistent.
* Required logging exists.
* No unnecessary files/dependencies were introduced.
* The feature can be demonstrated.

For adaptive functionality, the behavior must be **observable**, not merely present in source code.
