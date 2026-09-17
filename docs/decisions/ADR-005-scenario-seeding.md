# ADR-005: State-Driven Scenario Seeding for Experiments

## Decision

Experiments share one controlled input — a scenario — with both orchestration
strategies by materializing the scenario's task set directly into the workflow
state's existing `tasks` field. The fixed `project_manager_node` and the
adaptive `adaptive_plan` node detect a non-empty incoming `tasks` field and
adopt it instead of calling `ProjectManagerAgent.plan(...)`; every eligible task
is assigned to its role's (baseline) agent and the strategy then orchestrates
that exact task set.

## Reason

The experiment harness (Milestone 8) requires "the same scenario inputs under
both strategies; only orchestration differs". The default PM planning path
only ever produces the fixed five-task role plan, which cannot represent
workload/risk scenarios (saturated single-role backlogs, retries, failures).
Replacing the planner with scenario-driven input is the minimal change that
keeps:

* The existing `EkatraState` schema unchanged (tests assert exact key sets).
* The task lifecycle, message bus, agent pool, controller, workload and risk
  formulas, and the M7 observability model untouched.
* Scenario-parity: the identical task dicts are produced from one scenario
  object regardless of strategy.

The PM-plan path remains the default when no seeded tasks are present, so the
original fixed and adaptive behavior is preserved.

## Behavior

* `project_manager_node` / `adaptive_plan` adopt seeded tasks: they rebuild the
  `TaskManager` from the provided task dicts, assign every non-terminal task to
  its role's baseline agent, broadcast a `STATUS_UPDATE`, and emit
  `workflow_started`, `task_created`, and `task_assigned` events exactly like
  the planning path.
* No fixed agent is spawned or terminated; within its one node visit each role
  drains every task it can start — the single static agent executes all
  `PENDING` / `ASSIGNED` / `RETRY` tasks whose dependencies are satisfied,
  resets to IDLE between tasks, and never selects `FAILED` tasks (the baseline
  does not recover from failures).
* The adaptive loop observes the same adopted task set on every controller
  cycle and may spawn / terminate / reassign / prioritize per the documented
  deterministic policy.

## Implementation notes (M8)

* `adaptive_execute` now increments `adaptive_cycle` after every round. The
  control loop previously never advanced the cycle, so multi-cycle scenarios
  could not terminate once `max_adaptive_rounds` was meant to bound the run.
* The round limit is now a strict bound on execution cycles: `max_adaptive_rounds`
  permits at most that many execute/adapt cycles. The off-by-one is gone — a
  limit of `N` no longer silently allows only `N - 1` cycles, and no extra
  cycle is appended past the limit. The loop also terminates as soon as the
  workflow reaches its terminal execution state (no executable work remains).
* `workflow_completed` uses one shared rule for the fixed and adaptive
  strategies: it is emitted only when every task is terminal (`COMPLETED` /
  `FAILED` / `CANCELLED`) and no executable work remains. Reaching the graph's
  final node is not enough while `PENDING` / `RETRY` work can still run.
* Scenarios forbid terminal task states, non-execution roles, forward
  dependency references, duplicate keys, paths, and secret-looking content.

## Consequences

* Same inputs, same orchestration entry points; strategy is the only
  experimental variable.
* Data dependency: workflow graph nodes now branch on the presence of `tasks`
  in the incoming state, which is an intentional, documented coupling to the
  harness.